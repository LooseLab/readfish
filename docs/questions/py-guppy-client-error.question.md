---
title: "Connection error. \\[timed_out\\] Timeout waiting for reply to request: LOAD_CONFIG"
alt_titles:
  - "Error connecting to Guppy"
  - "LOAD_CONFIG error when connecting to py-guppy-client"
  - "LOAD_CONFIG error when connecting to Guppy"
---

N.B. The answer below was taken from this [issue](https://github.com/LooseLab/readfish/issues/221#issuecomment-1375673490)
Theoretically this should be caught in the latest readfish release, but if you are still having issues, please try the below.

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
