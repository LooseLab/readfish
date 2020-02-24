Read Until
==========

This is a Python3 package that integrates with the 
[Read Until API](https://github.com/nanoporetech/read_until_api).

The Read Until API provides a mechanism for an application to connect to a
MinKNOW server to obtain read data in real-time. The data can be analysed in the
way most fit for purpose, and a return call can be made to the server to unblock
the read in progress.

**This implementation of Read Until requires Guppy version 3.4 or newer.**

Installation
------------

```bash
# Make a virtual environment
python3 -m venv read_until
. ./read_until/bin/activate
pip install --upgrade pip

# Install our Read Until API
pip install git+https://github.com/LooseLab/read_until_api_v2@master
pip install git+https://github.com/LooseLab/ru@master
```

Usage
-----

