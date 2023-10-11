"""
This module is the stats entry point into the Readfish package, focussed specifically
on calculating summary information about a Readfish experiment. It parses base-called
FASTQ files produced after a Readfish experiment and, by using the same aligner
setup as the experiment, aligns reads, aggregates stats and prints out a summary.

This module can be used to assess the results of a Readfish experiment, where the user
wants to get insights into the experiment's outcome within the context of readfish.
It accepts several command-line arguments to customize its
behaviour, including specifying the TOML file used in the Readfish experiment, the
directory containing the FASTQ files, and options to control the output format.

The alignment and aggregation of the FASTQ happens in a separate package,
`readfish_summarise`. https://github.com/Adoni5/ReadfishSummarise

FASTQ are demultiplexed into separate files for each combination of the Condition
( Region or Barcode ) name and the decision that readfish makes about the read
(stop_receiving, unblock or proceed). For example:


    #. `barcode01_stop_receiving.fastq.gz`

    #. `control_region_unblock.fastq.gz`

returns:
    An exit code. 0 if the process completes successfully without errors, otherwise the number of errors.

Command-Line Arguments
----------------------
The module accepts the following command-line arguments:

- ``toml`` (required):
    Path to the TOML file used in the Readfish experiment.

- ``fastq_dir`` (required):
    Path to the directory containing the FASTQ files produced by the Readfish
    experiment.

- ``--no-paf-out`` (optional):
    Disables the output of the alignments in PAF format. Enabled by default.

- ``--no-demultiplex`` (optional):
    If specified, the module won't demultiplex and write out FASTQ. Demultiplexing is enabled by default.

- ``--prom`` (optional):
    If specified, indicates that the target platform was a PromethION.


Usage
-----
An example of how to use this module without outputting demultiplexed FASTQ and PAF alignments is shown below:

.. code-block:: bash

    readfish stats --toml tests/static/stats_test/yeast_summary_test.toml --fastq-directory tests/static/stats_test/ --no-paf-out --no-demultiplex

To run and demultiplex, but not output PAF alignments

.. code-block:: bash

    readfish stats --toml tests/static/stats_test/yeast_summary_test.toml --fastq-directory tests/static/stats_test/ --no-paf-out

To run and output PAF alignments and demutiplexed FASTQ

.. code-block:: bash

    readfish stats --toml tests/static/stats_test/yeast_summary_test.toml --fastq-directory tests/static/stats_test/

To run and output PAF alignments and demutiplexed FASTQ, and output a HTML summary file at summary_adaptive.html

.. code-block:: bash

    readfish stats --toml tests/static/stats_test/yeast_summary_test.toml --fastq-directory tests/static/stats_test/ --html summary_adaptive

"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import logging

if sys.version_info < (3, 11):
    from exceptiongroup import BaseExceptionGroup

from readfish._config import Conf
from readfish._cli_args import BASE_ARGS
from readfish._utils import iter_exception_group
from readfish_summarise.summarise import _fastq


_help = "Readfish experiment summary stats"
_cli = BASE_ARGS + (
    ("--toml", dict(help="TOML file used in the readfish experiment.", required=True)),
    (
        "--fastq-directory",
        dict(
            help="Path to the directory containing the FASTQ files produced by the readfish experiment",
            type=Path,
            required=True,
        ),
    ),
    (
        "--no-paf-out",
        dict(
            help="Don't output the alignments in PAF format. By default PAF output Enabled.",
            action="store_false",
        ),
    ),
    (
        "--no-demultiplex",
        dict(
            help="Don't demultiplex and write out FASTQ. By default Multiplexing Enabled.",
            action="store_false",
        ),
    ),
    (
        "--no-csv",
        dict(
            help="Use this flag to not output CSV of the calculated summary stats. By default CSV output Enabled.",
            action="store_false",
        ),
    ),
    (
        "--prom",
        dict(
            help="Use this flag if the target platform was a PromethION. Disabled by default.",
            action="store_true",
        ),
    ),
    (
        "--html",
        dict(
            help="Filepath to output a HTML file of the summary. Will append .html to given filename/path. Disabled by default.",
            type=Path,
            default=None,
        ),
    ),
)


def run(_parser, args: argparse.NameSpace, _extras):
    """
    Calculates summary information about a readfish experiment. Passes fastq into the aligner
    implementation of summarise - which will print out a summary after parsing all the data.

    :param _parser: The parser. Unused, but must be included as targets.py requires it.

    :param args: Command-line arguments obtained from the command-line parser.

    :param _extras: Additional arguments. Unused, but must be included as targets.py requires it.

    :returns: None

    """
    logger = logging.getLogger(f"readfish.{args.command}")
    channels = 3000 if args.prom else 512
    errors = 0
    try:
        _conf = Conf.from_file(args.toml, channels, logger=logger)
    except BaseExceptionGroup as exc:
        msg = f"Could not load TOML config ({args.toml}), see below for details:\n"
        msg += "\n".join(iter_exception_group(exc))
        logger.error(msg)
        errors += 1
    logger.info("Loaded TOML config without error")

    try:
        _fastq(
            args.toml,
            args.fastq_directory,
            demultiplex=args.no_demultiplex,
            paf_out=args.no_paf_out,
            prom=args.prom,
            csv=args.no_csv,
            html=args.html,
        )
    except Exception as exc:
        logger.error("Fastq data couldn't be summarised, see below for details:")
        logger.error(exc)
        errors += 1
    return errors
