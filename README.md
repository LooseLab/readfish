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

```bash
# check install
$ ru_generators
usage: Read Until API: ru_generators (/Users/Alex/projects/ru/ru/ru_gen.py)
       [-h] [--host HOST] [--port PORT] --device DEVICE --experiment-name
       EXPERIMENT-NAME [--read-cache READ_CACHE] [--workers WORKERS]
       [--channels CHANNELS CHANNELS] [--run-time RUN-TIME]
       [--unblock-duration UNBLOCK-DURATION] [--cache-size CACHE-SIZE]
       [--batch-size BATCH-SIZE] [--throttle THROTTLE] [--dry-run]
       [--log-level LOG-LEVEL] [--log-format LOG-FORMAT] [--log-file LOG-FILE]
       --toml TOML [--paf-log PAF_LOG] [--chunk-log CHUNK_LOG]
Read Until API: ru_generators (/Users/Alex/projects/ru/ru/ru_gen.py): error: 
    the following arguments are required: --device, --experiment-name, --toml

# example run command:
$ ru_generators --experiment-name "Test run" --device MN17073 --toml example.toml --log-file RU_log.log
```
