import argparse
import json
import sys
from pathlib import Path
import re

import toml
import jsonschema


def any_full_match(patterns, string):
    return any((re.fullmatch(p, string) for p in patterns))


def main():
    parser = argparse.ArgumentParser("RU3 TOML Validator ({})".format(__file__))
    parser.add_argument("schema", help="JSON schema")
    parser.add_argument("-i", help="TOML file", dest="toml", required=True)
    parser.add_argument("-t", help="Validate target file", action="store_true")
    args = parser.parse_args()

    d = toml.load(args.toml)
    with open(args.schema) as fh:
        s = json.load(fh)

    try:
        jsonschema.validate(d, s)
    except jsonschema.exceptions.ValidationError as err:
        print(
            "😾 this TOML file is not valid and may not work with Read Until:",
            err,
            sep="\n\n",
        )
        sys.exit(1)

    patterns = [
        v
        for p in s["definitions"]["conditions"]["patternProperties"]["^[0-9]+$"][
            "properties"
        ]["targets"]["items"]["oneOf"]
        for k, v in p.items()
    ]

    if args.t:
        for k, v in d["conditions"].items():
            if not isinstance(v, dict):
                continue

            if isinstance(v["targets"], str) and Path(v["targets"]).is_file():
                with open(v["targets"], "r") as fh:
                    for i, line in enumerate(fh, start=1):
                        line = line.strip()
                        if not any_full_match(patterns, line):
                            print("{}:{} is invalid ({})".format(v["targets"], i, line))


if __name__ == "__main__":
    main()
