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
from pathlib import Path
import time
from timeit import default_timer as timer
import traceback
from multiprocessing import TimeoutError
from multiprocessing.pool import ThreadPool
from collections import defaultdict, deque, Counter

# Pypi imports
import toml

# Read Until imports
import read_until_api_v2 as read_until
from ru.basecall import PerpetualCaller as Caller
from ru.basecall import Mapper as CustomMapper
from ru.arguments import get_parser
from ru.utils import print_args, get_run_info, between, setup_logger


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
    chunk_log=None,
    toml_path=None,
    flowcell_size=512,
    dry_run=False,
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
    chunk_log : str
        Log file to log chunk data to
    toml_path : str
        Path to a TOML configuration file for read until
    flowcell_size : int
        The number of channels on the flowcell, 512 for MinION and 3000 for PromethION
    dry_run : bool
        If True unblocks are replaced with `stop_receiving` commands

    Returns
    -------
    None
    """
    logger = logging.getLogger(__name__)
    toml_dict = toml.load(toml_path)
    live_file = Path("{}_live".format(toml_path))
    if live_file.is_file():
        live_file.unlink()

    # There may or may not be a reference
    run_info, conditions, reference = get_run_info(toml_dict, num_channels=flowcell_size)


    guppy_kwargs = toml_dict.get(
        "guppy_connection",
        {
            "config": "dna_r9.4.1_450bps_fast",
            "host": "127.0.0.1",
            "port": 5555,
            "procs": 4,
            "inflight": 512,
        }
    )

    caller = Caller(**guppy_kwargs)
    #What if there is no reference or an empty MMI
    mapper = CustomMapper(reference)

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
    else:
        decision_dict = {
            "stop_receiving": client.stop_receiving_read,
            "proceed": None,
            "unblock": lambda c, n: client.unblock_read(c, n, unblock_duration, read_id),
        }
    decision_str = ""
    below_threshold = False
    exceeded_threshold = False

    cl = setup_logger("DEC", log_file=chunk_log)
    pf = setup_logger("PAF", log_file="paflog.paf")
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
        if live_file.is_file():
            # We may want to update the reference under certain conditions here.
            run_info, conditions, new_reference = get_run_info(live_file, flowcell_size)
            if new_reference != reference:
                logger.info("Reloading mapper")
                #We need to update our mapper client.
                mapper = CustomMapper(new_reference)
                logger.info("Reloaded mapper")
                logger.info("Deleting old mmi {}".format(reference))
                #We now delete the old mmi file.
                Path(reference).unlink()
                logger.info("Old mmi deleted.")

        # TODO: Fix the logging to just one of the two in use

        if not reference:
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
        s1 = "Took {:.5f} to call and map {} reads"
        logger.info(s1.format(t1-t0, r))
        # limit the rate at which we make requests
        if t0 + throttle > t1:
            time.sleep(throttle + t0 - t1)
    else:
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
    extra_args = (
        (
            "--toml",
            dict(
                metavar="TOML",
                required=True,
                help="TOML file specifying experimental parameters",
            ),
        ),
        (
            "--chunk-log",
            dict(
                help="Chunk log",
                default="chunk_log.log",
            )
        ),
    )
    parser, args = get_parser(extra_args=extra_args, file=__file__)

    # TODO: Move logging config to separate configuration file
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

    read_until_client = read_until.ReadUntilClient(
        mk_host=args.host,
        mk_port=args.port,
        device=args.device,
        one_chunk=args.one_chunk,
        filter_strands=True,
        # TODO: test cache_type by passing a function here
        cache_type=args.read_cache,
        cache_size=args.cache_size,
    )

    analysis_worker = functools.partial(
        simple_analysis,
        read_until_client,
        unblock_duration=args.unblock_duration,
        throttle=args.throttle,
        batch_size=args.batch_size,
        chunk_log=args.chunk_log,
        toml_path=args.toml,
        dry_run=args.dry_run,
    )

    results = run_workflow(
        read_until_client,
        analysis_worker,
        args.workers,
        args.run_time,
        runner_kwargs={
            "min_chunk_size": args.min_chunk_size,
            "first_channel": min(args.channels),
            "last_channel": max(args.channels),
        },
    )
    # describe(results)
    # No results returned


if __name__ == "__main__":
    main()
