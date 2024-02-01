"""Store for command line arguments and defaults, these are used by readfish entry points.

These are held here in an agnostic format and the actual CLI is generated by ``readfish._cli_base``.
The two primary items that are exported are ``BASE_ARGS`` and ``DEVICE_BASE_ARGS`` which define different sets of command line arguments for different purposes.
``BASE_ARGS`` are the minimal required arguments for _all_ entry points as they used for initialising loggers.
``DEVICE_BASE_ARGS`` are the set of arguments that are used for connecting to a sequencer (device) and some other related settings for selective sequencing scripts.
"""

from enum import Enum, unique
from readfish._utils import nice_join


@unique
class Chemistry(Enum):
    #: For the "smarter" version of duplex - does this read map to the previous reads opposite strand on the same contig. Won't work for no map based decisions
    DUPLEX = "duplex"
    #: Normal simplex chemistry - no duplex override shenanigans
    SIMPLEX = "simplex"
    #: Simple duplex - if we are going to unblock a read given the previous read on the same channel was stop receiving, sequence the current read instead.
    DUPLEX_SIMPLE = "duplex_simple"


DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = None
DEFAULT_LOG_FORMAT = "%(asctime)s %(name)s %(message)s"
DEFAULT_LOG_LEVEL = "info"
DEFAULT_UNBLOCK = 0.1
DEFAULT_THROTTLE = 0.4
DEFAULT_MIN_CHUNK = 2000
LOG_LEVELS = ("debug", "info", "warning", "error", "critical")
DEFAULT_MAX_UNBLOCK_READ_LENGTH_SECONDS = 5

BASE_ARGS = (
    (
        "--log-level",
        dict(
            metavar="LOG-LEVEL",
            action="store",
            default=DEFAULT_LOG_LEVEL,
            choices=LOG_LEVELS,
            help=f"One of: {nice_join(LOG_LEVELS)}",
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

DEVICE_BASE_ARGS = (
    (
        "--host",
        dict(
            metavar="HOST",
            help=f"MinKNOW server host (default: {DEFAULT_SERVER_HOST})",
            default=DEFAULT_SERVER_HOST,
        ),
    ),
    (
        "--port",
        dict(
            metavar="PORT",
            help="MinKNOW server port, if not specified automatically chosen by the MinKNOW API",
            default=DEFAULT_SERVER_PORT,
        ),
    ),
    (
        "--device",
        dict(
            metavar="DEVICE",
            type=str,
            help="Name of the sequencing position e.g. MS29042 or X1 etc.",
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
        "--unblock-duration",
        dict(
            metavar="UNBLOCK-DURATION",
            type=float,
            help="Time, in seconds, to apply unblock voltage (default: {})".format(
                DEFAULT_UNBLOCK
            ),
            default=DEFAULT_UNBLOCK,
        ),
    ),
    (
        # TODO: Determine if we need a minimum value for throttle which shouldn't be overridden.
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
        "--max-unblock-read-length-seconds",
        dict(
            metavar="SECONDS",
            type=float,
            help=f"Maximum read length, in seconds, that MinKNOW will attempt to unblock (default: {DEFAULT_MAX_UNBLOCK_READ_LENGTH_SECONDS}).",
            default=DEFAULT_MAX_UNBLOCK_READ_LENGTH_SECONDS,
        ),
    ),
    (
        "--dry-run",
        dict(
            action="store_true",
            help="Run the readfish Until experiment without sending unblock commands",
        ),
    ),
    (
        "--wait-for-ready",
        dict(
            help="Timeout for the MinKNOW data folder to appear, and the device to report it is ready to start sequencing in seconds. (default: 120s).",
            required=False,
            default=120,
            type=int,
        ),
    ),
    (
        "--chemistry",
        dict(
            help="**EXPERIMENTAL** Choose between duplex and simplex chemistry mode. duplex_simple accept a read if the previous channels read was stop receiving,"
            "duplex checks that the previous reads alignment was on the same contig and opposite strand. default: SIMPLEX",
            required=False,
            type=str,
            default=Chemistry.SIMPLEX,
            choices=[chemistry.value for chemistry in Chemistry],
        ),
    ),
) + BASE_ARGS
