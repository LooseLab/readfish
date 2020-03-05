import sys
import argparse
import textwrap

from ru.utils import get_run_info, describe_experiment, Severity
from ru.basecall import Mapper


class colour:
   GREEN = '\033[92m'
   YELLOW = '\033[93m'
   RED = '\033[91m'
   BOLD = '\033[1m'
   END = '\033[0m'


def printer(s, sev, **kwargs):
    if sev == Severity.INFO:
        print(s, **kwargs)
    elif sev == Severity.WARN:
        print("{}{}{}".format(colour.YELLOW, s, colour.END), **kwargs)
    elif sev == Severity.ERROR:
        print("{}{}{}".format(colour.RED, s, colour.END), **kwargs)


def except_hook(type, value, traceback):
    print(value, file=sys.stderr)


def main():
    # Catch exceptions and only print error line
    sys.excepthook = except_hook

    # Parse single positional argument
    parser = argparse.ArgumentParser(
        "Read Until TOML Validator ({})".format(__file__)
    )
    parser.add_argument("toml", help="TOML file to validate")
    args = parser.parse_args()

    # Run load config to validate
    run_info, conditions, reference, caller_settings = get_run_info(args.toml)
    print("😻 Looking good!", file=sys.stdout)
    print("Generating experiment description - please be patient!", file=sys.stdout)
    mapper = Mapper(reference)
    for message, sev in describe_experiment(conditions, mapper):
        printer(textwrap.fill(message), sev, file=sys.stdout, end="\n\n")


if __name__ == "__main__":
    main()
