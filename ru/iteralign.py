"""
Iter-align.
Design spec.
    1. Grab fastq files from a location.
    2. Align the files ONCE to a reference.
    3. Calculate cumulative coverage information.
    4. Write a list of genomes that are covered at a particular threshold.
    5. Rinse and repeat
"""
import logging
import logging.handlers
import os
import sys
import time
import toml
from watchdog.observers.polling import PollingObserver as Observer

from ru.utils import send_message, Severity, get_device
from minknow_api.acquisition_pb2 import MinknowStatus
from ru.run_until_utils import FastQMonitor
from ru.ru_gen import _cli as BASE
from ru.ru_gen import run as dnrun
from argparse import Namespace


DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_LOG_FORMAT = "%(asctime)s - %(name)-20s - %(message)s"
LOG_LEVELS = ("debug", "info", "warning", "error", "critical")
DEFAULT_COVERAGE_DEPTH = 30
# DEFAULT_PERCENTAGE_COVERED = 0.99
DEFAULT_CORES = 2


_help = "ReadFish and Run Until, using minimap2"
_cli = BASE + (
    (
        # In use by event_handler - passed as args.path
        "--watch",
        dict(
            metavar="FOLDER",
            help="Top Level Folder containing fastq reads.",
            default=None,
        ),
    ),
    # (
    # Not used ToDo: Delete
    #    "--percent",
    #    dict(
    #        metavar="PERCENT",
    #        help="Default percent of target covered at given depth (default {})".format(
    #            DEFAULT_PERCENTAGE_COVERED
    #        ),
    #        default=DEFAULT_PERCENTAGE_COVERED,
    #        type=float,
    #    ),
    # ),
    (
        # Used in run until utils
        "--depth",
        dict(
            metavar="DEPTH",
            help="Desired coverage depth (default {})".format(DEFAULT_COVERAGE_DEPTH),
            default=DEFAULT_COVERAGE_DEPTH,
            type=int,
        ),
    ),
    (
        # in use by fastqhandler.
        "--threads",
        dict(
            metavar="THREADS",
            help="Set the number of default threads to use for threaded tasks (default {})".format(
                DEFAULT_CORES
            ),
            default=DEFAULT_CORES,
            type=int,
        ),
    ),
)


def main():
    sys.exit("This entry point is deprecated, please use 'readfish align' instead")


def run(parser, args):
    args_copy = Namespace(**vars(args))
    args.tomlfile = args.toml
    args.toml = toml.load(args.toml)

    # TODO: Move logging config to separate configuration file
    # set up logging to file
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(levelname)s::%(asctime)s::%(name)s::%(message)s",
        filename=args.log_file,
        filemode="w",
    )

    # define a Handler that writes INFO messages or higher to the sys.stderr
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)

    # set a format which is simpler for console use
    formatter = logging.Formatter("%(name)-15s: %(levelname)-8s %(message)s")
    console.setFormatter(formatter)

    # add the handler to the root logger
    logging.getLogger("").addHandler(console)

    # Start by logging sys.argv and the parameters used
    logger = logging.getLogger("Manager")
    logger.info(" ".join(sys.argv))

    logger.info("Initialising readfish align.")

    logger.info("Setting up FastQ monitoring.")

    #### Check if a run is active - if not, wait.

    args.simulation = True
    connection = None
    if args.watch is None:
        args.simulation = False
        logger.info("Creating rpc connection for device {}.".format(args.device))
        try:
            connection = get_device(args.device).connect()
        except ValueError as e:
            print(e)
            sys.exit(1)

        send_message(connection, "ReadFish align connected to MinKNOW", Severity.WARN)

        logger.info("Loaded RPC")
        while (
            connection.acquisition.current_status().status != MinknowStatus.PROCESSING
        ):
            time.sleep(1)
        #### Check if we know where data is being written to , if not... wait
        args.watch = (
            connection.acquisition.get_acquisition_info().config_summary.reads_directory
        )

    ### Here we configure the code to run either ReadFish align or itercent. If centrifuge is False it will run ReadFish align.
    event_handler = FastQMonitor(
        args, connection, centrifuge=False, mapper=True, rununtil=True
    )

    # This block handles the fastq
    observer = Observer()
    print(args.watch)
    observer.schedule(event_handler, path=args.watch, recursive=True)
    observer.daemon = True

    try:

        observer.start()
        logger.info("FastQ Monitoring Running.")

        if not args.simulation:
            dnrun(parser, args_copy)
        else:
            while 1:
                time.sleep(1)

    except KeyboardInterrupt:

        logger.info("Exiting - Will take a few seconds to clean up!")

        observer.stop()
        observer.join()

        os._exit(0)
