from __future__ import annotations
import logging
import argparse
from pathlib import Path
from typing import Optional, Callable, List


def setup_logger(
    name: str,
    log_format: str = "%(message)s",
    log_file: Optional[str] = None,
    log_console: bool = False,
    mode: str = "a",
    level: int = logging.DEBUG,
    propagate: bool = False,
) -> logging.Logger:
    """Setup loggers

    :param name: Name to give the logger
    :param log_format: logging format string using % formatting
    :param log_file: File to record logs to, sys.stderr if not set
    :param log_console: Add a console streamhandler, will be used if True or `log_file` is None
    :param mode: Mode to use for FileHandler, default is 'a'
    :param level: Where logging.LEVEL is one of (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    :param propagate: Pass through for logger.propagate, default is False

    :returns: :class:`logging.Logger` instance
    """
    logger = logging.getLogger(name)
    formatter = logging.Formatter(log_format)

    if log_file is not None:
        handler = logging.FileHandler(log_file, mode=mode)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    if log_console or log_file is None:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.setLevel(level)
    logger.propagate = propagate
    return logger


def setup_debug_logger(
    name: str,
    log_file: Optional[str] = None,
    header: Optional[str] = None,
    **kwargs,
) -> logging.Logger:
    """This function sets up a logger for debugging purposes.

    If a log file is specified a new logger
    is created with the specified name and log file. If the log file does not
    exist, an optional header string is added to the log file this is intended
    to be CSV column names or a comment on the file. If no ``log_file`` is specified,
    the function returns a disabled logger.

    :param name: The name of the logger to set up.
    :param log_file: The file path to write logs to. If not specified, a disabled logger will be returned.
    :param header: A string to write to the log file if a new file is created, will not be used if the ``log_file`` already exists.
    :param kwargs: Additional keyword arguments to pass to the :func:`setup_logger` function if a ``log_file`` is specified.

    :returns: A :class:`logging.Logger` object.
    """
    if log_file is not None:
        file_exists = Path(log_file).is_file()
        logger = setup_logger(name, log_file=log_file, **kwargs)
        if not file_exists and header is not None:
            logger.debug(header)
    else:
        logger = logging.getLogger(name)
        logger.disabled = True
    return logger


def print_args(
    args: argparse.Namespace,
    printer: Callable,
    exclude: Optional[List] = None,
) -> None:
    """
    Prints and formats all arguments from the command line. Takes all entirely lowercase
    attributes of ``args`` and prints them using the provided printer function (expected to be :func:`print` or :meth:`logging.Logger.info`). The exclude
    parameter can be used to exclude certain attributes from being printed.

    :param args: The command line arguments object to print.
    :param printer: A function to print the arguments. This function should take a single string argument.
    :param exclude: A list of attribute names to exclude from the output.
    """
    if exclude is None:
        exclude = []
    for attr in dir(args):
        if attr[0] != "_" and attr not in exclude and attr.lower() == attr:
            printer(f"{attr}={getattr(args, attr)!r}")
