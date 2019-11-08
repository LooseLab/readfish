"""unblock_all.py

ReadUntil implementation that will only unblock reads. This should result in
a read length histogram that has very short peaks (~280-580bp) as these are the
smallest chunks that we can acquire. If you are not seeing these peaks, the
`split_reads_after_seconds` parameter in the configuration file may need to be
edited to 0.2-0.4:
(<MinKNOW_folder>/ont-python/lib/python2.7/site-packages/bream4/configuration)
"""
# Core imports
import functools
import logging
import sys
import time
from timeit import default_timer as timer
from collections import defaultdict, deque

# Read Until imports
import read_until_api_v2 as read_until
from read_until_api_v2.utils import run_workflow
from ru.arguments import get_parser
from ru.basecall import PerpetualCaller as Caller
from ru.utils import print_args, setup_logger


def simple_analysis(client, batch_size=512, throttle=0.1, unblock_duration=0.1):
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

    Returns
    -------
    None
    """
    logger = logging.getLogger(__name__)
    guppy_kwargs = {
            "config": "dna_r9.4.1_450bps_hac",
            "host": "10.157.252.19",
            "port": 5555,
            "procs": 4,
            "inflight": 512,
        }

    caller = Caller(**guppy_kwargs)
    previous_signal = defaultdict(functools.partial(deque, maxlen=1))
    decided_reads = {}
    while client.is_running:
        r = 0
        t0 = timer()

        for r, (read_info, read_id, seq, seq_len, qual) in enumerate(caller.basecall_minknow(
            reads=client.get_read_chunks(batch_size=batch_size, last=True),
            signal_dtype=client.signal_dtype,
            prev_signal=previous_signal,
            decided_reads=decided_reads,
        ), start=1):
            channel, read_number = read_info
            # pass
            client.unblock_read(channel, read_number, read_id=read_id, duration=unblock_duration)
            client.stop_receiving_read(channel, read_number)
            logger.info("meta.seqlen: {:,}, len(seq): {:,}".format(seq_len, len(seq)))

        t1 = timer()
        if r:
            logger.info("Took {:.6f} for {} reads".format(t1-t0, r))
        # limit the rate at which we make requests
        if t0 + throttle > t1:
            time.sleep(throttle + t0 - t1)
    else:
        caller.disconnect()
        logger.info("Finished analysis of reads as client stopped.")


def main():
    parser, args = get_parser(file=__file__)

    # TODO: Move logging config to separate configuration file
    # TODO: use setup_logger here instead?
    # set up logging to file for DEBUG messages and above
    logging.basicConfig(
        level=logging.DEBUG,
        # TODO: args.log_format
        format="%(levelname)s %(asctime)s %(name)s %(message)s",
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
    # logger = setup_logger(__name__, args.log_format, log_file=args.log_file, level=logging.INFO)
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
        client=read_until_client,
        batch_size=args.batch_size,
        throttle=args.throttle,
        unblock_duration=args.unblock_duration,
    )

    results = run_workflow(
        client=read_until_client,
        partial_analysis_func=analysis_worker,
        n_workers=args.workers,
        run_time=args.run_time,
        runner_kwargs={
            "min_chunk_size": args.min_chunk_size,
            "first_channel": args.channels[0],
            "last_channel": args.channels[-1],
        },
    )
    # No results returned


if __name__ == "__main__":
    main()
