from pathlib import Path

import pytest

import readfish._cli_base

TEST_DIR = Path(__file__).parent.resolve()
TEST_NAME = Path(__file__).stem
SEARCH_PATH = Path(TEST_DIR / "static" / TEST_NAME)


def _generate_test_params(sub_dir, *args, search_path=SEARCH_PATH):
    """Find static files for this test set

    We will search the `search_path / subdir` for TOML files, then
    using those files will find corresponding `txt` files. These
    `txt` files contain messages that will be in STDERR of the func call.
    All extra args are passed through transparently.
    """
    _dir = search_path / sub_dir
    stems = set(p.stem for p in _dir.glob("*.toml"))
    for stem in stems:
        toml = str(_dir / f"{stem}.toml")
        errors = list(map(str, _dir.glob(f"{stem}*.txt")))
        if not errors:
            raise ValueError(
                f"TOML file: {toml} has no corresponding expected messages"
            )
        yield toml, errors, *args


# Failing TOMLs, found in `fail` directory, expect a non-zero return code
FAIL_TESTS = list(_generate_test_params("fail", lambda c: c != 0))
# Passing TOMLs, found in `pass` directory, expect a zero return code
PASS_TESTS = list(_generate_test_params("pass", lambda c: c == 0))


@pytest.mark.parametrize("toml,error_txts,exit_check", FAIL_TESTS + PASS_TESTS)
def test_validation(capsys, toml, error_txts, exit_check):
    """Test validating TOML files

    This test will call the readfish CLI as a user would, invoking the
    `validate` sub-command.
    """
    with pytest.raises(SystemExit) as exc_info:
        readfish._cli_base.main(["validate", toml, "--check-plugins"])
    assert exit_check(exc_info.value.code)
    out, err = capsys.readouterr()
    for error_txt in error_txts:
        with open(error_txt, "rt") as fh:
            expected_message = fh.read()
        assert expected_message, f"{error_txt!r} is empty"
        assert expected_message in err
