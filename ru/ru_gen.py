"""ru_gen.py
Generator based main read until script. This is where readfish targets code lives. It performs the back bone of the selected
sequencing.
"""
# Core imports
import functools
import logging
import sys
import time
from collections import defaultdict, deque, Counter
from pathlib import Path
from timeit import default_timer as timer

# Third party imports
from ru.read_until_client import RUClient
from read_until.read_cache import AccumulatingCache
import toml

from ru.arguments import BASE_ARGS
from ru.basecall import Mapper as CustomMapper
from ru.basecall import GuppyCaller as Caller
from ru.utils import (
    print_args,
    get_run_info,
    between,
    setup_logger,
    describe_experiment,
)
from ru.utils import send_message, Severity, get_device, DecisionTracker


_help = "Run targeted sequencing"
_cli = BASE_ARGS + (
    (
        "--toml",
        dict(
            metavar="TOML",
            required=True,
            help="TOML file specifying experimental parameters",
        ),
    ),
    (
        "--paf-log",
        dict(
            help="PAF log",
            default=None,
        ),
    ),
    (
        "--chunk-log",
        dict(
            help="Chunk log",
            default=None,
        ),
    ),
)


CHUNK_LOG_FIELDS = (
    "client_iteration",
    "read_in_loop",
    "read_id",
    "channel",
    "read_number",
    "seq_len",
    "counter",
    "mode",
    "decision",
    "condition",
    "min_threshold",
    "count_threshold",
    "start_analysis",
    "end_analysis",
    "timestamp",
)


