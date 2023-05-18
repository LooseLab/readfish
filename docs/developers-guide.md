# Developer's guide

## Pre-commit
In order to enforce coding style, we use [pre-commit](https://pre-commit.com/).

#### Installation
```bash
pip install pre-commit
cd readfish
pre-commit install
pre-commit run --all-files
```

In order to run the checks automatically when commiting/checking out branches, run the following command

```bash
pre-commit install -t pre-commit -t post-checkout -t post-merge
```

## Installation

```console
virtualenv ...
```



## Plugin modules
