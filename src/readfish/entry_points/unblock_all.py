"""An unblock all script.
This will attempt to unblock all reads on all channels.
This should result in a read length histogram that has very short peaks (<1kb) as these are the smallest chunks that we can acquire.
If you are not seeing these peaks, the ``break_reads_after_seconds`` parameter in the MinKNOW configuration file may need to be reduced to 0.5-0.8.

This script is primarily for testing a computer's response to processing data from the Read Until API without any other overheads (basecalling or mapping).
It is only recommended to use this script when running a simulated (playback) sequencing experiment.

The unblock all command only requires the target device and a small description of the experiment, for example:

.. code-block:: bash

   readfish unblock-all --device X3 --experiment-name "test unblock all"
"""
from tempfile import NamedTemporaryFile

from readfish._cli_args import DEVICE_BASE_ARGS
from readfish.entry_points import targets

_help = "Unblock all reads"
_cli = DEVICE_BASE_ARGS + (
    (
        "--no-debug-log",
        dict(
            help="Disable debug output of information about chunks seen into a .tsv formatted log. Default enabled.",
            action="store_false",
            dest="debug_log",
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
    """CLI entry point for the unblock all subcommand.

    This script is a simple wrapper that creates a temporary TOML file
    using the `TOML` variable above and then passes that through to the
    standard `targets` entry point. This TOML uses pass-through plugins
    so no basecalling or alignment occurs and the chosen action should
    always be "unblock". Running the script this way has the additional
    benefit of testing the targets entry point simultaneously.
    """
    with NamedTemporaryFile("wt") as fh:
        args.toml = fh.name
        fh.write(TOML)
        fh.flush()
        ret = targets.run(parser, args, extras)
    return ret
