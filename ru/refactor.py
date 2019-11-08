"""alex.py

A ReadUntil script that interacts with MinKNOW, basecalling with pyguppy,
and mapping using mappy (minimap2).
"""
# Core imports
import concurrent.futures
import functools
import logging
from multiprocessing.pool import ThreadPool
from multiprocessing import TimeoutError
import sys
from pathlib import Path
import traceback
import time
from collections import Counter, defaultdict, deque

# Pypi imports
import numpy as np
import toml

# Pyguppy imports
from pyguppy.caller import PerpetualCaller as Caller
from pyguppy.callermapper import CustomMapper
from pyguppy.io import parse_read_until

# Read Until imports
import read_until
from read_until.utils import get_run_info, print_args, between
from read_until.arguments import get_parser


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
    toml_dict = toml.load(toml_path)
    live_file = Path("{}_live".format(toml_path))
    if live_file.is_file():
        live_file.unlink()
    run_info, conditions = get_run_info(toml_dict, num_channels=flowcell_size)
    reference = toml_dict["conditions"].get("reference")
    guppy_kwargs = toml_dict.get(
        "guppy_connection",
        {
            "config": "dna_r9.4.1_450bps_fast",
            "host": "127.0.0.1",
            "port": 5555,
            "procs": 4,
            "inflight": 512,
        },
    )

    logger = logging.getLogger(__name__)
    try:
        caller = Caller(**guppy_kwargs)
    except Exception as e:
        logging.error(e, exc_info=True)
        raise e

    channels_data = defaultdict(functools.partial(deque, maxlen=1))

    # defaultdict of deque, each with a tuple of (read_id, raw_signal)
    # TODO: check for conditions that may break this
    for i in range(min(run_info.keys()), max(run_info.keys()) + 1):
        channels_data[i].append(("noread", np.ndarray(0)))

    logger.info("Loading Mapper")
    Mapper = CustomMapper(reference)
    logger.info("Mapper loaded")

    # Initialise dictionary to keep track of how often we have seen a read.
    tracker = defaultdict(Counter)

    # Init DECISION log string and the header row
    log_string = "DECISION\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}"
    logger.debug(
        log_string.format(
            "read_id",
            "channel",
            "read_number",
            "counter",
            "mode",
            "decision",
            "condition",
            "min_threshold",
            "count_threshold",
            "timestamp",
        )
    )

    # Strand converter because mappy is going against the flow
    strand_converter = {1: "+", -1: "-"}
    # Holds partial/lambda functions that correspond to the RU decisions
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
            "unblock": lambda c, n: client.unblock_read(c, n, unblock_duration),
        }
    decision_str = ""
    below_threshold = False
    exceeded_threshold = False

    while client.is_running:
        if live_file.is_file():
            run_info, conditions = get_run_info(live_file, flowcell_size)
        # TODO: reference switcher goes here
        """
        if toml_dict["conditions"].get("switch_reference", False):
            logger.info("Reloading mapper")
            del Mapper  # May not be needed
            Mapper = CustomMapper(toml_dict["conditions"].get("reference"))
            logger.info("Reloaded mapper")
        """
        # Start time of this iteration
        t0 = time.time()

        # get the most recent read chunks from the client
        # FIXME: get read chunks can either be a generator or a list this needs
        #  to be unified so that single style of analysis can be used
        read_batch = client.get_read_chunks(batch_size=batch_size, last=True)
        t1 = time.time()
        # There are reads from MinKNOW
        if read_batch:
            # Create the read_map: read_id => (channel, read.number)
            # and create the tracker (Counter) to count how many times a chunk of a read is seen
            read_map = dict()
            for channel, read in read_batch:
                read_map[read.id] = (channel, read.number)
                if read.number not in tracker[channel].keys():
                    tracker[channel].clear()
                tracker[channel][read.number] += 1

            # Get pyguppy read objects from the read_batch
            reads = parse_read_until(read_batch, client, channels_data)

            t1 = time.time()
            basecall_list = caller.basecall_read_until(reads)

            for read_id, results in Mapper.map_reads(basecall_list):
                channel, read_number = read_map.pop(read_id)
                mode = ""
                exceeded_threshold = False
                below_threshold = False

                log_decision = lambda: logger.debug(
                    log_string.format(
                        read_id,
                        channel,
                        read_number,
                        tracker[channel][read_number],
                        mode,
                        getattr(conditions[run_info[channel]], mode, mode),
                        conditions[run_info[channel]].name,
                        below_threshold,
                        exceeded_threshold,
                        time.time(),
                    )
                )

                hits = set()

                # Control channels
                if conditions[run_info[channel]].control:
                    mode = "control"
                    log_decision()
                    client.stop_receiving_read(channel, read_number)
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
                    # Exceeded max chunks in this condition
                    exceeded_threshold = True

                # No mappings
                if not results:
                    mode = "no_map"

                # Log mappings
                for result in results:
                    logger.debug(
                        "PAFOUTPUT:{}\t{}\t{}\t{}".format(
                            read_id, channel, read_number, result
                        )
                    )
                    hits.add(result.ctg)

                if hits & conditions[run_info[channel]].targets:
                    # Mappings and targets overlap
                    # TODO: Check these modes, even with an on-target mapping (ctg)
                    #  we can still get an off-target classification
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
                            # Single match to contig outside coordinate range
                            mode = "single_off"
                    elif len(hits) > 1:
                        if coord_match:
                            # Multiple contig matches at least one in correct region
                            mode = "multi_on"
                        else:
                            # Multiple matches to target contigs outside coordinate range
                            mode = "multi_off"

                else:
                    # No matches in mappings
                    if len(hits) > 1:
                        # More than one, off-target, mapping
                        mode = "multi_off"
                    elif len(hits) == 1:
                        # Single off-target mapping
                        mode = "single_off"

                # This is where we make out decision:
                # Get the associated action for this condition
                decision_str = getattr(conditions[run_info[channel]], mode)
                # decision is an alias for the functions "unblock" or "stop_receiving"
                decision = decision_dict[decision_str]

                # If max_chunks has been exceeded AND we don't want to keep sequencing we unblock
                if exceeded_threshold and decision_str != "stop_receiving":
                    mode = "exceeded_max_chunks_unblocked"
                    client.unblock_read(channel, read_number, unblock_duration)

                # TODO: WHAT IS GOING ON?!
                # If under min_chunks AND any mapping mode seen we unblock
                # if below_threshold and mode in {"single_off", "multi_off"}:
                if below_threshold and mode in {
                    "single_on",
                    "single_off",
                    "multi_on",
                    "multi_off",
                }:
                    mode = "below_min_chunks_unblocked"
                    client.unblock_read(channel, read_number, unblock_duration)

                # proceed returns None, so we send no decision; otherwise unblock or stop_receiving
                elif decision is not None:
                    decision(channel, read_number)

                log_decision()

            logger.info("{} reads in read_map".format(len(read_map.keys())))

            # Here we catch reads that didn't map
            # log_decision may be called before it is assigned???
            for read_id, (channel, read_number) in read_map.items():
                # Control channels
                if conditions[run_info[channel]].control:
                    mode = "control"
                    log_decision()
                    client.stop_receiving_read(channel, read_number)
                    continue
                # TODO: these may have sequence, so no_map is better? CHECK!
                mode = "no_seq"
                exceeded_threshold = False
                if (
                    tracker[channel][read_number]
                    >= conditions[run_info[channel]].max_chunks
                ):
                    client.unblock_read(channel, read_number, unblock_duration)
                    mode = "exceeded_max_chunks"
                    exceeded_threshold = True
                log_decision()

            t2 = time.time()
            s1 = "Took {:.5f} to call and map {} reads with {} basecalls"
            logger.info(s1.format((t2 - t1), len(read_batch), len(basecall_list)))

        # No reads received from MinKNOW
        else:
            # limit the rate at which we make requests
            t1 = time.time()
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
            collected.append(None)
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
    )
    parser, args = get_parser(extra_args=extra_args, file=__file__)

    # TODO: Move logging config to separate configuration file
    # set up logging to file for DEBUG messages and above
    logging.basicConfig(
        level=logging.DEBUG, format=args.log_format, filename=args.log_file, filemode="w"
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
        device=args.device,
        one_chunk=args.one_chunk,
        filter_strands=True,
        cache_size=args.cache_size,
    )

    analysis_worker = functools.partial(
        simple_analysis,
        read_until_client,
        unblock_duration=args.unblock_duration,
        toml_path=args.toml,
        flowcell_size=args.channels[-1],
        dry_run=args.dry_run,
    )

    results = run_workflow(
        read_until_client,
        analysis_worker,
        args.workers,
        args.run_time,
        runner_kwargs={
            "min_chunk_size": args.min_chunk_size,
            "first_channel": args.channels[0],
            "last_channel": args.channels[-1],
        },
    )
    # No results returned