def simple_analysis(
    client,
    batch_size=512,
    throttle=0.1,
    unblock_duration=0.5,
    cl=None,
    pf=None,
    live_toml_path=None,
    flowcell_size=512,
    dry_run=False,
    run_info=None,
    conditions=None,
    mapper=None,
    caller_kwargs=None,
):
    """Analysis function

    Parameters
    ----------
    client : read_until.ReadUntilClient
        An instance of the ReadUntilClient object
    batch_size : int
        The number of reads to be retrieved from the ReadUntilClient at a time
    throttle : int or float
        The number of seconds interval between requests to the ReadUntilClient
    unblock_duration : int or float
        Time, in seconds, to apply unblock voltage
    cl : logging.Logger
        Log file to log chunk data to
    pf : logging.Logger
        Log file to log alignments to
    live_toml_path : str
        Path to a `live` TOML configuration file for ReadFish. If this exists when
        the run starts it will be deleted
    flowcell_size : int
        The number of channels on the flowcell, 512 for MinION and 3000 for PromethION
    dry_run : bool
        If True unblocks are replaced with `stop_receiving` commands
    run_info : dict
        Dictionary of {channel: index} where index corresponds to an index in `conditions`
    conditions : list
        Experimental conditions as List of namedtuples.
    mapper : mappy.Aligner
    caller_kwargs : dict

    Returns
    -------
    None
    """
    # Init logger for this function
    logger = logging.getLogger(__name__)

    # Delete live TOML file if it exists
    live_toml_path = Path(live_toml_path)
    if live_toml_path.is_file():
        live_toml_path.unlink()

    # TODO: test this
    # Write channels.toml
    d = {
        "conditions": {
            str(v): {"channels": [], "name": conditions[v].name}
            for k, v in run_info.items()
        }
    }
    for k, v in run_info.items():
        d["conditions"][str(v)]["channels"].append(k)

    channels_out = str(Path(client.mk_run_dir) / "channels.toml")
    with open(channels_out, "w") as fh:
        fh.write(
            "# This file is written as a record of the condition each channel is assigned.\n"
        )
        fh.write("# It may be changed or overwritten if you restart ReadFish.\n")
        fh.write("# In the future this file may become a CSV file.\n")
        toml.dump(d, fh)

    caller = Caller(
        address="{}:{}".format(caller_kwargs["host"], caller_kwargs["port"]),
        config=caller_kwargs["config_name"],
    )
    # What if there is no reference or an empty MMI

    decisiontracker = DecisionTracker()

    # DefaultDict[int: collections.deque[Tuple[str, ndarray]]]
    #  tuple is (read_id, previous_signal)
    # TODO: tuple should use read_number instead
    previous_signal = defaultdict(functools.partial(deque, maxlen=1))
    # count how often a read is seen
    tracker = defaultdict(Counter)

    interval = 600  # time in seconds we are going to log a message #ToDo: set to be an interval or supressed
    interval_checker = timer()

    # decided
    decided_reads = {}
    strand_converter = {1: "+", -1: "-"}

    read_id = ""

    # TODO: partial-ise / lambda unblock to take the unblock duration
    if dry_run:
        decision_dict = {
            "stop_receiving": lambda c, n: stop_receiving_action_list.append((c, n)),
            "proceed": None,
            "unblock": lambda c, n: stop_receiving_action_list.append((c, n)),
        }
        send_message(
            client.connection,
            "This is a test run. No unblocks will occur.",
            Severity.WARN,
        )
    else:
        decision_dict = {
            "stop_receiving": lambda c, n: stop_receiving_action_list.append((c, n)),
            "proceed": None,
            "unblock": lambda c, n: unblock_batch_action_list.append((c, n, read_id)),
        }
        send_message(
            client.connection, "This is a live run. Unblocks will occur.", Severity.WARN
        )
    decision_str = ""
    below_threshold = False
    exceeded_threshold = False

    l_string = "\t".join(("{}" for _ in CHUNK_LOG_FIELDS))
    loop_counter = 0
    while client.is_running:
        if live_toml_path.is_file():
            # Reload the TOML config from the *_live file
            run_info, conditions, new_reference, _ = get_run_info(
                live_toml_path, flowcell_size
            )

            # Check the reference path if different from the loaded mapper
            if new_reference != mapper.index:
                old_reference = mapper.index
                # Log to file and MinKNOW interface
                logger.info("Reloading mapper")
                send_message(
                    client.connection,
                    "Reloading mapper. ReadFish paused.",
                    Severity.INFO,
                )

                # Update mapper client.
                mapper = CustomMapper(new_reference)
                # Log on success
                logger.info("Reloaded mapper")

                # If we've reloaded a reference, delete the previous one
                if old_reference:
                    logger.info("Deleting old mmi {}".format(old_reference))
                    # We now delete the old mmi file.
                    Path(old_reference).unlink()
                    logger.info("Old mmi deleted.")

        # TODO: Fix the logging to just one of the two in use

        if not mapper.initialised:
            time.sleep(throttle)
            continue

        loop_counter += 1
        t0 = timer()
        r = 0
        unblock_batch_action_list = []
        stop_receiving_action_list = []

        for read_info, read_id, seq_len, results in mapper.map_reads_2(
            caller.basecall_minknow(
                reads=client.get_read_chunks(batch_size=batch_size, last=True),
                signal_dtype=client.signal_dtype,
                decided_reads=decided_reads,
            )
        ):
            r += 1
            read_start_time = timer()
            channel, read_number = read_info
            if read_number not in tracker[channel]:
                tracker[channel].clear()
            tracker[channel][read_number] += 1
            mode = ""
            exceeded_threshold = False
            below_threshold = False
            log_decision = lambda: cl.debug(
                l_string.format(
                    loop_counter,
                    r,
                    read_id,
                    channel,
                    read_number,
                    seq_len,
                    tracker[channel][read_number],
                    mode,
                    getattr(conditions[run_info[channel]], mode, mode),
                    conditions[run_info[channel]].name,
                    below_threshold,
                    exceeded_threshold,
                    read_start_time,
                    timer(),
                    time.time(),
                )
            )

            # Control channels
            if conditions[run_info[channel]].control:
                mode = "control"
                log_decision()
                stop_receiving_action_list.append((channel, read_number))
                continue

            # This is an analysis channel
            # Below minimum chunks
            if (
                tracker[channel][read_number]
                <= conditions[run_info[channel]].min_chunks
            ):
                below_threshold = True

            # Greater than or equal to maximum chunks
            if (
                tracker[channel][read_number]
                >= conditions[run_info[channel]].max_chunks
            ):
                exceeded_threshold = True

            # No mappings
            if not results:
                mode = "no_map"

            hits = set()
            for result in results:
                pf.debug("{}\t{}\t{}".format(read_id, seq_len, result))
                hits.add(result.ctg)

            if hits & conditions[run_info[channel]].targets:
                # Mappings and targets overlap
                coord_match = any(
                    between(r.r_st, c)
                    for r in results
                    for c in conditions[run_info[channel]]
                    .coords.get(strand_converter.get(r.strand), {})
                    .get(r.ctg, [])
                )
                if len(hits) == 1:
                    if coord_match:
                        # Single match that is within coordinate range
                        mode = "single_on"
                    else:
                        # Single match to a target outside coordinate range
                        mode = "single_off"
                elif len(hits) > 1:
                    if coord_match:
                        # Multiple matches with at least one in the correct region
                        mode = "multi_on"
                    else:
                        # Multiple matches to targets outside the coordinate range
                        mode = "multi_off"

            else:
                # No matches in mappings
                if len(hits) > 1:
                    # More than one, off-target, mapping
                    mode = "multi_off"
                elif len(hits) == 1:
                    # Single off-target mapping
                    mode = "single_off"

            # This is where we make our decision:
            # Get the associated action for this condition
            decision_str = getattr(conditions[run_info[channel]], mode)
            # decision is an alias for the functions "unblock" or "stop_receiving"
            decision = decision_dict[decision_str]

            # If max_chunks has been exceeded AND we don't want to keep sequencing we unblock
            if exceeded_threshold and decision_str != "stop_receiving":
                mode = "exceeded_max_chunks_unblocked"
                decisiontracker.event_seen(mode)
                unblock_batch_action_list.append((channel, read_number, read_id))

            # TODO: WHAT IS GOING ON?!
            #  I think that this needs to change between enrichment and depletion
            # If under min_chunks AND any mapping mode seen we unblock
            # if below_threshold and mode in {"single_off", "multi_off"}:
            if below_threshold and mode in {
                "single_on",
                "single_off",
                "multi_on",
                "multi_off",
            }:
                mode = "below_min_chunks_unblocked"
                unblock_batch_action_list.append((channel, read_number, read_id))
                decisiontracker.event_seen(decision_str)

            # proceed returns None, so we send no decision; otherwise unblock or stop_receiving
            elif decision is not None:
                decided_reads[channel] = read_id
                decision(channel, read_number)
                decisiontracker.event_seen(decision_str)

            log_decision()

        client.unblock_read_batch(unblock_batch_action_list, duration=unblock_duration)
        client.stop_receiving_batch(stop_receiving_action_list)

        t1 = timer()
        if r > 0:
            s1 = "{}R/{:.5f}s"
            logger.info(s1.format(r, t1 - t0))
        # limit the rate at which we make requests
        if t0 + throttle > t1:
            time.sleep(throttle + t0 - t1)

        if interval_checker + interval < t1:
            interval_checker = t1
            send_message(
                client.connection,
                "ReadFish Stats - accepted {:.2f}% of {} total reads. Unblocked {} reads.".format(
                    decisiontracker.fetch_proportion_accepted(),
                    decisiontracker.fetch_total_reads(),
                    decisiontracker.fetch_unblocks(),
                ),
                Severity.INFO,
            )

    else:
        send_message(client.connection, "ReadFish Client Stopped.", Severity.WARN)
        caller.disconnect()
        logger.info("Finished analysis of reads as client stopped.")


