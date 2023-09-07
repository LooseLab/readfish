"""Mapping interface for readfish, using Minimap2 mappy, or mappy-rs (if available).
If available, mappy-rs will be used, otherwise mappy will be used.
If neither are available, an ImportError will be raised.
"""
from itertools import chain, repeat
from pathlib import Path
from typing import Optional, Iterable

from readfish._config import Conf
from readfish._loggers import setup_debug_logger
from readfish.plugins.abc import AlignerABC
from readfish.plugins.utils import (
    Decision,
    Result,
    Strand,
    _summary_percent_reference_covered,
    count_dict_elements,
)
from readfish._utils import nice_join

_mappy_rs = False
try:
    import mappy_rs as mappy

    _mappy_rs = True
except ImportError:
    mappy = None

if mappy is None:
    try:
        import mappy
    except ImportError:
        raise ImportError(
            "Cannot find either `mappy-rs` nor `mappy`. One of these is required."
        )

UNMAPPED_PAF = "0\t0\t*\t*\t0\t0\t0\t0\t0\t0"


class Aligner(AlignerABC):
    """Wrapper for the mappy.Aligner class

    This class wraps a minimap2 python Aligner, which can be one of either the `mappy` or `mappy-rs` aligner.
    It will decide which to use by availability starting with `mappy-rs` then `mappy`.
    """

    def __init__(
        self, readfish_config: Conf, debug_log: Optional[str] = None, **kwargs
    ):
        self.config = readfish_config
        self.logger = setup_debug_logger(__name__, log_file=debug_log)
        self.aligner_params = kwargs
        self.validate()
        self.aligner = mappy.Aligner(**self.aligner_params)  # type: ignore
        if _mappy_rs:
            threads = self.aligner_params.get("n_threads", 1)
            self.enable_threading(threads)

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

    @property
    def has_multithreading(self) -> bool:
        """Is this Aligner capable of multi-threaded mapping"""
        return _mappy_rs

    def enable_threading(self, threads: int) -> None:
        """Pass through for mappy_rs.Aligner.enable_threading

        Will raise a RuntimeError if not using `mappy-rs`
        """
        if self.has_multithreading:
            self.aligner.enable_threading(threads)
        else:
            raise RuntimeError("Not using mappy-rs, can't use multithreading")

    def make_decision(self, result: Result) -> Decision:
        if result.alignment_data is None:
            result.alignment_data = []
        paf_info = f"{result.read_id}\t{len(result.seq)}"
        targets = self.config.get_targets(result.channel, result.barcode)
        results = result.alignment_data
        matches = []
        for al in results:
            self.logger.debug(f"{paf_info}\t{al}")
            contig = al.ctg
            strand = al.strand
            coord = al.r_st if al.strand == -1 else al.r_en
            matches.append(targets.check_coord(contig, strand, coord))
        coord_match = any(matches)

        if not results:
            self.logger.debug(f"{paf_info}\t{UNMAPPED_PAF}")
            if len(result.seq) > 0:
                return Decision.no_map
            else:
                return Decision.no_seq
        elif len(results) == 1:
            return Decision.single_on if coord_match else Decision.single_off
        elif len(results) > 1:
            return Decision.multi_on if coord_match else Decision.multi_off
        raise ValueError()

    def map_reads(self, basecall_results: Iterable[Result]) -> Iterable[Result]:
        """Map an iterable of base-called data.

        All arguments are passed through to C/rust wrapper functions
        Current expected arguments:
        - basecalls: list[tuple[tuple, dict]]
        - key: function that gets FASTA sequence from the dict (keyword only)
        """
        if _mappy_rs:
            iter_ = self._rust_mappy_wrapper(basecall_results)
        else:
            iter_ = self._c_mappy_wrapper(basecall_results)
        for result in iter_:
            result.decision = self.make_decision(result)
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

    def describe(self) -> str:
        """
        Describe the mappy Aligner plugin instance. Returns human readable information about the plugin.

        :return: Human readable string to be logged to readfish and MinKNOW
        """
        description = []
        mappy_type = "mappy_rs" if _mappy_rs else "mappy"
        if self.initialised:
            description.append(
                f"Using the {mappy_type} plugin. Using reference: {(self.aligner_params['fn_idx_in'])}.\n"
            )
            seq_names = set(self.aligner.seq_names)
            # Get total seq length of the reference.
            ref_len = sum(len(self.aligner.seq(sn)) * 2 for sn in seq_names)
            # Print out for each region
            for condition, region_or_barcode_str in chain(
                zip(self.config.regions, repeat("Region", len(self.config.regions))),
                zip(
                    self.config.barcodes.values(),
                    repeat("Barcode", len(self.config.barcodes)),
                ),
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
                percentage_ref_covered = _summary_percent_reference_covered(
                    ref_len, condition.targets._targets, self.aligner
                )
                # add some front padding to the flowcell print out
                description.append(
                    f"""{region_or_barcode_str} {condition.name} has targets on {num_unique_contigs} contig{pluralise}, with {num_in_ref_contigs} found in the provided reference.
This {region_or_barcode_str.lower()} has {num_targets} total targets (+ve and -ve strands), covering approximately {percentage_ref_covered} percent of the genome.\n"""
                )
            return "\n".join(description)
        return "Aligner is not initialised yet. No reference has been provided, readfish will not proceed until the Aligner is initialised."
