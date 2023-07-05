"""Mapping interface for readfish.
"""
from typing import Optional, Iterable

from readfish._config import Conf
from readfish._loggers import setup_debug_logger
from readfish.plugins.abc import AlignerABC
from readfish.plugins.utils import Decision, Result

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
        self.aligner = mappy.Aligner(**self.aligner_params)  # type: ignore
        if _mappy_rs:
            threads = self.aligner_params.get("n_threads", 1)
            self.enable_threading(threads)

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
