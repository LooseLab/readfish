# random_classifier.py
from __future__ import annotations

import random
from typing import Iterable, Optional

from readfish._config import Barcode, Region
from readfish._loggers import setup_logger
from readfish.plugins.abc import AlignerABC
from readfish.plugins.utils import Decision, Result


class Aligner(AlignerABC):

    def __init__(self, fraction_keep=0.5, seed=None, debug_log=None, **kwargs):
        self.fraction_keep = fraction_keep
        self.rng = random.Random(seed)
        self.logger = setup_logger(__name__, log_file=debug_log)

    def validate(self) -> None:
        if not 0.0 <= self.fraction_keep <= 1.0:
            raise ValueError(f"fraction_keep must be between 0.0 and 1.0, got {self.fraction_keep}")

    def disconnect(self) -> None:
        pass

    @property
    def initialised(self) -> bool:
        return True          # ← add this

    def map_reads(self, basecall_results):
        for result in basecall_results:
            if self.rng.random() < self.fraction_keep:
                result.decision = Decision.single_on
                self.logger.debug("KEEP\tread_id=%s\tchannel=%s", result.read_id, result.channel)
            else:
                result.decision = Decision.no_map
                self.logger.debug("REJECT\tread_id=%s\tchannel=%s", result.read_id, result.channel)
            yield result

    def describe(self, regions, barcodes) -> str:
        return (
            f"Random classifier plugin active.\n"
            f"  Keeping {self.fraction_keep:.0%} of reads randomly.\n"
            f"  Seed: {self.rng.getstate()[1][0]}.\n"
            f"  *** TEST PLUGIN — replace with BERTax before real sequencing. ***"
        )
