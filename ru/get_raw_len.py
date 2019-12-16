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
from timeit import default_timer as timer
import traceback
from multiprocessing import TimeoutError
from multiprocessing.pool import ThreadPool
from collections import defaultdict, deque, Counter

# Pypi imports
import toml
import numpy as np

# Read Until imports
import read_until
from read_until.arguments import get_parser
from read_until.utils import print_args


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


def setup_logger(name, log_file, level=logging.DEBUG):
    """Function setup as many loggers as you want"""
    formatter = logging.Formatter("%(message)s")
    handler = logging.FileHandler(log_file, mode="w")
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)

    return logger


from uuid import uuid4
from fast5_research import Fast5
def rpc_to_fast5(channel, read, dtype):
    """
    ['ByteSize', 'Clear', 'ClearExtension', 'ClearField', 'CopyFrom', 'DESCRIPTOR',
     'DiscardUnknownFields', 'Extensions', 'FindInitializationErrors', 'FromString',
     'HasExtension', 'HasField', 'IsInitialized', 'ListFields', 'MergeFrom',
     'MergeFromString', 'ParseFromString', 'RegisterExtension', 'SerializePartialToString',
     'SerializeToString', 'SetInParent', 'UnknownFields', 'WhichOneof',
     '_CheckCalledFromGeneratedFile', '_SetListener', '__class__', '__deepcopy__',
     '__delattr__', '__dir__', '__doc__', '__eq__', '__format__', '__ge__', '__getattribute__',
     '__getstate__', '__gt__', '__hash__', '__init__', '__init_subclass__', '__le__', '__lt__',
     '__module__', '__ne__', '__new__', '__reduce__', '__reduce_ex__', '__repr__', '__setattr__',
     '__setstate__', '__sizeof__', '__slots__', '__str__', '__subclasshook__', '__unicode__',
     '_extensions_by_name', '_extensions_by_number', 'chunk_classifications', 'chunk_length',
     'chunk_start_sample', 'id', 'median', 'median_before', 'number', 'raw_data', 'start_sample']

    Parameters
    ----------
    channel
    read

    Returns
    -------

    """
    filename = f"{read.id}.fast5"
    # mean, stdv, n = 40.0, 2.0, 10000
    # raw_data = np.random.laplace(mean, stdv / np.sqrt(2), int(n))
    raw_data = np.frombuffer(read.raw_data, dtype=dtype)

    # example of how to digitize data
    start, stop = int(min(raw_data - 1)), int(max(raw_data + 1))
    rng = stop - start
    digitisation = 8192.0
    bins = np.arange(start, stop, rng / digitisation)

    # np.int16 is required, the library will refuse to write anything other
    raw_data = np.digitize(raw_data, bins).astype(np.int16)

    # The following are required meta data
    channel_id = {
        'digitisation': digitisation,
        'offset': 0,
        'range': rng,
        'sampling_rate': 4000,
        'channel_number': channel,
    }
    read_id = {
        'start_time': 0,
        'duration': len(raw_data),
        'read_number': read.number,
        'start_mux': 1,
        'read_id': str(uuid4()),
        'scaling_used': 1,
        'median_before': read.median_before,
    }
    tracking_id = {
        'exp_start_time': '1970-01-01T00:00:00Z',
        'run_id': str(uuid4()).replace('-', ''),
        'flow_cell_id': 'FAH00000',
    }
    context_tags = {}

    with Fast5.New(filename, 'w', tracking_id=tracking_id, context_tags=context_tags, channel_id=channel_id) as h:
        h.set_raw(raw_data, meta=read_id, read_number=1)
    return True


