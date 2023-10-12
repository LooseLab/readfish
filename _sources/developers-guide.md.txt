# Developer's guide

If you want to contribute some code to readfish, please check out the [contributors guide] on GitHub.

## Pre-commit
In order to enforce coding style, we use [pre-commit](https://pre-commit.com/).

### Installation
```console
pip install pre-commit
cd readfish
pre-commit install
pre-commit run --all-files
```

In order to run the checks automatically when committing/checking out branches, run the following command

```console
pre-commit install -t pre-commit -t post-checkout -t post-merge
```

## Readfish Installation
We use `pyproject.toml` to handle building, packaging and installation, along with [`hatch`](https://hatch.pypa.io/latest/).

Installation candidates are listed in the `pyproject.toml` like so
```toml
[project.optional-dependencies]
# Development dependencies
docs = ["sphinx-copybutton", "furo", "myst-parser", "faqtory"]
tests = ["pytest"]
dev = ["readfish[all,docs,tests]"]
# Running dependencies, this is a little bit clunky but works for now
mappy = ["mappy"]
mappy-rs = ["mappy-rs"]
guppy = ["ont_pyguppy_client_lib"]
all = ["readfish[mappy,mappy-rs,guppy]"]
```

An example install command would be `pip install readfish[all]`.

An example conda development environment is specified as:
```yaml
name: readfish_dev
channels:
  - bioconda
  - conda-forge
  - defaults
dependencies:
  - python=3.10
  - pip
  - pip:
    - -e .[dev]
```
This file is included here: [development.yml](development.yml), and can be installed in the main readfish repository like so:

With mamba:

```console
mamba env create -f docs/development.yml
```

With conda:

```console
conda env create -f docs/development.yml
```

## Readfish versioning
Readfish uses [calver](https://calver.org/) for versioning. Specifically the format should be
`YYYY.MINOR.MICRO.Modifier`, where `MINOR` is the feature addiiton, `MICRO` is any hotfix/bugfix, and `Modifier` is the modifier (e.g. `rc` for release candidate, `dev` for development, empty for stable).

## Changelog

We are generally trying to follow the guidance here. https://keepachangelog.com/en/1.0.0/

Notably we should correctly update the Unreleased section for things added in the PRs that are inbetween releases.

If possible, link the PR that introduced the change, and add a **brief** description of the change.

## Adding a simulated position for testing
```{include} ../README.md
:start-after: <!-- begin-simulate -->
:end-before: <!-- end-simulate -->
```

## Setting up a test playback experiment
```{include} ../README.md
:start-after: <!-- begin-new-playback -->
:end-before: <!-- end-new-playback -->
```


## Viewing Documentation
Aside from a traditional [`README.md`](https://github.com/LooseLab/readfish/blob/main/README.md), `readfish` uses [`sphinx`](https://www.sphinx-doc.org/en/master/) to create documentation.
All documentation is kept in the `readfish/docs` directory.

A live version is available at https://looselab.github.io/readfish/.

With an activated development readfish environment (includes `docs` dependencies), run the following to view the documentation:

```console
cd docs
make html
cd _build/html
python -m http.server 8080
```

The documentation HTML should now be available at http://0.0.0.0:8080/.

## Adding to Documentation

The main file for configuring `sphinx` is [`conf.py`](conf.py).
This file should not need altering, it sets things up for activated `sphinx` extensions, auto generated API documentation, building etc.

`sphinx` builds from `markdown` files (amongst others), with [`index.md`](index.md) as the `master_doc` page that other pages are included into.

If another markdown file is added, it should be included into the ```{toc_tree}``` directive in `index.md`.

Otherwise documentation should be written using standard `markdown`, **excepting** API documentation, which is written in `ReStructured Text`.
An example of this is `readfish.console.rst`, which auto generates a documentation page for all entry points in `readfish`.
However, the entry points to be documented must be added by a deVeLoPEr.
<!-- We can attempt to address this later -->

## Entry points

Entry points are the subcommands that `readfish` runs.
These are found in `src/readfish/entry_points`.
Excepting `validate.py`, ideally these wrap `targets.py`, which performs the bare minimum `read_until` loop, calling the Aligner and Caller plugins.

If adding an entry point, they must also be included in [`src/readfish/_cli_base.py`](../src/readfish/_cli_base.py),adding to this `cmds` list

```{literalinclude} ../src/readfish/_cli_base.py
:language: python
:lines: 30-43
```
## Plugin modules

Plugin modules are designed to make `readfish` more modular.
Each Plugin module should inherit an Abstract Base Class (ABC), which define methods which **MUST** be present on the plugin.
Currently, two types of plugins can be written
 - `Caller` plugins (must inherit `CallerABC`), which wrap a base caller for calling chunks
 - `Aligner` plugins (must inherit `AlignerABC`), which wrap an aligner for making decisions on base called chunks.

These ABCs are defined in [`abc.py`](https://github.com/LooseLab/readfish/blob/main/src/readfish/plugins/abc.py).
This means that the methods which are used in `targets.py` are present, so plugins can be swapped out at run time, and function as standardised self-contained interfaces to different external tools.

If a plugin module is written and not included in `readfish` package, but another, it is possible to include it by passing the path in the `toml`.
For example:

Plugins are loaded as instances of `_PluginModules` - see source of `_PluginModules` for more details.
```{eval-rst}
.. autoclass:: readfish._config._PluginModule
    :noindex:
```

```toml
[caller_settings.bar.foo]
```
This would try to load the `foo` module from the `bar` package.

```toml
[caller_settings.readfish.plugins.guppy]
```

This would load the readfish guppy `Caller` plugin explicitly.
There are instances of "builtin" plugins, which are the included `mappy`, `mappy_rs` and `guppy` plugins.
See the source of `readfish._config._PluginModule.load_module` for more details.
```{eval-rst}
.. automethod:: readfish._config._PluginModule.load_module
    :noindex:
```
for a list of built in modules.
This is how these plugins can be loaded, without passing an absolute import path to them.

Validation is left to the author of any plugins which inherits from the Aligner ABC.
Things we suggest that are validated:

 - required keys - keys that must be present in the TOML
 - correctly typed values - Values that have been passed in ar eof the correct instance
 - available input files - Check the existence of paths
 - writable outputs - Check permissions on output files


Let's dissect the structure of `_mappy.py`. In this case, `_mappy.py` defines shared behaviour between two Plugins, `mappy` and `mappy_rs`.
These files are in essence identical, however they use a different Aligner( mappy and mappy-rs respectively ),
and so are in separate files to allow the User to have a discrete choice between them when loading the plugin via the TOML file.

Here we define an `Aligner` class.
It is **Required** that the class name be `Aligner` for `Aligner` plugins and `Caller` for `Caller` plugins.
We inherit the `AlignerABC` class, which provides the required methods for an `Aligner`.

```{literalinclude} ../src/readfish/plugins/_mappy.py
:language: python
:lines: 30-49
```

### __init__()
Firstly, as with most python classes, we initialise the class.
We do not need to call `super().init()` as we aren't actually using the initialised `AlignerABC` just the inherited methods.

```{literalinclude} ../src/readfish/plugins/_mappy.py
:language: python
:lines: 52-73
```

### validate()

This next method is important. `validate()`

The validate function is intended to be called in the __init__ method, before the actual `Aligner` or `Caller` is initialised. The contents of this method are left up to the author, however we suggest that people check for the things listed above.

The purpose of `validate` is to check that the given parameters will create a valid `Aligner` or `Caller`. For example, in the `guppy.py` `Caller` plugin, we check the permissions of the provided `Guppy` socket. If these are insufficient, Guppy only errors out after a 10 minute timeout. However of this is caught in `validate`, everyone ends up being left a lot happier.

```{literalinclude} ../src/readfish/plugins/_mappy.py
:language: python
:lines: 75-96
```

### disconnect()

Required disconnect method - we don't have any clean up to do so we just return.

```{literalinclude} ../src/readfish/plugins/_mappy.py
:language: python
:lines: 98-99
```
### initialised()

Required `initialised`` method.
In this case, we are initialised if the Aligner has an index loaded - which is when a `mappy.Aligner` or `mappy_rs.Aligner` evaluates to `true`

```{literalinclude} ../src/readfish/plugins/_mappy.py
:language: python
:lines: 101-107
```

### map_reads()
Required function - map_reads.
This is required, and takes in an iterable of the `Results` from the `Caller` plugin.
The basecalled data present on the on the result is aligned through one of the two aligner wrapper functions
below, which set the alignments returned on the `Result` for this chunk.
The intention here is to allow the `Caller` plugin to be agnostic of the aligner used, and the `Aligner` plugin to be agnostic of the caller used,
as long as the `Result` object is properly populated.

```{literalinclude} ../src/readfish/plugins/_mappy.py
:language: python
:lines: 109-144
```

### describe()
Our final required function `describe`. The contents of the description string is left to the developer of any plugins - all that need be returned is a string
describing what the aligner is seeing before it starts. This will be logged in the readfish log file and MinKNOW logs,
so things to bear in mind are things that will be useful when retrospectively analysing the run.
This function is called in `targets.py` to be logged to the terminal.
This is a more complicated function, so I've commented details more thoroughly below.


```{literalinclude} ../src/readfish/plugins/_mappy.py
:language: python
:lines: 192-265
```

### _c_mappy_wrapper()
Just a look at the `_c_mappy_wrapper` - a simple **None required** function that maps using `mappy` and returns `mappy.Alignments`

```{literalinclude} ../src/readfish/plugins/_mappy.py
:language: python
:lines: 146-155
```

[contributors guide]: https://github.com/LooseLab/readfish/blob/main/.github/CONTRIBUTING.md
