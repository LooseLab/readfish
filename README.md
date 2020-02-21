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
# Make a virtual environment
python3 -m venv read_until
. ./read_until/bin/activate
pip install --upgrade pip

# Install our Read Until API
pip install git+https://github.com/LooseLab/read_until_api_v2@master
pip install git+https://github.com/LooseLab/ru@issue15

# We use deepnano-blitz, which requires rust
# Install rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Switch to a nightly build
rustup default nightly-2019-12-11

# Clone deepnano-blitz
git clone https://github.com/fmfi-compbio/deepnano-blitz

# Build deepnano-blitz
cd deepnano-blitz
python setup.py install
```


