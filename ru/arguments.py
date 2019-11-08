import argparse
import sys

import read_until_api_v2.read_cache as RC
from ru.utils import nice_join

# TODO: Add prefix parameter that is applied to all log files

DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 9501
DEFAULT_WORKERS = 1
DEFAULT_LOG_FORMAT = "%(asctime)s %(name)s %(message)s"
DEFAULT_LOG_LEVEL = "info"
DEFAULT_CHANNELS = [1, 512]
DEFAULT_DELAY = 0
DEFAULT_RUN_TIME = 172800
DEFAULT_UNBLOCK = 0.1
DEFAULT_CACHE_SIZE = 512
DEFAULT_BATCH_SIZE = 512
DEFAULT_THROTTLE = 0.1
DEFAULT_MIN_CHUNK = 2000
DEFAULT_LOG_PREFIX = ""

LOG_LEVELS = ("debug", "info", "warning", "error", "critical")
READ_CACHE = RC.__all__

if "ONTReadCache" in READ_CACHE:
    DEFAULT_READ_CACHE = "ONTReadCache"
else:
    try:
        DEFAULT_READ_CACHE = READ_CACHE[0]
    except IndexError:
        raise IndexError("No ReadCache classes found")

BASE_ARGS = (
    (
        "--host",
        dict(
            metavar="HOST",
            help="MinKNOW server host (default: {})".format(DEFAULT_SERVER_HOST),
            default=DEFAULT_SERVER_HOST,
        ),
    ),
    (
        "--port",
        dict(
            metavar="PORT",
            help="MinKNOW server port (default: {})".format(DEFAULT_SERVER_PORT),
            default=DEFAULT_SERVER_PORT,
        ),
    ),
    (
        "--device",
        dict(
            metavar="DEVICE",
            type=str,
            help="Name of the sequencing position e.g. MS29042 or GA10000 etc.",
            required=True,
        ),
    ),
    (
        "--experiment-name",
        dict(
            metavar="EXPERIMENT-NAME",
            type=str,
            help="Describe the experiment being run, enclose in quotes",
            required=True,
        ),
    ),
    (
        "--read-cache",
        dict(
            metavar="READ_CACHE",
            action="store",
            default=DEFAULT_READ_CACHE,
            choices=READ_CACHE,
            help="One of: {} (default: {})".format(
                nice_join(READ_CACHE), DEFAULT_READ_CACHE
            ),
        ),
    ),
    (
        "--workers",
        dict(
            metavar="WORKERS",
            type=int,
            help="Number of worker threads (default: {})".format(DEFAULT_WORKERS),
            default=DEFAULT_WORKERS,
        ),
    ),
    # TODO: Make channels more explicit as this param is used to determine the flowcell size
    #  even though we can opt to run on a subset of channels
    (
        "--channels",
        dict(
            metavar="CHANNELS",
            type=int,
            nargs=2,
            help="Channel range to use as a sequence, expects two integers "
                 "separated by a space (default: {})".format(
                    DEFAULT_CHANNELS
            ),
            default=DEFAULT_CHANNELS,
        ),
    ),
    # FIXME: This is now handled by the TOML file, but we may still want to use an
    #  odd/even configuration, this should be removed
    (
        "--split",
        dict(
            action="store_true",
            help="Split the flowcell into odd/even categories. Even channels "
                 "are controls while odd channels are selecting.",
        ),
    ),
    (
        "--delay",
        dict(
            metavar="DELAY",
            type=int,
            help="Period, in seconds, to wait before starting analysis (default: {})".format(
                DEFAULT_DELAY
            ),
            default=DEFAULT_DELAY,
        ),
    ),
    (
        "--run-time",
        dict(
            metavar="RUN-TIME",
            type=int,
            help="Period (seconds) to run the analysis (default: {:,})".format(
                DEFAULT_RUN_TIME
            ),
            default=DEFAULT_RUN_TIME,
        ),
    ),
    (
        "--unblock-duration",
        dict(
            metavar="UNBLOCK-DURATION",
            type=int,
            help="Time, in seconds, to apply unblock voltage (default: {})".format(
                DEFAULT_UNBLOCK
            ),
            default=DEFAULT_UNBLOCK,
        ),
    ),
    (
        "--cache-size",
        dict(
            metavar="CACHE-SIZE",
            type=int,
            help="The size of the read cache in the ReadUntilClient (default: {:,})".format(
                DEFAULT_CACHE_SIZE
            ),
            default=DEFAULT_CACHE_SIZE,
        ),
    ),
    (
        "--batch-size",
        dict(
            metavar="BATCH-SIZE",
            type=int,
            help="The maximum number of reads to pull from the read cache (default: {:,})".format(
                DEFAULT_BATCH_SIZE
            ),
            default=DEFAULT_BATCH_SIZE,
        ),
    ),
    (
        "--throttle",
        dict(
            metavar="THROTTLE",
            type=float,
            help="Time interval, in seconds, between requests to the ReadUntilClient (default: {})".format(
                DEFAULT_THROTTLE
            ),
            default=DEFAULT_THROTTLE,
        ),
    ),
    (
        "--one-chunk",
        dict(
            action="store_true",
            help="Attempt to receive only one chunk per read. When enabled a request "
                 "to stop receiving more data for a read is immediately staged when "
                 "the first chunk is cached. (default: False)"
        ),
    ),
    # FIXME: Marked for removal, min_chunk_size is set as a MinKNOW configuration setting
    #  and we receive chunks in the smallest available size. It doesn't make sense to add
    #  extra filters
    (
        "--min-chunk-size",
        dict(
            metavar="MIN-CHUNK-SIZE",
            type=int,
            help="Minimum read chunk size to receive. NOTE: this functionality "
            "is currently disabled; read chunks received will be unfiltered",
            default=DEFAULT_MIN_CHUNK,
        ),
    ),
    (
        "--dry-run",
        dict(
            action="store_true",
            help="Run the Read Until experiment without sending unblock commands",
        ),
    ),
    (
        "--log-level",
        dict(
            metavar="LOG-LEVEL",
            action="store",
            default=DEFAULT_LOG_LEVEL,
            choices=LOG_LEVELS,
            help="One of: {}".format(nice_join(LOG_LEVELS)),
        ),
    ),
    (
        "--log-format",
        dict(
            metavar="LOG-FORMAT",
            action="store",
            default=DEFAULT_LOG_FORMAT,
            help="A standard Python logging format string (default: {!r})".format(
                DEFAULT_LOG_FORMAT.replace("%", "%%")
            ),
        ),
    ),
    (
        "--log-file",
        dict(
            metavar="LOG-FILE",
            action="store",
            default=None,
            help="A filename to write logs to, or None to write to the standard stream (default: None)",
        ),
    ),
)


def get_parser(extra_args=None, file=None, default_args=None):
    """Generic argument parser for Read Until scripts

    Parameters
    ----------
    extra_args : Tuple[Tuple[str, dict], ...]
        Extra arguments to append onto the base arguments
    file : str
        Optional. __file__ from the python script, used for program string
    default_args : Tuple[Tuple[str, dict], ...]
        Arguments that form the base requirements for all Read Until scripts

    Returns
    -------
    parser : argparse.ArgumentParser
        The argparse parser, used for raising parser errors manually
    arguments : argparse.ArgumentParser().parse_args()
        The parsed arguments
    """
    if default_args is None:
        args = BASE_ARGS
    else:
        args = default_args

    if extra_args is not None:
        args = args + extra_args

    if file is None:
        prog_string = "Read Until API: {}".format(sys.argv[0].split("/")[-1])
    else:
        prog_string = "Read Until API: {} ({})".format(sys.argv[0].split("/")[-1], file)

    parser = argparse.ArgumentParser(prog_string)
    for arg in args:
        flags = arg[0]
        if not isinstance(flags, tuple):
            flags = (flags,)
        parser.add_argument(*flags, **arg[1])

    return parser, parser.parse_args()
