---
title: "Connection error. \\[bad_reply\\] Could not interpret message from server for request: LOAD_CONFIG. Reply: INVALID_PROTOCOL"
alt_titles:
  - "Error connecting to Guppy"
  - "LOAD_CONFIG error when connecting to py-guppy-client"
  - "INVALID_PROTOCOL error when connecting to Guppy"
---

This is most likely a version mismatch between `ont-pyguppy-client-lib`, the python library that enables readfish to talk to Guppy and the installed version of Guppy.

If you open a terminal and run
```console
guppy_basecall_server --version
```

You should get something like this back

    Guppy Basecall Service Software, (C) Oxford Nanopore Technologies plc. Version 6.1.5+446c35524, client-server API version 11.0.0

The important part is the first three numbers of the version, in this case `6.1.5`.

If you then activate your readfish python environment and run

```python
pip list
```

You will see a list of installed python packages. Most likely the version of `ont-pyguppy-client-lib` won't be the same version.

To fix this, simply run

```console
pip install ont-pyguppy-client-lib==X.X.X
```
where `X.X.X` is the version from the Guppy command above. So in this example the correct command would be:

`pip install ont-pyguppy-client-lib==6.1.5`.

The final thing to keep in mind is some versions of Guppy don't have a corresponding version of `ont-pyguppy-client-lib`. In this case you will get an error message which looks like

```
ERROR: Could not find a version that satisfies the requirement ont-pyguppy-client-lib==6.4.5 (from versions: 5.1.9, 5.1.10, 5.1.11, 5.1.12, 5.1.13, 5.1.15, 5.1.16, 5.1.17, 6.0.0, 6.0.1, 6.0.4, 6.0.6, 6.0.7, 6.1.1, 6.1.2, 6.1.3, 6.1.5, 6.1.6, 6.1.7, 6.2.1, 6.2.11, 6.3.2, 6.3.4, 6.3.7, 6.3.8, 6.3.9, 6.4.2)
ERROR: No matching distribution found for ont-pyguppy-client-lib==6.4.5
```
Select the closest version for you Guppy version from the list given, moving down the version numbers.

So if you had Guppy version `6.4.1` installed, you would install `ont-pyguppy-client-lib==6.3.9`, as the closest lower version.

Then you should be able to run

```console
python -c 'from pyguppy_client_lib.pyclient import PyGuppyClient as PGC; \
           c = PGC("ipc:///tmp/.guppy/5555", "dna_r9.4.1_450bps_fast.cfg"); \
           c.connect(); print(c)'
```

Good luck!

Rory
