"""Mapping interface for readfish, using Minimap2 mappy, or mappy-rs as dictated by the experiment TOML
`mapper_settings.<PLUGIN>` section. See {ref}`plugin configuration <plugins-config>` section.
"""

from __future__ import annotations
from enum import Enum
from itertools import chain, repeat
from pathlib import Path
from typing import Optional, Iterable

from readfish._loggers import setup_logger
from readfish._config import Barcode, Region
from readfish.plugins.abc import AlignerABC
from readfish.plugins.utils import (
    Result,
    Strand,
    count_dict_elements,
    get_contig_lengths,
    _summary_percent_reference_covered,
)
from readfish._utils import nice_join


UNMAPPED_PAF = "0\t0\t*\t*\t0\t0\t0\t0\t0\t0"


class Aligners(Enum):
    C_MAPPY = "mappy"
    MAPPY_RS = "mappy_rs"


class _Aligner(AlignerABC):
    """
    A wrapper class for mappy.Aligner providing an interface to either `mappy` or `mappy-rs` aligner implementations.

    :param Aligners mappy_impl: Specifies which mappy implementation to use, represented by an `Aligners` enum instance.
    :param Optional[str] debug_log: Specifies the file to log debug information to. If `None`, no logging is performed.
    :param kwargs: Additional keyword arguments to be passed to the mappy aligner constructor.

    :raises ValueError: When an invalid `mappy_impl` value is provided.

    Example:
        .. code-block:: python

            aligner = _Aligner(mappy_impl=Aligners.C_MAPPY, debug_log="debug.log", preset="map-ont")

    .. note::
        The actual aligner instance is created during initialization based on the provided `mappy_impl`, and is accessible via the `aligner` attribute of the instance.

    .. seealso::
        {ref}`plugin configuration <plugins-config>` for details on how `mappy_impl` is determined from the experiment TOML configuration.
    """

    def __init__(self, mappy_impl: Aligners, debug_log: Optional[str] = None, **kwargs):
        # Variant of the mappy aligner to use - `mappy` or `mappy_rs`
        self.mappy_impl = mappy_impl
        # Setup logger with the provided debug_log file, or a null logger if no file is provided.
        self.logger = setup_logger(__name__, log_file=debug_log)
        self.aligner_params = kwargs
        # Validate the provided arguments will create a valid Aligner.
        self.validate()
        # Import selected aligner and Initialise it
        if self.mappy_impl is Aligners.C_MAPPY:
            import mappy

            self.aligner = mappy.Aligner(**self.aligner_params)
        elif self.mappy_impl is Aligners.MAPPY_RS:
            import mappy_rs

            self.aligner = mappy_rs.Aligner(**self.aligner_params)
            threads = self.aligner_params.get("n_threads", 1)
            self.aligner.enable_threading(threads)
        else:
            raise ValueError("Nu uh")

    def validate(self) -> None:
        """
        Check that this aligner can be initialised without any issues. Catches any problems and raises helpful errors.
        Currently checks:
         1. that the Reference (fn_idx_in) exists, IF one is provided
         2. That the reference is an .mmi file, or a FASTA or FASTQ, either uncompressed or Gzipped, IF a fn_idx_in is provided.

        :return: None, if the Aligner is setup with valid paths and permissions
        """
        index: str = self.aligner_params["fn_idx_in"]
        file_extensions = [".fasta", ".fna", ".fsa", ".fa", ".fastq", ".fq"]
        file_extensions.extend([f"{f}.gz" for f in file_extensions])
        file_extensions.append(".mmi")
        if all((not Path(index).is_file(), index)):
            raise FileNotFoundError(f"{index} does not exist")
        if not any(index.lower().endswith(suffix) for suffix in file_extensions):
            raise RuntimeError(
                f"Provided index file appears to be of an incorrect type - should be one of {file_extensions}"
            )

    def disconnect(self) -> None:
        return

    @property
    def initialised(self) -> bool:
        """Is the mappy Aligner initialised?

        If ``False`` the ``Aligner`` is unlikely to work for mapping.
        """
        return bool(self.aligner)

    def map_reads(self, basecall_results: Iterable[Result]) -> Iterable[Result]:
        """
        Maps an iterable of base-called data using either the C `mappy` or `mappy-rs` Rust implementation,
        based on the `mappy_impl` provided during the instantiation of the class.

        :param Iterable[Result] basecall_results: An iterable of basecalled read results to be mapped.
        :return: An iterable of mapped read results.

        :raises NotImplementedError: If the aligner is not configured (i.e., if `mappy_impl` is neither `Aligners.MAPPY_RS` nor `Aligners.C_MAPPY`).

        Example:
            .. code-block:: python

                mapped_results = aligner.map_reads(basecall_results)

        .. note::
            This method logs the mapping results or `UNMAPPED_PAF` for unmapped reads,
            and the actual mapping is performed by `_c_mappy_wrapper` or `_rust_mappy_wrapper` methods based on the `mappy_impl`.
        """
        # Map with MAPPY_RS
        if self.mappy_impl is Aligners.MAPPY_RS:
            iter_ = self._rust_mappy_wrapper(basecall_results)
        # Map with MAPPY
        elif self.mappy_impl is Aligners.C_MAPPY:
            iter_ = self._c_mappy_wrapper(basecall_results)
        else:
            raise NotImplementedError("Aligner not configured")
        # Iterate over the results and log them, then yield, now with Alignment data
        # If there were alignments
        for result in iter_:
            paf_info = f"{result.read_id}\t{len(result.seq)}"
            for al in result.alignment_data:
                self.logger.debug(f"{paf_info}\t{al}")
            if not result.alignment_data:
                self.logger.debug(f"{paf_info}\t{UNMAPPED_PAF}")
            yield result

    def _c_mappy_wrapper(self, basecalls: Iterable[Result]) -> Result:
        """
        A private method to map an iterable of base-called data using the C minimap2 `mappy` implementation.

        :param Iterable[Result] basecalls: An iterable of basecalled read results to be mapped.
        :return: A generator yielding mapped read results.
        """
        for result in basecalls:
            result.alignment_data = list(self.aligner.map(result.seq))
            yield result

    def _rust_mappy_wrapper(self, basecalls: Iterable[Result]) -> Result:
        """
        A private method to map an iterable of base-called data using the `mappy-rs`
        multithreaded Rust implementation of mappy.

        :param Iterable[Result] basecalls: An iterable of basecalled read results to be mapped.
        :return: A generator yielding mapped read results, including those skipped due to the absence of sequences.

        Example:
            .. code-block:: python

                mapped_results = list(aligner._rust_mappy_wrapper(basecall_results))

        .. note::
            Skipped reads, ones with no sequences, are yielded last with empty alignment data.
        """
        skipped = []

        def _gen(_basecalls):
            """Create dictionaries of sequences and metadata for the Rust mappy aligner."""
            for result in _basecalls:
                fa = result.seq
                if not fa:
                    skipped.append(result)
                    continue
                yield {"seq": fa, "meta": result}

        recv = self.aligner.map_batch(_gen(basecalls))
        for mappings, sent_data in recv:
            result = sent_data["meta"]
            result.alignment_data = mappings
            yield result
        for result in skipped:
            result.alignment_data = []
            yield result

    def describe(self, regions: list[Region], barcodes: list[Barcode]) -> str:
        """
        Provides a human-readable description of the mappy Aligner plugin instance. This description
        includes details about the plugin, the reference used, target regions, and barcodes, making it useful
        for logging and debugging purposes.

        :param list[Region] regions: A list of regions to be described.
        :param list[Barcode] barcodes: A list of barcodes to be described.
        :return: A formatted string containing detailed, human-readable information about the regions, barcodes,
                and the state of the Aligner instance.
        :raises SystemExit: If there are contigs listed as targets but not found in the target reference.

        Example:
            .. code-block:: python

                description = aligner.describe(regions, barcodes)
                print(description)

        .. note::
            The description generated by this method is intended for logging to readfish and MinKNOW and provides
            insights into the configuration and status of the aligner instance, reference used, and target specifics.
            If the Aligner is not initialised yet, it will return a message indicating that no reference has been
            provided, and the Aligner needs initialisation before proceeding.
        """
        # List to store strings, that will be concatenated at the end and returned.
        description = []
        # Check we have a reference.
        if self.initialised:
            description.append(
                f"Using the {self.mappy_impl.value} plugin. Using reference: {(self.aligner_params['fn_idx_in'])}.\n"
            )
            # All the contig names that are in the reference.
            seq_names = set(self.aligner.seq_names)
            # Get total seq length of the reference.
            genome = get_contig_lengths(self.aligner)
            # Ref len for tow strands
            ref_len = sum(genome.values()) * 2
            # Print out for each region and barcode. Zip an identifying string in with the class containing the Condition data.
            for condition, region_or_barcode_str in chain(
                zip(regions, repeat("Region", len(regions))),
                zip(barcodes.values(), repeat("Barcode", len(barcodes))),
            ):
                # Create a set of all contigs listed as targets so contigs are unique
                unique_contigs = set(condition.targets._targets[Strand.forward].keys())
                unique_contigs.update(
                    set(condition.targets._targets[Strand.reverse].keys())
                )
                num_unique_contigs = len(unique_contigs)
                # More than one contig should be plural!
                pluralise = {1: ""}.get(num_unique_contigs, "s")
                num_in_ref_contigs = len(unique_contigs & seq_names)
                # Check all targets are in the reference.
                num_not_in_ref_contigs = len(unique_contigs - seq_names)
                # NOTE - we raise an error if we have a contig in the targets that is not in the reference.
                warn_not_found = (
                    f"NOTE - The following {num_not_in_ref_contigs} {'contigs are listed as targets but have' if num_not_in_ref_contigs > 1 else 'contig is listed as a target but has'} not been found on the target reference:\n {nice_join(sorted(unique_contigs - seq_names), conjunction='and')}"
                    if num_not_in_ref_contigs
                    else ""
                )
                if warn_not_found:
                    raise SystemExit(warn_not_found)
                # Calculate some fun stats - this could just count from the `iter_targets` method, but this is more fun.
                num_targets = count_dict_elements(condition.targets._targets)
                ref_covered = _summary_percent_reference_covered(
                    ref_len, condition.targets, genome
                )
                # Append a nicely formatted summation for each region or barcode
                description.append(
                    f"""{region_or_barcode_str} {condition.name} has targets on {num_unique_contigs} contig{pluralise}, with {num_in_ref_contigs} found in the provided reference.
This {region_or_barcode_str.lower()} has {num_targets} total targets (+ve and -ve strands), covering approximately {ref_covered:.2%} of the genome.\n"""
                )
            # Join the list of strings together with newlines and return.
            return "\n".join(description)
        return "Aligner is not initialised yet. No reference has been provided, readfish will not proceed until the Aligner is initialised."
