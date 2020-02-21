Read Until
==========

This is a Python3 package that integrates with the 
[Read Until API](https://github.com/nanoporetech/read_until_api).

The Read Until API provides a mechanism for an application to connect to a
MinKNOW server to obtain read data in real-time. The data can be analysed in the
way most fit for purpose, and a return call can be made to the server to unblock
the read in progress.

This branch of read until REQUIRES DeepNano-Blitz to be installed but can use either Guppy or DeepNano-Blitz for basecalling.

---

Installation
------------

### Read Until API with PyGuppyClient

```bash
# Make a virtual environment
python3 -m venv read_until
. ./read_until/bin/activate
pip install --upgrade pip

# Install our Read Until API
pip install git+https://github.com/LooseLab/read_until_api_v2@master
pip install git+https://github.com/LooseLab/ru@issue15

```

### DeepNano Blitz for CPU basecalling


To install rust follow the instructions at https://rustup.rs/  
Make sure you switch to a nightly build of rust as in deepnano-blitz documentation.  
e.g. `rustup default nightly-2019-12-11`  
To install deepnano-blitz follow the instructions at https://github.com/fmfi-compbio/deepnano-blitz  
If running on a mac change [line 11 of build.rs](https://github.com/fmfi-compbio/deepnano-blitz/blob/6ac007822dccf5c97ab0e8ce2cd0eb4c1837eae8/build.rs#L11) to:

```
.arg("https://anaconda.org/intel/mkl-static/2020.0/download/osx-64/mkl-static-2020.0-intel_166.tar.bz2")

```





