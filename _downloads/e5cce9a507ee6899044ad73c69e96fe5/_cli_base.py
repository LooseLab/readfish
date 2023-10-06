"""Main entry point for command line read until scripts.

Set as entrypoint in ``pyproject.toml``
"""
from __future__ import annotations
import sys
import argparse
import importlib
import logging

from readfish.__about__ import __version__
from readfish._loggers import setup_logger, print_args


def main(argv: list[str] | None = None) -> None:
    """Main function for entry point of the read until scripts.

    :param argv: used in tests default None
    :raises SystemExit: Raises a system exit when the command function exits.
    """
    parser = argparse.ArgumentParser(
        prog="readfish",
        epilog="See '<command> --help' to read about a specific sub-command.",
        allow_abbrev=False,
    )
    version = f"readfish {__version__}"
    parser.add_argument("--version", action="version", version=version)
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands", metavar="")
    # add new entry point here
    cmds = [
        ("targets", "targets"),
        ("barcode-targets", "targets"),
        ("unblock-all", "unblock_all"),
        ("validate", "validate"),
        ("stats", "stats"),
    ]
    # Entry point is imported during runtime, and added as a sub command to readfish
    for cmd, module in cmds:
        _module = importlib.import_module(f"readfish.entry_points.{module}")
        _parser = subparsers.add_parser(cmd, help=_module._help)
        for *flags, opts in _module._cli:
            _parser.add_argument(*flags, **opts)
        _parser.set_defaults(func=_module.run)

    args, extras = parser.parse_known_args(argv)

    if args.command is not None:
        logger = setup_logger(
            "readfish",
            level=getattr(logging, args.log_level.upper()),
            log_format=args.log_format,
            log_console=True,
            log_file=args.log_file,
            # FIXME: Need to evaluate whether we should be propagating this or not?
            #        pytest caplog doesn't work without it..., but will a chunk/other
            #        debug log create issues?
            # propagate=True,
        )
        logger.info(" ".join(sys.argv) if argv is None else argv)
        print_args(args, printer=logger.info, exclude=["func"])
        raise SystemExit(args.func(parser, args, extras))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
