import os
from pathlib import Path


def reset_file_perms():
    """
    Change the socket file 5555_fail_nr back to read permissions - otherwise git/pre-commit has issues with it.

    """
    TEST_DIR = Path(__file__).parent.resolve()
    SEARCH_PATH = Path(TEST_DIR / "static")
    nr_socket_path = SEARCH_PATH / "guppy_validation_test" / "fail" / "5555_fail_nr"
    os.chmod(nr_socket_path, 0o660)


def pytest_sessionfinish(session, exitstatus):
    """whole test run finishes."""
    reset_file_perms()
