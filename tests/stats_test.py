from pathlib import Path
import pytest

import readfish._cli_base

import re


def remove_ansi_escape_sequences(text):
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    return ansi_escape.sub("", text)


TEST_FILES = Path(__file__).parent.resolve() / "static" / "stats_test"


@pytest.fixture
def toml_file():
    return str(TEST_FILES / "yeast_summary_test.toml")


@pytest.fixture
def expected():
    return str(TEST_FILES / "expected_summary.txt")


@pytest.fixture(autouse=True)
def set_ci_env_var(monkeypatch):
    monkeypatch.setenv("CI", "True")


def _generate_test_params():
    yield from [
        (
            TEST_FILES / "yeast_summary_test.toml",
            str(TEST_FILES),
            TEST_FILES / "expected_summary.txt",
        ),
        (
            TEST_FILES / "yeast_summary_test_mappyrs.toml",
            str(TEST_FILES),
            TEST_FILES / "expected_summary.txt",
        ),
    ]


@pytest.mark.parametrize("toml_file,fastq_directory,expected", _generate_test_params())
@pytest.mark.alignment
def test_fastq_stats(capfd, toml_file, fastq_directory, expected):
    with pytest.raises(SystemExit) as exc_info:
        readfish._cli_base.main(
            [
                "stats",
                "--toml",
                str(toml_file),
                "--fastq-directory",
                str(fastq_directory),
                "--no-paf-out",
                "--no-demultiplex",
                "--no-csv",
            ]
        )
    assert exc_info.value.code == 0
    out, _err = capfd.readouterr()
    x = remove_ansi_escape_sequences(out)
    with open(expected, "rt") as fh:
        expected_message = fh.read()
    assert expected_message in x
