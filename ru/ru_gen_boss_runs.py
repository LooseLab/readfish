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
import numpy as np

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
    query_array,
)
from ru.utils import send_message, Severity, get_device, DecisionTracker

print("v0.0.3_BR")

_help = "Run dynamic selective sequencing."
_cli = BASE_ARGS + (
    (
        "--toml",
        dict(
            metavar="TOML",
            required=True,
            help="TOML file specifying experimental parameters",
        ),
    ),
    ("--paf-log", dict(help="PAF log", default=None,),),
    ("--chunk-log", dict(help="Chunk log", default=None,),),
    ("--mask", dict(help="Path to BOSS-RUNS produced masks",),),
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


def init_BR_bits(conditions):
    """
    initialise the bits of code needed for BR

    Parameters
    ----------
    conditions : list
        Experimental conditions as List of namedtuples.

    Returns
    -------
    bool


    """
    # Overwrite the default strand_converter
    # used to index into the strategies,
    # which are shaped 2xN for forward & reverse in 1st dim
    strand_converter_br = {1: False, -1: True}

    # grab path to masks and contigs, requires presence of 1 BR cond in toml
    mask_path = Path([getattr(cond, "mask", False) for cond in conditions if getattr(cond, "mask", False)][0])
    contigs_path = Path([getattr(cond, "contigs", False) for cond in conditions if getattr(cond, "contigs", False)][0])
    masks = {}
    return strand_converter_br, mask_path, contigs_path, masks



def reload_masks(mask_path, masks, logger):
    """
    Reload updated decision masks. Only load if the marker file exists
    Loads all present .npy files and deletes the marker file

    Parameters
    ----------
    mask_path: pathlib.Path
        path to the directory where new masks are placed
    masks: dict
        dict of {contig name: mask array}

    Returns
    -------
    masks: dict
        dict of {contig name: mask array}
    """
    if not (mask_path / "masks.updated").exists():
        return masks

    def reload_npy(mask_files):
        masks = {path.stem: np.load(path) for path in mask_files}
        return masks

    def reload_npz(mask_files):
        mask_container = np.load(mask_files[0])
        masks = {name: mask_container[name] for name in mask_container}
        return masks

    # can use multiple .npy or a single .npz file
    # BR uses .npy for the moment
    new_masks = list(mask_path.glob("*.npy"))
    if new_masks:
        reload_func = reload_npy
    elif not new_masks:
        new_masks = list(mask_path.glob("*.npz"))
        reload_func = reload_npz
    else:
        reload_func = False
        logger.info("Expected either .npy or .npz file but found neither")

    try:
        masks = reload_func(mask_files=new_masks)
        logger.info(f"Reloaded mask dict for {masks.keys()}")
    except Exception as e:
        logger.error(f"Error reading mask array ->>> {repr(e)}")
        masks = {"exception": True}
    (mask_path / "masks.updated").unlink()
    return masks



def reload_mapper(contigs_path, mapper, logger):
    """
    Reload mapping index for decision making. Only load if marker file exists.

    Parameters
    ----------
    contigs_path: pathlib.Path
        path to directory where the index file sits
    mapper: CustomMapper
        mapper object that gets replaced with new index

    Returns
    -------
    mapper: mappy.Aligner
        mapper object that gets replaced with new index
    """
    # if dynamic contigs are not used
    if not contigs_path:
        return mapper
    # if contigs were not updated since last time
    if not (contigs_path / "contigs.updated").exists():
        return mapper

    try:
        contigs_mmi = [path for path in contigs_path.glob("*.mmi")][0]
        logger.info(f"Reloading mapping index")
        mapper = CustomMapper(str(contigs_mmi))
        # wait until init is complete
        while not mapper.initialised:
            time.sleep(1)

    except Exception as e:
        logger.error(f"Error loading mapping index ->>> {repr(e)}")
    (contigs_path / "contigs.updated").unlink()
    return mapper



def check_names(masks, mapper, logger):
    """
    Check that the names of masks and sequences in the mapper are the same.

    Parameters
    ----------
    mapper: mappy.Aligner
        mapper object that gets replaced with new index
    masks: dict
        dict of {contig name: mask array}

    Returns
    -------

    """
    if not mapper.initialised:
        return
    mask_names = sorted(list(masks.keys()))
    contig_names = sorted(list(mapper.mapper.seq_names))
    same_names = mask_names == contig_names
    if not same_names:
        logger.error(f"Error loading masks and contigs: discrepancy in names \n {mask_names} \n {contig_names}")




def write_out_channels_toml(conditions, run_info, client):
    """
    Write out the channels toml file

    Parameters
    ----------
    conditions : list of collections.namedtuple
        Experimental conditions as List of namedtuples.
    run_info : dict
        Dictionary of {channel: index} where index corresponds to an index in `conditions`

    client: read_until.ReadUntilClient
        An instance of the ReadUntilClient object

    Returns
    -------

    """
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


def decision_boss_runs(
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
    if live_toml_path:
        live_toml_path = Path(live_toml_path)
        if live_toml_path.is_file():
            live_toml_path.unlink()
    write_out_channels_toml(conditions, run_info, client)

    if caller_kwargs["host"].startswith("ipc"):
        guppy_address = "{}/{}".format(caller_kwargs["host"], caller_kwargs["port"])
    else:
        guppy_address = "{}:{}".format(caller_kwargs["host"], caller_kwargs["port"])

    caller = Caller(
        address=guppy_address,
        config=caller_kwargs["config_name"],
    )
    # What if there is no reference or an empty MMI

    decision_tracker = DecisionTracker()

    # DefaultDict[int: collections.deque[Tuple[str, ndarray]]]
    #  tuple is (read_id, previous_signal)
    # TODO: tuple should use read_number instead
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

    # BR: initialise parts needed for dynamic decisions
    strand_converter_br, mask_path, contigs_path, masks = init_BR_bits(conditions)

    while client.is_running:
        if not client.is_phase_sequencing:
            time.sleep(5)
            continue
        # todo reverse engineer from channels.toml
        # if live_toml_path.is_file():
        #     # Reload the TOML config from the *_live file
        #     run_info, conditions, new_reference, _ = get_run_info(
        #         live_toml_path, flowcell_size, validate=False  # BR: don't validate toml (due to mask param)
        #     )
        #
        #     # Check the reference path if different from the loaded mapper
        #     if new_reference != mapper.index:
        #         old_reference = mapper.index
        #         # Log to file and MinKNOW interface
        #         logger.info("Reloading mapper")
        #         send_message(
        #             client.connection,
        #             "Reloading mapper. ReadFish paused.",
        #             Severity.INFO,
        #         )
        #
        #         # Update mapper client.
        #         mapper = CustomMapper(new_reference)
        #         # Log on success
        #         logger.info("Reloaded mapper")
        #
        #         # If we've reloaded a reference, delete the previous one
        #         if old_reference:
        #             logger.info("Deleting old mmi {}".format(old_reference))
        #             # We now delete the old mmi file.
        #             Path(old_reference).unlink()
        #             logger.info("Old mmi deleted.")

        # TODO: Fix the logging to just one of the two in use

        # BR: load updated decision masks and contigs
        masks = reload_masks(mask_path=mask_path, masks=masks, logger=logger)
        mapper = reload_mapper(contigs_path=contigs_path, mapper=mapper, logger=logger)
        check_names(masks=masks, mapper=mapper, logger=logger)


        if not mapper.initialised:
            time.sleep(throttle)
            continue

        loop_counter += 1
        t0 = timer()
        r = 0
        unblock_batch_action_list = []
        stop_receiving_action_list = []




        for read_info, read_id, seq_len, mappings in mapper.map_reads_2(
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
            if not mappings:
                mode = "no_map"

            hits = set()
            for result in mappings:
                pf.debug("{}\t{}\t{}".format(read_id, seq_len, result))
                hits.add(result.ctg)

            if hits & conditions[run_info[channel]].targets:
                # Mappings and targets overlap
                coord_match = any(
                    between(r.r_st, c)
                    for r in mappings
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


            # BR: this is where the decisions are getting checked in the masks
            # the function to query the masks query_array() lives in utils.py
            elif hits and conditions[run_info[channel]].mask:
                coord_match = any(
                    [
                        query_array(
                            start_pos=mapping.r_st,
                            mask_dict=masks,
                            reverse=strand_converter_br.get(mapping.strand, False),
                            contig=mapping.ctg,
                            logger=logger
                        )
                        for mapping in mappings
                    ]
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
                        mode = "multi_off"  ##

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
                decision_tracker.event_seen(mode)
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
                decision_tracker.event_seen(decision_str)

            # proceed returns None, so we send no decision; otherwise unblock or stop_receiving
            elif decision is not None:
                decided_reads[channel] = read_id
                decision(channel, read_number)
                decision_tracker.event_seen(decision_str)

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
                    decision_tracker.fetch_proportion_accepted(),
                    decision_tracker.fetch_total_reads(),
                    decision_tracker.fetch_unblocks(),
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
        args.toml, num_channels=512, validate=False  # BR: no toml validation
    )
    live_toml = Path("{}_live".format(args.toml))

    # Load Minimap2 index
    logger.info("Initialising minimap2 mapper")
    mapper = CustomMapper(reference)
    logger.info("Mapper initialised")

    position = get_device(args.device, host=args.host, port=args.port)

    read_until_client = RUClient(
        mk_host=position.host,
        mk_port=position.description.rpc_ports.secure,
        filter_strands=True,
        cache_type=AccumulatingCache,
    )
    # todo reverse engineer from channels.toml

    send_message(
        read_until_client.connection,
        "ReadFish is controlling sequencing on this device. You use it at your own risk.",
        Severity.WARN,
    )

    for message, sev in describe_experiment(conditions, mapper):
        logger.info(message)

        send_message(
            read_until_client.connection, message, sev,
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
        first_channel=args.channels[0], last_channel=args.channels[-1],
    )

    try:
        decision_boss_runs(
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
