"""unblock_all.py

ReadUntil implementation that will only unblock reads. This should result in
a read length histogram that has very short peaks (~280-580bp) as these are the
smallest chunks that we can acquire. If you are not seeing these peaks, the
`split_reads_after_seconds` parameter in the configuration file may need to be
edited to 0.2-0.4:
(<MinKNOW_folder>/ont-python/lib/python2.7/site-packages/bream4/configuration)
"""
# Core imports
import concurrent.futures
import functools
import logging
import sys
import time
import traceback
from collections import defaultdict, deque, Counter
from multiprocessing import TimeoutError
from multiprocessing.pool import ThreadPool
from pathlib import Path
from timeit import default_timer as timer

# Third party imports
import read_until_api_v2 as read_until
import toml

from ru.arguments import get_parser, BASE_ARGS
from ru.basecall import Mapper as CustomMapper
from ru.basecall import GuppyCaller as Caller
from ru.utils import print_args, get_run_info, between, setup_logger, describe_experiment
from ru.utils import send_message, Severity


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
            default="paflog.log",
        )
    ),
    (
        "--chunk-log",
        dict(
            help="Chunk log",
            default="chunk_log.log",
        )
    ),
)

class ThreadPoolExecutorStackTraced(concurrent.futures.ThreadPoolExecutor):
    """ThreadPoolExecutor records only the text of an exception,
    this class will give back a bit more."""

    def submit(self, fn, *args, **kwargs):
        """Submits the wrapped function instead of `fn`"""
        return super(ThreadPoolExecutorStackTraced, self).submit(
            self._function_wrapper, fn, *args, **kwargs
        )

    def _function_wrapper(self, fn, *args, **kwargs):
        """Wraps `fn` in order to preserve the traceback of any kind of
        raised exception

        """
        try:
            return fn(*args, **kwargs)
        except Exception:
            raise sys.exc_info()[0](traceback.format_exc())


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
    d = {"conditions": {str(v): {"channels": [], "name": conditions[v].name} for k, v in run_info.items()}}
    for k, v in run_info.items():
        d["conditions"][str(v)]["channels"].append(k)

    channels_out = str(client.mk_run_dir / "channels.toml")
    with open(channels_out, "w") as fh:
        fh.write("# This file is written as a record of the condition each channel is assigned.\n")
        fh.write("# It may be changed or overwritten if you restart ReadFish.\n")
        fh.write("# In the future this file may become a CSV file.\n")
        toml.dump(d, fh)

    caller = Caller(**caller_kwargs)
    # What if there is no reference or an empty MMI

    # DefaultDict[int: collections.deque[Tuple[str, ndarray]]]
    #  tuple is (read_id, previous_signal)
    # TODO: tuple should use read_number instead
    previous_signal = defaultdict(functools.partial(deque, maxlen=1))
    # count how often a read is seen
    tracker = defaultdict(Counter)
    # decided
    decided_reads = {}
    strand_converter = {1: "+", -1: "-"}

    read_id = ""

    # TODO: partial-ise / lambda unblock to take the unblock duration
    if dry_run:
        decision_dict = {
            "stop_receiving": client.stop_receiving_read,
            "proceed": None,
            "unblock": client.stop_receiving_read,
        }
        send_message(client.connection,"This is a test run. No unblocks will occur.",Severity.WARN)
    else:
        decision_dict = {
            "stop_receiving": client.stop_receiving_read,
            "proceed": None,
            "unblock": lambda c, n: client.unblock_read(c, n, unblock_duration, read_id),
        }
        send_message(client.connection, "This is a live run. Unblocks will occur.", Severity.WARN)
    decision_str = ""
    below_threshold = False
    exceeded_threshold = False

    l_string = (
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
    cl.debug("\t".join(l_string))
    l_string = "\t".join(("{}" for _ in l_string))
    loop_counter = 0
    while client.is_running:
        if live_toml_path.is_file():
            # Reload the TOML config from the *_live file
            run_info, conditions, new_reference, _ = get_run_info(live_toml_path, flowcell_size)

            # Check the reference path if different from the loaded mapper
            if new_reference != mapper.index:
                old_reference = mapper.index
                # Log to file and MinKNOW interface
                logger.info("Reloading mapper")
                send_message(client.connection, "Reloading mapper. ReadFish paused.", Severity.INFO)

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

        for read_info, read_id, seq_len, results in mapper.map_reads_2(
                caller.basecall_minknow(
                    reads=client.get_read_chunks(batch_size=batch_size, last=True),
                    signal_dtype=client.signal_dtype,
                    prev_signal=previous_signal,
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
                client.stop_receiving_read(channel, read_number)
                continue

            # This is an analysis channel
            # Below minimum chunks
            if tracker[channel][read_number] <= conditions[run_info[channel]].min_chunks:
                below_threshold = True

            # Greater than or equal to maximum chunks
            if tracker[channel][read_number] >= conditions[run_info[channel]].max_chunks:
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
                client.unblock_read(channel, read_number, unblock_duration, read_id)

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
                client.unblock_read(channel, read_number, unblock_duration, read_id)

            # proceed returns None, so we send no decision; otherwise unblock or stop_receiving
            elif decision is not None:
                decided_reads[channel] = read_id
                decision(channel, read_number)

            log_decision()

        t1 = timer()
        if r > 0:
            s1 = "{}R/{:.5f}s"
            logger.info(s1.format(r, t1 - t0))
        # limit the rate at which we make requests
        if t0 + throttle > t1:
            time.sleep(throttle + t0 - t1)
    else:
        send_message(client.connection, "ReadFish Client Stopped.", Severity.WARN)
        caller.disconnect()
        logger.info("Finished analysis of reads as client stopped.")


def run_workflow(client, analysis_worker, n_workers, run_time, runner_kwargs=None):
    """Run an analysis function against a ReadUntilClient

    Parameters
    ----------
    client : read_until.ReadUntilClient
        An instance of the ReadUntilClient object
    analysis_worker : partial function
        Analysis function to process reads, should exit when client.is_running == False
    n_workers : int
        Number of analysis worker functions to run
    run_time : int
        Time, in seconds, to run the analysis for
    runner_kwargs : dict
        Keyword arguments to pass to client.run()

    Returns
    -------
    list
        Results from the analysis function, one item per worker

    """
    if runner_kwargs is None:
        runner_kwargs = dict()

    logger = logging.getLogger("Manager")

    results = []
    pool = ThreadPool(n_workers)
    logger.info("Creating {} workers".format(n_workers))
    try:
        # start the client
        client.run(**runner_kwargs)
        # start a pool of workers
        for _ in range(n_workers):
            results.append(pool.apply_async(analysis_worker))
        pool.close()
        # wait a bit before closing down
        time.sleep(run_time)
        logger.info("Sending reset")
        client.reset()
        pool.join()
    except KeyboardInterrupt:
        logger.info("Caught ctrl-c, terminating workflow.")
        client.reset()
    except Exception as e:
        logger.exception("Got exception", exc_info=e)
        client.reset()
        raise

    # collect results (if any)
    collected = []
    for result in results:
        try:
            res = result.get(3)
        except TimeoutError:
            logger.warning("Worker function did not exit successfully.")
            # collected.append(None)
        except Exception as e:
            logger.exception("EXCEPT", exc_info=e)
            # logger.warning("Worker raise exception: {}".format(repr(e)))
        else:
            logger.info("Worker exited successfully.")
            collected.append(res)
    pool.terminate()
    return collected


def main():
    sys.exit(
        "This entry point is deprecated, please use 'readfish targets' instead"
    )


def run(parser, args):
    # set up logging to file for DEBUG messages and above
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(name)s %(message)s",
        filename=args.log_file,
        filemode="w",
    )

    # define a Handler that writes INFO messages or higher to the sys.stderr
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)

    # set a format which is simpler for console use
    formatter = logging.Formatter(args.log_format)
    console.setFormatter(formatter)

    # add the handler to the root logger
    logging.getLogger("").addHandler(console)

    # Start by logging sys.argv and the parameters used
    logger = logging.getLogger("Manager")
    logger.info(" ".join(sys.argv))
    print_args(args, logger=logger)

    # Setup chunk and paf logs
    chunk_logger = setup_logger("DEC", log_file=args.chunk_log)
    paf_logger = setup_logger("PAF", log_file=args.paf_log)

    # Parse configuration TOML
    # TODO: num_channels is not configurable here, should be inferred from client
    run_info, conditions, reference, caller_kwargs = get_run_info(args.toml, num_channels=512)
    live_toml = Path("{}_live".format(args.toml))

    # Load Minimap2 index
    logger.info("Initialising minimap2 mapper")
    mapper = CustomMapper(reference)
    logger.info("Mapper initialised")

    read_until_client = read_until.ReadUntilClient(
        mk_host=args.host,
        mk_port=args.port,
        device=args.device,
        # one_chunk=args.one_chunk,
        filter_strands=True,
        # TODO: test cache_type by passing a function here
        cache_type=args.read_cache,
        cache_size=args.cache_size,
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
    analysis_worker = functools.partial(
        simple_analysis,
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

    results = run_workflow(
        read_until_client,
        analysis_worker,
        args.workers,
        args.run_time,
        runner_kwargs={
            # "min_chunk_size": args.min_chunk_size,
            "first_channel": min(args.channels),
            "last_channel": max(args.channels),
        },
    )

    # No results returned
    send_message(
        read_until_client.connection,
        "ReadFish is disconnected from this device. Sequencing will proceed normally.",
        Severity.WARN,
    )


if __name__ == "__main__":
    main()
