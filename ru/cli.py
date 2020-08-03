import argparse
import importlib

from ._version import __version__


def run_command(parser, args):
    try:
        command = importlib.import_module("ru.{}".format(args.commmand))
    except ImportError:
        parser.exit(2, "Could not use sub-command: {!r}".format(args.commmand))

    command.run(parser, args)


def main():
    parser = argparse.ArgumentParser(
        prog="readfish",
        epilog="See '<command> --help' to read about a specific sub-command.",
    )
    version = "readfish {}".format(__version__)
    parser.add_argument("--version", action="version", version=version)
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    cmds = [
        ("targets", "ru_gen"),
        ("align", "iteralign"),
        ("centrifuge", "iteralign_centrifuge"),
        ("unblock-all", "unblock_all"),
        ("validate", "validate"),
        ("summary", "summarise_fq")
    ]
    for cmd, module in cmds:
        _module = importlib.import_module("ru.{}".format(module))
        _parser = subparsers.add_parser(cmd, help=_module._help)
        for *flags, opts in _module._cli:
            _parser.add_argument(*flags, **opts)
        _parser.set_defaults(func=run_command)

    args = parser.parse_args()
    if args.command is not None:
        args.func(parser, args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
