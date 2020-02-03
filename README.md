Read Until
==========

This is a Python3 package that integrates with the 
[Read Until API](https://github.com/nanoporetech/read_until_api).

The Read Until API provides a mechanism for an application to connect to a
MinKNOW server to obtain read data in real-time. The data can be analysed in the
way most fit for purpose, and a return call can be made to the server to unblock
the read in progress.

---

Installation
------------

```bash
# Clone repositories
git clone https://github.com/looselab/read_until_api_v2.git
git clone https://github.com/looselab/ru.git

# Build ru code
cd ru
python3 -m venv venv3
source ./venv3/bin/activate
pip install --upgrade pip -r requirements.txt
python setup.py develop

# Build read until api
cd ../read_until_api_v2
pip install -r requirements.txt
python setup.py develop
```

PyGuppy is available request from Oxford Nanopore Technologies

You can now use `pip list` to check that the repos are installed with the correct directories.

```bash
$ pip list
Package                  Version   Location
------------------------ --------- --------------------------------------
...
pyguppy                  0.0.1     /Users/Alex/projects/pyguppyplay
...
read-until-api-v2        3.0.0     /Users/Alex/projects/read_until_api_v2
...
ru                       2.0.0     /Users/Alex/projects/ru
...
```