def simple_analysis(
    client, batch_size=512, throttle=0.1, unblock_duration=0.5, chunk_log=None, paf_log=None, toml_path=None, log_level="INFO"
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
    paf_log : str
        Log file to log paf data to
    log_level: str
        Default log level

    Returns
    -------
    None
    """
    display = True
    t = toml.load(toml_path)
    logger = logging.getLogger(__name__)

    # DefaultDict[int: collections.deque[Tuple[str, ndarray]]]
    #  tuple is (read_id, previous_signal)
    # TODO: tuple could use read_number instead
    previous_signal = defaultdict(functools.partial(deque, maxlen=1))
    # count how often a read is seen
    tracker = defaultdict(Counter)
    # decided
    decided_reads = {}


    cl = setup_logger("DEC", chunk_log,level=logging.INFO)
    pf = setup_logger("PAF", paf_log,level=logging.INFO)
    l_string = (
        "client_iteration",
        "read_in_loop",
        "read_id",
        "channel",
        "read_number",
        "raw_len",
        "estimated_bases",
        "start_analysis",
        "end_analysis",
        "timestamp",
    )
    cl.debug("\t".join(l_string))
    l_string = "\t".join(("{}" for _ in l_string))

    tracker = defaultdict(Counter)

    longestreads = dict()

    loop_counter = 0
    r = 0
    readcounter = 0
    while client.is_running:
        logger.info(f"Client is running {loop_counter}")
        loop_counter += 1
        t0 = timer()

        for r, (channel, read) in enumerate(
                client.get_read_chunks(batch_size=batch_size, last=True),
                start=1
        ):
            logger.info("got reads")
            read_start_time = timer()
            if read.number not in tracker[channel]:
                tracker[channel].clear()
            tracker[channel][read.number] += 1

            old_read_id, old_signal = previous_signal.get(channel, (("", np.empty(0, dtype=client.signal_dtype)),))[0]
            x = np.frombuffer(read.raw_data, dtype=client.signal_dtype)
            logger.info(client.signal_dtype)
            logger.info("{} {}".format(type(old_signal), len(old_signal)))
            logger.info("{} {}".format(type(x), len(x)))
            if old_read_id == read.id:
                signal = np.concatenate((old_signal, x,))
            else:
                signal = x

            previous_signal[channel].append((read.id, signal))

            cl.debug(
                l_string.format(
                    loop_counter,
                    r,
                    read.id,
                    channel,
                    read.number,
                    len(signal),
                    len(signal) / 450,
                    read_start_time,
                    timer(),
                    time.time(),
                    )
            )
            # print(dir(read))
            if not rpc_to_fast5(channel, read, signal.dtype):
                logger.info("💣")
            break
        # break

        t1 = timer()
        # logger.info("Took {} for {} reads".format(t1 - t0, r))
        # limit the rate at which we make requests
        if t0 + throttle > t1:
            time.sleep(throttle + t0 - t1)
    else:
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
            res = result.get(5)
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
            "--chunk-log",
            dict(
                help="Chunk log",
                default="chunk_log.log",
            )
        ),
        (
            "--paf-log",
            dict(
                help="PAF log file",
                default="paf_output_log.paf",
            )
        ),
        (
            "--toml",
            dict(
                metavar="TOML",
                required=True,
                help="TOML file specifying experimental parameters. Here we only "
                     "use `guppy_connection` and the `reference` location.",
            ),
        ),
    )
    parser, args = get_parser(extra_args=extra_args, file=__file__)

    print (args)


    # TODO: Move logging config to separate configuration file
    # set up logging to file for DEBUG messages and above
    logging.basicConfig(
        level=logging.DEBUG,
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
    logger.info(" ".join(sys.argv))
    print_args(args, logger=logger)

    read_until_client = read_until.ReadUntilClient(
        mk_host=args.host,
        device=args.device,
        # one_chunk=args.one_chunk,
        filter_strands=True,
        cache_type=args.read_cache,
        cache_size=args.cache_size,
    )

    analysis_worker = functools.partial(
        simple_analysis,
        read_until_client,
        unblock_duration=args.unblock_duration,
        throttle=args.throttle,
        chunk_log=args.chunk_log,
        paf_log=args.paf_log,
        toml_path=args.toml,
        log_level=args.log_level,
    )

    results = run_workflow(
        read_until_client,
        analysis_worker,
        args.workers,
        args.run_time,
        runner_kwargs={
            # "min_chunk_size": args.min_chunk_size,
            "first_channel": args.channels[0],
            "last_channel": args.channels[-1],
        },
    )
    # No results returned


if __name__ == "__main__":
    main()
