"""Validate experiment configuration :doc:`TOML <toml>` files.

This script is used to check that an experiment configuration file can be loaded.
In addition, using the ``--check-plugins`` flag will also attempt to load the listed ``Aligner`` and ``Caller`` plugins.

These basic checks are for compatibility and do not indicate that a configuration/plugins will work efficiently with readfish.

Any errors are passed back through and printed to terminal.
If you require help understanding or resolving an error you can check the :doc:`TOML <toml>` documentation pages or `open an issue`_.

Example run command::

   readfish validate my_exp.toml --check-plugins

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
        "--check-plugins",
        dict(
            help="If the config can be loaded attempt loading the plugins too",
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
    if args.check_plugins:
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
            _ = conf.mapper_settings.load_object("Aligner", readfish_config=conf)
        except Exception as exc:
            logger.error("Aligner could not be initialised, see below for details")
            logger.error(str(exc))
            errors += 1
        else:
            logger.info("Aligner initialised")
    return errors
