"""Mapping interface for readfish, using Minimap2 mappy, or mappy-rs (if available).
If available, mappy-rs will be used, otherwise mappy will be used.
If neither are available, an ImportError will be raised.
"""
from enum import Enum
from itertools import chain, repeat
from pathlib import Path
from typing import Optional, Iterable

from readfish._loggers import setup_logger
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
    """Wrapper for the mappy.Aligner class

    This class wraps a minimap2 python Aligner, which can be one of either the `mappy` or `mappy-rs` aligner.
    It will decide which to use by availability starting with `mappy-rs` then `mappy`.
    """

    def __init__(self, mappy_impl: Aligners, debug_log: Optional[str] = None, **kwargs):
        self.mappy_impl = mappy_impl
        self.logger = setup_logger(__name__, log_file=debug_log)
        self.aligner_params = kwargs
        self.validate()

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
        if (
            "".join(map(str.lower, Path(index).suffixes)) not in set(file_extensions)
            and index
        ):
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
        """Map an iterable of base-called data.

        All arguments are passed through to C/rust wrapper functions
        Current expected arguments:
        - basecalls: list[tuple[tuple, dict]]
        - key: function that gets FASTA sequence from the dict (keyword only)
        """
        if self.mappy_impl is Aligners.MAPPY_RS:
            iter_ = self._rust_mappy_wrapper(basecall_results)
        elif self.mappy_impl is Aligners.C_MAPPY:
            iter_ = self._c_mappy_wrapper(basecall_results)
        else:
            raise NotImplementedError("Aligner not configured")
        for result in iter_:
            paf_info = f"{result.read_id}\t{len(result.seq)}"
            for al in result.alignment_data:
                self.logger.debug(f"{paf_info}\t{al}")
            if not result.alignment_data:
                self.logger.debug(f"{paf_info}\t{UNMAPPED_PAF}")
            yield result

    def _c_mappy_wrapper(self, basecalls):
        for result in basecalls:
            result.alignment_data = list(self.aligner.map(result.seq))
            yield result

    def _rust_mappy_wrapper(self, basecalls):
        skipped = []

        def _gen(_basecalls):
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

    def describe(self, regions, barcodes) -> str:
        """
        Describe the mappy Aligner plugin instance. Returns human readable information about the plugin.

        :return: Human readable string to be logged to readfish and MinKNOW
        """
        description = []
        if self.initialised:
            description.append(
                f"Using the {self.mappy_impl.value} plugin. Using reference: {(self.aligner_params['fn_idx_in'])}.\n"
            )
            seq_names = set(self.aligner.seq_names)
            # Get total seq length of the reference.
            genome = get_contig_lengths(self.aligner)
            ref_len = sum(genome.values()) * 2
            for condition, region_or_barcode_str in chain(
                zip(regions, repeat("Region", len(regions))),
                zip(barcodes.values(), repeat("Barcode", len(barcodes))),
            ):
                unique_contigs = set(condition.targets._targets[Strand.forward].keys())
                unique_contigs.update(
                    set(condition.targets._targets[Strand.reverse].keys())
                )
                num_unique_contigs = len(unique_contigs)
                # More than one contig should be plural!
                pluralise = {1: ""}.get(num_unique_contigs, "s")
                num_in_ref_contigs = len(unique_contigs & seq_names)
                num_not_in_ref_contigs = len(unique_contigs - seq_names)
                warn_not_found = (
                    f"NOTE - The following {num_not_in_ref_contigs} {'contigs are listed as targets but have' if num_not_in_ref_contigs > 1 else 'contig is listed as a target but has'} not been found on the target reference:\n {nice_join(sorted(unique_contigs - seq_names), conjunction='and')}"
                    if num_not_in_ref_contigs
                    else ""
                )
                if warn_not_found:
                    raise SystemExit(warn_not_found)
                num_targets = count_dict_elements(condition.targets._targets)
                ref_covered = _summary_percent_reference_covered(
                    ref_len, condition.targets, genome
                )
                # add some front padding to the flowcell print out
                description.append(
                    f"""{region_or_barcode_str} {condition.name} has targets on {num_unique_contigs} contig{pluralise}, with {num_in_ref_contigs} found in the provided reference.
This {region_or_barcode_str.lower()} has {num_targets} total targets (+ve and -ve strands), covering approximately {ref_covered:.2%} of the genome.\n"""
                )
            return "\n".join(description)
        return "Aligner is not initialised yet. No reference has been provided, readfish will not proceed until the Aligner is initialised."