def main():
    sys.exit("This entry point is deprecated, please use 'readfish targets' instead")


def run(parser, args):
    if args.chunk_log is not None:
        chunk_log_exists = Path(args.chunk_log).is_file()
        chunk_logger = setup_logger("chunk_log", log_file=args.chunk_log)
        if not chunk_log_exists:
            chunk_logger.debug("\t".join(CHUNK_LOG_FIELDS))
    else:
        chunk_logger = logging.getLogger("chunk_log")
        chunk_logger.disabled = True

    if args.paf_log is not None:
        paf_logger = setup_logger("paf_log", log_file=args.paf_log)
    else:
        paf_logger = logging.getLogger("paf_log")
        paf_logger.disabled = True

    logger = setup_logger(
        __name__,
        log_format=args.log_format,
        log_file=args.log_file,
        level=logging.INFO,
    )
    if args.log_file is not None:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter(args.log_format))
        logger.addHandler(h)
    logger.info(" ".join(sys.argv))
    print_args(args, logger=logger)

    # Parse configuration TOML
    # TODO: num_channels is not configurable here, should be inferred from client
    run_info, conditions, reference, caller_kwargs = get_run_info(
        args.toml, num_channels=512
    )
    live_toml = Path("{}_live".format(args.toml))

    # Load Minimap2 index
    logger.info("Initialising minimap2 mapper")
    mapper = CustomMapper(reference)
    logger.info("Mapper initialised")

    position = get_device(args.device, host=args.host)

    read_until_client = RUClient(
        mk_host=position.host,
        mk_port=position.description.rpc_ports.insecure,
        filter_strands=True,
        cache_type=AccumulatingCache,
    )

    send_message(
        read_until_client.connection,
        "ReadFish is controlling sequencing on this device. You use it at your own risk.",
        Severity.WARN,
    )

    for message, sev in describe_experiment(conditions, mapper):
        logger.info(message)

        send_message(
            read_until_client.connection,
            message,
            sev,
        )

    """
    This experiment has N regions on the flowcell.

    using reference: /path/to/ref.mmi

    Region i:NAME (control=bool) has X targets of which Y are found in the reference.
    reads will be unblocked when [u,v], sequenced when [w,x] and polled for more data when [y,z].
    """

    # FIXME: currently flowcell size is not included, this should be pulled from
    #  the read_until_client

    read_until_client.run(
        first_channel=args.channels[0],
        last_channel=args.channels[-1],
    )

    try:
        simple_analysis(
            read_until_client,
            unblock_duration=args.unblock_duration,
            throttle=args.throttle,
            batch_size=args.batch_size,
            cl=chunk_logger,
            pf=paf_logger,
            live_toml_path=live_toml,
            dry_run=args.dry_run,
            run_info=run_info,
            conditions=conditions,
            mapper=mapper,
            caller_kwargs=caller_kwargs,
        )
    except KeyboardInterrupt:
        pass
    finally:
        read_until_client.reset()

    # No results returned
    send_message(
        read_until_client.connection,
        "ReadFish is disconnected from this device. Sequencing will proceed normally.",
        Severity.WARN,
    )


if __name__ == "__main__":
    main()
