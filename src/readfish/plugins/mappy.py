from functools import partial

from readfish.plugins._mappy import Aligners, _Aligner

Aligner = partial(_Aligner, Aligners.C_MAPPY)
