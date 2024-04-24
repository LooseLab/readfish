from __future__ import annotations
import logging
import argparse
from logging.handlers import QueueHandler, QueueListener
import queue
from typing import Callable
from readfish.__about__ import __version__


def setup_logger(
    name: str,
    header: str | None = None,
    log_format: str = "%(message)s",
    log_file: str | None = None,
    log_console: bool = False,
    mode: str = "a",
    level: int = logging.DEBUG,
    propagate: bool = False,
    queue_bound: int = 100_000,
) -> logging.Logger:
    """
    Configures and returns a `logging.Logger` object with handlers specified by the values
    set in ``log_file`` and ``log_format``, specified format, and level.

    A custom header can be included if logging to a file.
    Log messages will be formatted using the provided format string.

    :param name: Name to assign to the logger.
    :param header: Optional header to write at the top of the log file.
    :param log_format: Format string for log messages using % formatting, default is "%(message)s".
    :param log_file: Path to the file where logs should be written.
    :param log_console: Whether to log to console. If True, a console StreamHandler is added.
    :param mode: Mode to use when opening the log file, default is 'a' (append).
    :param level: Logging level, where logging.LEVEL is one of (DEBUG, INFO, WARNING, ERROR, CRITICAL). Default is logging.DEBUG.
    :param propagate: Whether the logger should propagate messages to higher-level loggers, default is False.
    :param queue_bound: Maximum number of log messages to store in the queue, default is 100_000. If full, adding to queue will block until space is available.

    :returns: Configured :class:`logging.Logger` instance.

    :Example:

        >>> logger = setup_logger('my_logger', log_console=True, level=logging.INFO)
        >>> logger.info('This is an info message')

        >>> import tempfile
        >>> with tempfile.NamedTemporaryFile(mode='w+', delete=True) as tmpfile:
        ...     logger = setup_logger('my_logger', log_file=tmpfile.name, header='Time\tMessage', level=logging.INFO)


    :raises IOError: If an I/O error occurs while opening or writing to the file.

    :Note:
        - If `log_file` is specified, a QueueHandler and QueueListener will be used to send logs to the specified file.
            The Queue will be bounded, with a default size of 100_000. Putting to queue will block if full.
        - If `log_file` is specified and `log_console` is False, logs will only be recorded to the specified file.
        - If `log_console` is True, logs will be sent to console irrespective of whether `log_file` is specified.
        - If `log_file` is None and `log_console` is False, logs will be sent to a `logging.NullHandler` instance.
        - If `header` is provided and the file specified by `filename` already exists,
            the header will not be written to the file.
    """
    logger = logging.getLogger(name)
    formatter = logging.Formatter(log_format)

    if log_file is not None:
        try:
            if header is not None:
                with open(log_file, "x") as file:
                    file.write(f"{header}\n")
        except FileExistsError:
            pass  # File already exists, proceed to normal logging.
        except IOError as e:
            logging.error(f"Unable to write header to {log_file}: {e}")
        log_queue = queue.Queue(queue_bound)
        queue_handler = QueueHandler(log_queue)
        logger.addHandler(queue_handler)

        handler = logging.FileHandler(log_file, mode=mode, encoding="utf-8")
        handler.setFormatter(formatter)

        listener = QueueListener(log_queue, handler)
        listener.start()
    if log_console:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    if log_file is None and not log_console:
        logger.addHandler(logging.NullHandler())

    logger.setLevel(level)
    logger.propagate = propagate
    return logger


def print_args(
    args: argparse.Namespace,
    printer: Callable,
    exclude: list | None = None,
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
    printer(f"Version={__version__}")
