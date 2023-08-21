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

## Viewing Documentation
Aside from a traditional [`README.md`](../README.md), `readfish` uses [`sphinx`](https://www.sphinx-doc.org/en/master/) to create documentation.
All documentation is kept in the `readfish/docs` directory.

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

If adding an entry point, they must also be included in [`src/readfish/_cli_base.py`](/src/readfish/_cli_base.py),adding to this `cmds` list

```python
    # add entry point here
    cmds = [
        ("targets", "targets"),
        ("barcode-targets", "targets"),
        ("unblock-all", "unblock_all"),
        ("validate", "validate"),
    ]
    # Entry point is imported during runtime, and added as a sub command to readfish
    for cmd, module in cmds:
        _module = importlib.import_module(f"readfish.entry_points.{module}")
        _parser = subparsers.add_parser(cmd, help=_module._help)
        for *flags, opts in _module._cli:
            _parser.add_argument(*flags, **opts)
        _parser.set_defaults(func=_module.run)
```

## Plugin modules

Plugin modules are designed to make `readfish` more modular.
Each Plugin module should inherit an Abstract Base Class (ABC), which define methods which **MUST** be present on the plugin.
Currently, two types of plugins can be written
 - `Caller` plugins (must inherit `CallerABC`), which wrap a base caller for calling chunks
 - `Aligner` plugins (must inherit `AlignerABC`), which wrap an aligner for making decisions on base called chunks.

These ABCs are defined in [`abc.py`](/src/readfish/plugins/abc.py).
This means that the methods which are used in `targets.py` are present, so plugins can be swapped out at run time, and function as standardised self-contained interfaces to different external tools.

If a plugin module is written and not included in `readfish` package, but another, it is possible to include it by passing the path in the `toml`.
For example:

Plugins are loaded as instances of `_PluginModules` - see https://github.com/LooseLab/readfish_dev/blob/86f962734eee5d1d364dacd053af09676622e5b6/src/readfish/_config.py#L63 for more.

```toml
[caller_settings.bar.foo]
```
This would try to load the `foo` module from the `bar` package.

```toml
[caller_settings.readfish.plugins.guppy]
```

This would load the readfish guppy `Caller` plugin explicitly.
There are instances of "builtin" plugins, which are the included `mappy` and `guppy` plugins.
These are listed in https://github.com/LooseLab/readfish_dev/blob/86f962734eee5d1d364dacd053af09676622e5b6/src/readfish/_config.py#L111.
This is how these plugins can be loaded, without passing an absolute import path to them.

Validation is left to the author of any plugins which inherits from the Aligner ABC.
Things we suggest that are validated:

 - required keys - keys that must be present in the TOML
 - correctly typed values - Values that have been passed in ar eof the correct instance
 - available input files - Check the existence of paths
 - writable outputs - Check permissions on output files


Let's dissect the structure of `mappy.py`.
Ignore the part about trying to import `mappy-rs`.

Here we define an `Aligner` class.
It is **Required** that the class name be `Aligner` for `Aligner` plugins and `Caller` for `Caller` plugins.
We inherit the `AlignerABC` class, which provides the required methods for an `Aligner`.

```python
class Aligner(AlignerABC):
    """Wrapper for the mappy.Aligner class

    This class wraps a minimap2 python Aligner, which can be one of either the
    `mappy` or `mappy-rs` aligner. It will decide which to use by availability
    starting with `mappy-rs` then `mappy`.
    """
```

Initialise the class.
We do not need to call `super().init()` as we aren't actually using the initialised `AlignerABC` just the inherited method.

```python
    # No parameters are required in a plugin Aligner class, these are the ones we needed to make this a mappy based Aligner class work.
    def __init__(
        self, readfish_config: Conf, debug_log: Optional[str] = None, **kwargs
    ):
        # Access to the config provided
        self.config = readfish_config
        # Optional output PAF alignments
        self.logger = setup_debug_logger(__name__, log_file=debug_log)
        # Additional kwargs are assumed to be for the mappy.Aligner, such as fn_idx_in, etc...
        self.aligner_params = kwargs
        # Validate the provided arguments will create a valid Aligner.
        self.validate()
        # create the mappy aligner
        self.aligner = mappy.Aligner(**self.aligner_params)  # type: ignore
```

This next method is important. `validate`

```python
def validate(self) -> None:
    """
    Check that this aligner can be initialised without any issues. Catches any problems and raises helpful errors.
    Currently checks:
        1. that the Reference (fn_idx_in) exists, IF one is provided
        2. That the reference is an .mmi file, or a FASTA or FASTQ, either uncompressed or Gzipped, IF a fn_idx_in is provided.

    :return: None, if the Aligner is setup with valid paths and permissions
    """
    index: str = self.aligner_params.get("fn_idx_in")
    file_extensions = [".fasta", ".fna", ".fsa", ".fa", ".fastq", ".fq"]
    file_extensions.extend([f"{f}.gz" for f in file_extensions])
    file_extensions.append(".mmi")
    if all((not Path(index).is_file(), index)):
        raise FileNotFoundError(f"{index} does not exist")
    if (
        "".join(map(str.lower, Path(index).suffixes)) not in set(file_extensions)
        and index
    ):
        raise RuntimeError(
            f"Provided index file appears to be of an incorrect type - should be one of {file_extensions}"
        )
```

The validate function is intended to be called in the __init__ method, before the actual `Aligner` or `Caller` is initialised. The contents of this method are left up to the author, however we suggest that people check for the things listed above.

The purpose of `validate` is to check that the given parameters will create a valid `Aligner` or `Caller`. For example, in the `guppy.py` `Caller` plugin, we check the permissions of the provided `Guppy` socket. If these are insufficient, Guppy only errors out after a 10 minute timeout. However of this is caught in `validate`, everyone ends up being left a lot happier.

Required disconnect method - we don't have any clean up to do so we just return.

```python
    def disconnect(self) -> None:
        return
```

Required initialised method.
In this case, we are initialised if the Aligner has an index loaded - which is when a `mappy.Aligner` evaluates to `true`

```python
    @property
    def initialised(self) -> bool:
        """Is the mappy Aligner initialised?

        If ``False`` the ``Aligner`` is unlikely to work for mapping.
        """
        return bool(self.aligner)
```

Here we have our first non-required function.
As this function is not used in `targets.py` This makes a decision on whether the alignment returns is on or off target.
This isn't required, but is a legible place to put this logic.
This function is why we had to pass in the `Conf` instance, so we could determine whether a read was within a target range or on a target contig.

```python
    def make_decision(self, result: Result) -> Decision:
        if result.alignment_data is None:
            result.alignment_data = []
        # Mappy misses out the first two columns on an Alignment (query name and query length), so here we recreate that
        paf_info = f"{result.read_id}\t{len(result.seq)}"
        # get the targets for this channel
        targets = self.config.get_targets(result.channel, result.barcode)
        # The alignments from mappy
        results = result.alignment_data
        matches = []
        # iterate alignments
        for al in results:
            # write out paf line into debug logger
            self.logger.debug(f"{paf_info}\t{al}")
            contig = al.ctg
            strand = al.strand
            coord = al.r_st if al.strand == -1 else al.r_en
            # targets `check_coord` checks if these alignment results are on target, return true or false
            matches.append(targets.check_coord(contig, strand, coord))
        # if any alignments were true, we have a hit!
        coord_match = any(matches)
        # no alignments, check whether had sequence
        if not results:
            self.logger.debug(f"{paf_info}\t{UNMAPPED_PAF}")
            if len(result.seq) > 0:
                return Decision.no_map
            else:
                return Decision.no_seq
        # Only one mapping - single on
        elif len(results) == 1:
            return Decision.single_on if coord_match else Decision.single_off
        # More than one mapping, multi on
        elif len(results) > 1:
            return Decision.multi_on if coord_match else Decision.multi_off
        raise ValueError()
```

The below `describe` function is required. The contents of the description string is left to the developer of any plugins - all that need be returned is a string
describe what the aligner is seeing before it starts. This will be logged in the readfish log file and MinKNOW logs,
so things to bear in mind are things that will be useful when retrospectively analysing the run.
This function is called in `targets.py` to be logged to the terminal.
This is a more complicated function, so I've commented details more thoroughly below.

```python
    def describe(self) -> str:
        """
        Describe the mappy Aligner plugin instance. Returns human readable information about the plugin.

        :return: Human readable string to be logged to readfish and MinKNOW
        """
        # List to store strings, that will be concatenated at the end and returned.
        description = []
        mappy_type = "mappy_rs" if _mappy_rs else "mappy"
        # Check we have a reference.
        if self.initialised:
            # Append first useful information.
            description.append(
                f"Using the {mappy_type} plugin. Using reference: {(self.aligner_params['fn_idx_in'])}.\n"
            )
            # All the contig names that are in the reference.
            seq_names = set(self.aligner.seq_names)
            # Get total seq length of the reference.
            ref_len = sum(len(self.aligner.seq(sn)) * 2 for sn in seq_names)
            # Print out for each region and barcode. Zip an identifying string in with the class containing the Condition data.
            for condition, region_or_barcode_str in chain(
                zip(self.config.regions, repeat("Region", len(self.config.regions))),
                zip(
                    self.config.barcodes.values(),
                    repeat("Barcode", len(self.config.barcodes)),
                ),
            ):
                # Create a set of all contigs listed as targets to get them uniquely
                unique_contigs = set(condition.targets._targets[Strand.forward].keys())
                unique_contigs.update(
                    set(condition.targets._targets[Strand.reverse].keys())
                )
                num_unique_contigs = len(unique_contigs)
                # More than one contig should be plural in the final string!
                pluralise = {1: ""}.get(num_unique_contigs, "s")
                num_in_ref_contigs = len(unique_contigs & seq_names)
                # Check all targets are in the reference.
                num_not_in_ref_contigs = len(unique_contigs - seq_names)
                warn_not_found = (
                    f"NOTE - The following {num_not_in_ref_contigs} {'contigs are listed as targets but have' if num_not_in_ref_contigs > 1 else 'contig is listed as a target but has'} not been found on the target reference:\n {nice_join(sorted(unique_contigs - seq_names), conjunction='and')}"
                    if num_not_in_ref_contigs
                    else ""
                )
                # NOTE - we raise an error if we have a contig in the targets that is not in the reference.
                if warn_not_found:
                    raise SystemExit(warn_not_found)
                # Calculate some fun stats
                num_targets = count_dict_elements(condition.targets._targets)
                num_bases_in_targets = sum_target_coverage(
                    condition.targets._targets, self.aligner
                )
                percentage_ref_covered = round(num_bases_in_targets / ref_len * 100, 2)
                # Append a useful summation of each region or barcode
                description.append(
                    f"""{region_or_barcode_str} {condition.name} has targets on {num_unique_contigs} contig{pluralise}, with {num_in_ref_contigs} found in the provided reference.
This {region_or_barcode_str.lower()} has {num_targets} total targets (+ve and -ve strands), covering approximately {percentage_ref_covered} percent of the genome.\n"""
                )
            return "\n".join(description)
        return "Aligner is not initialised yet. No reference has been provided, readfish will not proceed until the Aligner is initialised."
```

Our final required function - map_reads.
This is required, and takes in an iterable of the Results from the `Caller` plugin.

```python
    def map_reads(self, basecall_results: Iterable[Result]) -> Iterable[Result]:
        """Map an iterable of base-called data.

        All arguments are passed through to C/rust wrapper functions
        Current expected arguments:
         - C/rust:
           - basecalls: list[tuple[tuple, dict]]
           - key: function that gets FASTA sequence from the dict (keyword only)
        """
        # map using mappy_rs, our multithreaded mappy wrapper
        if _mappy_rs:
            iter_ = self._rust_mappy_wrapper(basecall_results)
        # map using mappy
        else:
            iter_ = self._c_mappy_wrapper(basecall_results)
        for result in iter_:
            result.decision = self.make_decision(result)
            yield result
```

Just a look at the `_c_mappy_wrapper` - simple function that maps using `mappy` and returns `mappy.Alignments`

```python
    def _c_mappy_wrapper(self, basecalls):
        for result in basecalls:
            result.alignment_data = list(self.aligner.map(result.seq))
            yield result
```

[contributors guide]: https://github.com/LooseLab/readfish/blob/main/.github/CONTRIBUTING.md
