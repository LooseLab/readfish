from setuptools import setup, find_packages
from os import path

PKG_NAME = "readfish"
MOD_NAME = "ru"

DESCRIPTION = """# <img src="https://raw.githubusercontent.com/LooseLab/ru/rename_cli/examples/images/readfish_logo.jpg">

Installation
---

This toolkit currently requires MinKNOW (minknow-core v4.0.4) to be installed and 
[`read_until_api`](https://github.com/nanoporetech/read_until_api) to be installed
separately. We recommend installing in a virtual environment as so:

```bash
# Make a virtual env
python3 -m venv readfish
source ./readfish/bin/activate
pip install git+https://github.com/nanoporetech/read_until_api
pip install readfish
```

Usage
---
```bash
# check install
$ readfish
usage: readfish [-h] [--version]
                {targets,align,centrifuge,unblock-all,validate,summary} ...

positional arguments:
  {targets,align,centrifuge,unblock-all,validate,summary}
                        Sub-commands
    targets             Run targeted sequencing
    align               ReadFish and Run Until, using minimap2
    centrifuge          ReadFish and Run Until, using centrifuge
    unblock-all         Unblock all reads
    validate            ReadFish TOML Validator
    summary             Summary stats from FASTQ files

optional arguments:
  -h, --help            show this help message and exit
  --version             show program's version number and exit

See '<command> --help' to read about a specific sub-command.

# example run command - change arguments as necessary:
$ readfish targets --experiment-name "Test run" --device MN17073 --toml example.toml --log-file RU_log.log
```
"""

here = path.abspath(path.dirname(__file__))

with open(path.join(here, "README.md")) as fh, open(
    path.join(here, "requirements.txt")
) as req:
    install_requires = [pkg.strip() for pkg in req]

__version__ = ""
exec(open("{}/_version.py".format(MOD_NAME)).read())

setup(
    name=PKG_NAME,
    version=__version__,
    author="Alexander Payne",
    author_email="alexander.payne@nottingham.ac.uk",
    description="Adaptive sampling toolkit for MinION",
    long_description=DESCRIPTION,
    long_description_content_type="text/markdown",
    url="https://github.com/LooseLab",
    packages=find_packages(exclude=["*.test", "*.test.*", "test.*", "test"]),
    entry_points={
        "console_scripts": [
            "ru_validate={}.validate:main".format(MOD_NAME),
            "ru_generators={}.ru_gen:main".format(MOD_NAME),
            "ru_summarise_fq={}.summarise_fq:main".format(MOD_NAME),
            "ru_iteralign={}.iteralign:main".format(MOD_NAME),
            "ru_iteralign_centrifuge={}.iteralign_centrifuge:main".format(MOD_NAME),
            "ru_unblock_all={}.unblock_all:main".format(MOD_NAME),
            "readfish={}.cli:main".format(MOD_NAME),
        ],
    },
    install_requires=install_requires,
    include_package_data=True,
    python_requires=">=3.5",
)
