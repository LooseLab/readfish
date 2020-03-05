from setuptools import setup, find_packages
from os import path

PKG_NAME = "ru"

here = path.abspath(path.dirname(__file__))

with open(path.join(here, "README.md")) as fh, open(path.join(here, "requirements.txt")) as req:
    long_description = fh.read()
    install_requires = [pkg.strip() for pkg in req]

__version__ = ""
exec(open("{}/_version.py".format(PKG_NAME)).read())

setup(
    name=PKG_NAME,
    version=__version__,
    author="Alexander Payne",
    author_email="alexander.payne@nottingham.ac.uk",
    description="Python3 implementation of read_until client",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/nanoporetech",
    packages=find_packages(exclude=["*.test", "*.test.*", "test.*", "test"]),
    entry_points={
        "console_scripts": [
            "ru_validate={}.validate:main".format(PKG_NAME),
            "ru_generators={}.ru_gen:main".format(PKG_NAME),
            "ru_summarise_fq={}.summarise_fq:main".format(PKG_NAME),
            "ru_iteralign={}.iteralign:main".format(PKG_NAME),
            "ru_iteralign_centrifuge={}.iteralign_centrifuge:main".format(PKG_NAME),
            "ru_unblock_all={}.unblock_all:main".format(PKG_NAME),
        ],
    },
    install_requires=install_requires,
    include_package_data=True,
)
