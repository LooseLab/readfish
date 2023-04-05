"""arguments.py
The central commands used by most CLI read fish scripts.
"""
from readfish._utils import nice_join

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
            type=int,
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
            help="Run the ReadFish Until experiment without sending unblock commands",
        ),
    ),
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
