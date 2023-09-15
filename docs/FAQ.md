
# Frequently Asked Questions

<a name="connection-error-\[bad_reply\]-could-not-interpret-message-from-server-for-request:-load_config-reply:-invalid_protocol"></a>
## Connection error. \[bad_reply\] Could not interpret message from server for request: LOAD_CONFIG. Reply: INVALID_PROTOCOL

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

<a name="connection-error-\[timed_out\]-timeout-waiting-for-reply-to-request:-load_config"></a>
## Connection error. \[timed_out\] Timeout waiting for reply to request: LOAD_CONFIG

This error often stems from a couple of sources. To test your Guppy Connection you can run

```console
python -c 'from pyguppy_client_lib.pyclient import PyGuppyClient as PGC; \
           c = PGC("ipc:///tmp/.guppy/5555", "dna_r9.4.1_450bps_fast.cfg"); \
           c.connect(); print(c)'
```

Replacing the `5555` (The default guppy port) with whichever port Guppy may be running on.

The following tends to be the problem only on Computers which ar not provided by ONT, and have been set up manually. Guppy creates the socket file on which is listens as the `MinKNOW ` User, which doens't allow your User account to read/write to the socket.

To fix this, you can either add yourself to the `minknow` group and give the group write permission , or you can give everyone write permissions to the socket which is a bit less secure (Quick, but maybe try the group thing first).

To add yourself to the group and change the permissions -
```console
sudo usermod -a -G minknow $USER
```

You will then have to restart for the user/group changes to take effect!

Alternatively you can just Yolo it and run

```console
sudo chmod 775 /tmp/.guppy/5555
```

Which means any User has all permissions on this file.

Once you have done that if you run the above Python command changing the IPC port to whatever port Guppy is listening on. This is usually found in `/tmp/.guppy`, and can be seen by running `ls /tmp/.guppy`

```console
python -c 'from pyguppy_client_lib.pyclient import PyGuppyClient as PGC; \
           c = PGC("ipc:///tmp/.guppy/5555", "dna_r9.4.1_450bps_fast.cfg"); \
           c.connect(); print(c)'
```

Theoretically you should be good to go!

<a name="how-do-i-create-a-readfish-python-environment"></a>
## How do I create a readfish python environment?

We recommend using conda to manage your readfish environments, especially on ONT machines!
To install conda instructions can be found [here](https://docs.conda.io/projects/conda/en/latest/user-guide/install/index.html#regular-installation).
An explanation is found in an answer to this [issue](https://github.com/LooseLab/readfish/issues/124#issuecomment-759599319) as well.

Once Conda is installed, copy the following code snippet into a file on your system, and replace the X.X.X of the `ont-pyguppy-client-lib` with the version output of

```console
 guppy_basecall_server --version
```

You should get something like this back

    Guppy Basecall Service Software, (C) Oxford Nanopore Technologies plc. Version 6.1.5+446c35524, client-server API version 11.0.0

The important part is the first three numbers of the version, in this case `6.1.5`.

```yaml
name: readfish
channels:
  - bioconda
  - conda-forge
  - defaults
dependencies:
  - python=3.9
  - pip
  - pip:
    - git+https://github.com/nanoporetech/read_until_api@3.4.1
    - ont-pyguppy-client-lib==X.X.X
    - git+https://github.com/LooseLab/readfish@dev_staging
```

<a name="what-should-my-batch-times-look-like"></a>
## What should my batch times look like.

When running readfish, you will see output scrolling down your terminal pane to the effect of

```console
2023-01-17 19:18:57,355 ru.ru_gen 15R/0.50858s
2023-01-17 19:18:57,834 ru.ru_gen 17R/0.47959s
2023-01-17 19:18:58,333 ru.ru_gen 16R/0.49804s
2023-01-17 19:18:58,848 ru.ru_gen 21R/0.51518s
2023-01-17 19:18:59,365 ru.ru_gen 16R/0.51708s
```

What this means varies a little bit on things like what length of time your signal chunks being read by MinKNOW are, and how good the occupancy on your flow cell is.
Ideally, the time on the right here wants to be less than the amount of time your signal chunks represent.
The default chunk size is 1.0 second, but if you have reduced it just make sure the readfish batch times are roughly in line.
See [this issue repsonse](https://github.com/LooseLab/readfish/issues/221#issuecomment-1547349894) for more information.

<a name="which-branch-of-readfish-should-i-use"></a>
## Which branch of readfish should I use?

We are aware that readfish is a bit messy in terms of code branches right now (18/05/2023). Whilst we are working to bring this in to line, currently the most tried and tested version in `dev_staging`.
Watch this space for any updates!
See elsewhere in this file for installtion FAQs. 🕵️‍♂️

<hr>

Generated by [FAQtory](https://github.com/willmcgugan/faqtory)
