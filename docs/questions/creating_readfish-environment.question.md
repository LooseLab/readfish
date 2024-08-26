---
title: "How do I create a readfish python environment?"
alt_titles:
  - "create conda environment for readfish"
---

We recommend using conda to manage your readfish environments, especially on ONT machines!
To install conda instructions can be found [here](https://docs.conda.io/projects/conda/en/latest/user-guide/install/index.html#regular-installation).
An explanation is found in an answer to this [issue](https://github.com/LooseLab/readfish/issues/124#issuecomment-759599319) as well.

Once Conda is installed, copy the following code snippet into a file on your system, and replace the X.X.X of the `ont-pybasecall-client-lib` with the version output of

```console
 dorado_basecall_server --version
```

You should get something like this back

    : Dorado Basecall Service Software, (C)Oxford Nanopore Technologies plc. Version 7.4.12+0e5e75c49, client-server API version 20.0.0

    Use of this software is permitted solely under the terms of the end user license agreement (EULA).
    By running, copying or accessing this software, you are demonstrating your acceptance of the EULA.
    The EULA may be found in /opt/ont/dorado/bin

The important part is the first three numbers of the version, in this case `7.4.12`.

```yaml
name: readfish
channels:
  - bioconda
  - conda-forge
  - defaults
dependencies:
  - python=3.11
  - pip
  - pip:
    - git+https://github.com/nanoporetech/read_until_api@3.4.1
    - ont-pybasecall-client-lib==X.X.X
    - git+https://github.com/LooseLab/readfish@main
```
