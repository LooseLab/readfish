from tempfile import NamedTemporaryFile

from readfish._cli_args import BASE_ARGS
from readfish.entry_points import targets

_help = "Unblock all reads"
_cli = BASE_ARGS + (
    (
        "--debug-log",
        dict(
            help="Debug log, write a TSV for all records",
            default=None,
            dest="chunk_log",
        ),
    ),
)

TOML = """\
[caller_settings.no_op]
[mapper_settings.no_op]
[[regions]]
name = "unblock all"
min_chunks = 1
max_chunks = 2
targets = []
single_on = "unblock"
single_off = "unblock"
multi_on = "unblock"
multi_off = "unblock"
no_seq = "unblock"
no_map = "unblock"
above_max_chunks = "unblock"
below_min_chunks = "unblock"
"""


def run(parser, args, extras):
    with NamedTemporaryFile("wt") as fh:
        args.toml = fh.name
        fh.write(TOML)
        fh.flush()
        targets.run(parser, args, extras)
