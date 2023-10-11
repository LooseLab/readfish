---
title: "How do I create a readfish python environment?"
alt_titles:
  - "create conda environment for readfish"
---

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
    - git+https://github.com/LooseLab/readfish@main
```
