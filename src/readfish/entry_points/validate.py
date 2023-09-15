"""Validate experiment configuration :doc:`TOML <toml>` files.

This script is used to check that an experiment configuration file can be loaded.
By default, this will attempt to load the ``Caller`` and ``Aligner`` plugins as specified in the
:doc:`TOML <toml>` file. The ``--no-check-plugins`` flag can be used to skip this step.
The ``--no-describe`` flag can be used to skip printing a description of the configuration to terminal. Description will error if there a re contigs listed as targets which are not found in the reference.

These basic checks are for compatibility and do not indicate that a configuration/plugins will work efficiently with readfish.

Any errors are passed back through and printed to terminal.
If you require help understanding or resolving an error you can check the :doc:`TOML <toml>` documentation pages or `open an issue`_.

Example run command::

   readfish validate my_exp.toml

.. _`open an issue`: https://github.com/LooseLab/readfish/issues/new
"""

import sys
import logging

if sys.version_info < (3, 11):
    from exceptiongroup import BaseExceptionGroup

from readfish._config import Conf
from readfish._cli_args import BASE_ARGS
from readfish._utils import iter_exception_group


_help = "Readfish TOML Validator"
_cli = BASE_ARGS + (
    ("toml", dict(help="TOML file to validate")),
    (
        "--prom",
        dict(
            help="Use this flag if the target platform is a PromethION",
            action="store_true",
        ),
    ),
    (
        "--no-check-plugins",
        dict(
            help="Do not attempt to load the plugins with the supplied toml file configuration.",
            action="store_true",
        ),
    ),
    (
        "--no-describe",
        dict(
            help="Do not describe the experimental and plugin configuration. Always disabled if --no-check-plugins is passed.",
            action="store_true",
        ),
    ),
)


def run(parser, args, extras) -> int:
    """
    Runs the validate entry point

    :parser: The parser. Unused, but must be included as targets.py requires it
    :type:
    """
    logger = logging.getLogger(f"readfish.{args.command}")
    channels = 3000 if args.prom else 512
    try:
        conf = Conf.from_file(args.toml, channels, logger=logger)
    except BaseExceptionGroup as exc:
        msg = f"Could not load TOML config ({args.toml}), see below for details:\n"
        msg += "\n".join(iter_exception_group(exc))
        logger.error(msg)
        return 1
    logger.info("Loaded TOML config without error")

    errors = 0
    if args.no_check_plugins:
        logger.info("Plugin initialisation and testing was skipped.")
    else:
        logger.info("Initialising Caller")
        try:
            _ = conf.caller_settings.load_object("Caller")
        except Exception as exc:
            logger.error("Caller could not be initialised, see below for details")
            logger.error(str(exc))
            errors += 1
        else:
            logger.info("Caller initialised")

        logger.info("Initialising Aligner")
        try:
            al = conf.mapper_settings.load_object("Aligner")
        except Exception as exc:
            logger.error("Aligner could not be initialised, see below for details")
            logger.error(str(exc))
            errors += 1
        else:
            logger.info("Aligner initialised")

        if args.no_describe:
            logger.info("Skipping descriptions of Config and Plugins.")
        elif not errors:
            logger.info(conf.describe_experiment())
            logger.info(al.describe(conf.regions, conf.barcodes))
        else:
            logger.info("Skipping descriptions due to errors.")

    return errors
