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
from statistics import mean, median, stdev
from collections import defaultdict, deque, Counter

# Pypi imports
import toml
import numpy as np

# Pyguppy imports
from read_until.basecall import PerpetualCaller as Caller
from read_until.basecall import Mapper as CustomMapper

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


def describe(L):
    f = (
        ("count", len, "i"),
        ("mean", mean, "f"),
        ("stdev", stdev, "f"),
        ("min", min, "f"),
        ("median", median, "f"),
        ("max", max, "f"),
    )
    m = max(len(n) for n, _, _1 in f)
    for n, x, t in f:
        if t == "f":
            print("{:>{}}  {:.8f}".format(n, m, x(L)))
        elif t == "i":
            print("{:>{}}  {:,}".format(n, m, x(L)))


def setup_logger(name, log_file, level=logging.DEBUG):
    """Function setup as many loggers as you want"""
    formatter = logging.Formatter("%(message)s")
    handler = logging.FileHandler(log_file, mode="w")
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)

    return logger


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
    guppy_kwargs = t.get("guppy_connection", {
            "config": "dna_r9.4.1_450bps_fast",
            "host": "127.0.0.1",
            "port": 5555,
            "procs": 4,
            "inflight": 512,
        })
    caller = Caller(**guppy_kwargs)
    mapper = CustomMapper(t["conditions"].get("reference"))

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
        loop_counter += 1
        t0 = timer()

        for r, (channel, read) in enumerate(
                client.get_read_chunks(batch_size=batch_size, last=True),
                start=1
        ):
            read_start_time = timer()
            if read.number not in tracker[channel]:
                tracker[channel].clear()
            tracker[channel][read.number] += 1

            cl.debug(
                l_string.format(
                    loop_counter,
                    r,
                    read.id,
                    channel,
                    read.number,
                    len(np.fromstring(read.raw_data, client.signal_dtype)),
                    read_start_time,
                    timer(),
                    time.time(),
                )
            )

            #print (read.id)
           # print (type(channel))
            if "readid" in previous_signal[channel]:
                #print (previous_signal[channel]["readid"])
                #print ("seen this before")
                #sys.exit()
                if read.id == str(previous_signal[channel]["readid"]):
                    previous_signal[channel]["signal"]+=len(np.fromstring(read.raw_data, client.signal_dtype))
                    previous_signal[channel]["updatetime"]=time.time()
            else:
                readcounter+=1
                print ("replacing channel/read:{}/{}".format(channel,read.id))
                previous_signal[channel]={"readid":read.id,"signal":len(np.fromstring(read.raw_data, client.signal_dtype)),"updatetime":time.time()}
            #print (previous_signal[channel]["readid"])
            #if read.id in previous_signal[channel]:
            #    previous_signal[channel][read.id]+=len(np.fromstring(read.raw_data, client.signal_dtype))
            #else:
            #    previous_signal[channel]={read.id:len(np.fromstring(read.raw_data, client.signal_dtype))}
            #print (read.number, read.id, channel,len(np.fromstring(read.raw_data, client.signal_dtype)))

        #print (previous_signal)
        #print (len(previous_signal))


        ## prune previous signal
        prunetime = time.time()


        for entry in previous_signal:
            #Prune a read if we haven't seen it for 20 seconds
            if prunetime - previous_signal[entry]['updatetime']>=2:
                previous_signal[entry]["readid"]="NA"
                previous_signal[entry]["signal"]=0

            previous_signal[entry]["updatetime"]=time.time()


            longestreads[entry]=int(previous_signal[entry]["signal"]/4000*400)

        if int(time.time() %60) % 5 == 0:
            if display:
                print (int(time.time() %60) % 10)
                print ("{}".format(sorted(longestreads.items(), key=lambda pair: pair[1], reverse=True)[:10])) #,end = '')
                print (len(longestreads))
                print ("reads seen: {}".format(readcounter))
                display = False
        else:
            display = True


        t1 = timer()
        #logger.info("Took {} for {} reads".format(t1 - t0, r))
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
            res = result.get(5)
        except TimeoutError:
            logger.warning("Worker function did not exit successfully.")
            # collected.append(None)
        except Exception as e:
            logger.exception("EXCEPT", exc_info=e)
            # logger.warning("Worker raise exception: {}".format(repr(e)))
        else:
            logger.info("Worker exited successfully.")
            collected.extend(res)
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
        one_chunk=args.one_chunk,
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
            "min_chunk_size": args.min_chunk_size,
            "first_channel": args.channels[0],
            "last_channel": args.channels[-1],
        },
    )
    # describe(results)
    # No results returned


if __name__ == "__main__":
    main()
