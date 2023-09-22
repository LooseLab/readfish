from pathlib import Path

import pytest
import os

import readfish._cli_base

TEST_DIR = Path(__file__).parent.resolve()
SEARCH_PATH = Path(TEST_DIR / "static")


def ch_file_perms():
    """
    Change the file permissions on the fake Guppy sockets, if they aren't correct.
      Most likely this is the case after a fresh clone.
      Sets the no read socket (5555_fail_nr) to allow no one to read,
      and the no write socket (5555_fail_nw) to allow no one to write.
    """

    nr_socket_path = SEARCH_PATH / "guppy_validation_test" / "fail" / "5555_fail_nr"
    nw_socket_path = SEARCH_PATH / "guppy_validation_test" / "fail" / "5555_fail_nw"

    if os.access(nr_socket_path, os.R_OK):
        os.chmod(nr_socket_path, 0o260)
    if os.access(nw_socket_path, os.W_OK):
        os.chmod(nw_socket_path, 0o460)


ch_file_perms()


def _generate_test_params(sub_dir, *args, search_path=SEARCH_PATH):
    """Find static files for this test set

    We will search the `search_path / subdir` for TOML files, then
    using those files will find corresponding `txt` files. These
    `txt` files contain messages that will be in STDERR of the func call.
    All extra args are passed through transparently.
    """
    _dir = search_path
    tomls = _dir.rglob(f"*validation_test/{sub_dir}/*.toml")
    for toml in tomls:
        stem = toml.stem
        toml = str(toml)
        errors = list(map(str, _dir.rglob(f"*validation_test/{sub_dir}/{stem}*.txt")))
        if not errors:
            raise ValueError(
                f"TOML file: {toml} has no corresponding expected messages"
            )
        yield toml, errors, *args


def zero_exit(exit_code):
    return exit_code == 0


def non_zero_exit(exit_code):
    return exit_code != 0


# Failing TOMLs, found in `fail` directory, expect a non-zero return code
FAIL_TESTS = list(_generate_test_params("fail", non_zero_exit))
# Passing TOMLs, found in `pass` directory, expect a zero return code
PASS_TESTS = list(_generate_test_params("pass", zero_exit))


@pytest.mark.alignment
@pytest.mark.parametrize("toml,error_txts,exit_check", FAIL_TESTS + PASS_TESTS)
def test_validation(capsys, toml, error_txts, exit_check):
    """Test validating TOML files

    This test will call the readfish CLI as a user would, invoking the
    `validate` sub-command.
    """
    with pytest.raises(SystemExit) as exc_info:
        readfish._cli_base.main(["validate", toml, "--no-describe"])
    assert exit_check(exc_info.value.code)
    out, err = capsys.readouterr()
    for error_txt in error_txts:
        with open(error_txt, "rt") as fh:
            expected_message = fh.read()
        assert expected_message, f"{error_txt!r} is empty"
        assert expected_message in err
