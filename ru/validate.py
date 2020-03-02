import sys
import argparse

from ru.utils import load_config_toml


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
    load_config_toml(args.toml, validate=True)
    print("😻 Looking good!", file=sys.stderr)


if __name__ == "__main__":
    main()
