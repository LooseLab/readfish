import pytest
from pathlib import Path
from readfish._config import Conf
import collections
from contextlib import nullcontext
from importlib.util import find_spec

TEST_DIR = Path(__file__).parent.resolve() / "static" / "describe_test"

_ALIGNER = ""
if find_spec("mappy_rs") is not None:
    _ALIGNER = "mappy_rs"

elif find_spec("mappy") is not None:
    _ALIGNER = "mappy"
else:
    raise ImportError(
        "Cannot find either `mappy-rs` nor `mappy`. One of these is required."
    )

FileSet = collections.namedtuple(
    "FileSet",
    "conf, experiment_description, aligner_expectation, caller_description",
)


def _load_conf(fn):
    # Could do try/except, but an Exception here should crash the tests
    return Conf.from_file(fn, 512, logger=None)


def _read_expected(file_path):
    """Read expected test text"""
    with open(file_path) as fh:
        return fh.read().replace("mappy_rs", _ALIGNER)


@pytest.mark.parametrize(
    "test_conf",
    [
        FileSet(
            _load_conf(TEST_DIR / "describe.toml"),
            TEST_DIR / "describe_experiment_regions_expected.txt",
            nullcontext(
                _read_expected(TEST_DIR / "describe_aligner_regions_expected.txt")
            ),
            None,
        ),
        FileSet(
            _load_conf(TEST_DIR / "describe_barcoded.toml"),
            TEST_DIR / "describe_barcoded_experiment_expected.txt",
            nullcontext(
                _read_expected(TEST_DIR / "describe_aligner_barcoded_expected.txt")
            ),
            None,
        ),
        FileSet(
            _load_conf(TEST_DIR / "describe_barcoded_missing.toml"),
            None,
            pytest.raises(SystemExit),
            None,
        ),
        FileSet(
            _load_conf(TEST_DIR / "describe_region_and_barcode.toml"),
            TEST_DIR / "describe_barcoded_regions_experiment_expected.txt",
            nullcontext(
                _read_expected(
                    TEST_DIR / "describe_aligner_barcoded_regions_expected.txt"
                )
            ),
            None,
        ),
        FileSet(
            _load_conf(TEST_DIR / "describe_region_and_barcode_missing.toml"),
            None,
            pytest.raises(SystemExit),
            None,
        ),
    ],
)
def test_describe(test_conf):
    conf = test_conf.conf
    if test_conf.experiment_description:
        with open(test_conf.experiment_description) as fh:
            assert conf.describe_experiment() == fh.read()
    if test_conf.aligner_expectation:
        al = conf.mapper_settings.load_object("Aligner")
        with test_conf.aligner_expectation as e:
            assert al.describe(conf.regions, conf.barcodes) == e
    if test_conf.caller_description:
        ca = conf.caller_settings.load_object("Caller")
        with open(test_conf.caller_description) as fh:
            assert ca.describe() == fh.read()
