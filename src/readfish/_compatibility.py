"""_compatibility.py

Contains utilities for checking readfish compatibility with various versions of MinKNOW and Dorado.

Throws a warning for the last supported version of MinKNOW for this version of readfish

Checks ranges of `readfish` against the `MinKNOW` version

"""

from readfish.__about__ import __version__
from minknow_api.manager import Manager
from packaging.version import parse as parse_version
from packaging.version import Version
from minknow_api.protocol_pb2 import ProtocolRunInfo
from enum import Enum
import operator


LATEST_TESTED = "5.9.7"

# The versions of MinKNOW which this version of readfish can connect to
# Format - (lowest minknow, version of minknow not supported as an upper bound)
MINKNOW_COMPATIBILITY_RANGE = (
    Version("5.0.0"),
    Version(LATEST_TESTED),
)


class DIRECTION(Enum):
    """
    Upgrade, downgrade or just right

    """

    UPGRADE = "upgrade"
    DOWNGRADE = "downgrade"
    JUST_RIGHT = "do nothing"


def _get_minknow_version(host: str = "127.0.0.1", port: int = None) -> Version:
    """
    Get the version of MinKNOW

    :param host: The host the RPC is listening on, defaults to "127.0.0.1"
    :param port: The port the RPC is listening on, defaults to None

    :return: The version of MinKNOW readfish is connected to
    """
    manager = Manager(host=host, port=port)
    minknow_version = parse_version(manager.core_version)
    return minknow_version


def check_compatibility(
    comparator: Version,
    version_range: tuple[Version, Version],
) -> bool:
    """
    Check the compatibility of a given software version, between a given range.

    :param comparator: Version of the provided software, for example MinKNOW 5.9.7
    :param version_ranges: A tuple of lowest supported version, highest supported version
    """
    (
        lowest_supported_version,
        highest_supported_version,
    ) = version_range
    if comparator < lowest_supported_version:
        return (
            False,
            DIRECTION.DOWNGRADE,
        )
    return (
        (True, DIRECTION.JUST_RIGHT)
        if comparator <= highest_supported_version
        else (False, DIRECTION.UPGRADE)
    )


def check_basecaller_compatibility(run_information: ProtocolRunInfo, op, version: str, extra_error: str = None):
    symbol = {
        operator.lt: "<",
        operator.gt: ">",
        operator.le: "<=",
        operator.ge: ">=",
        operator.eq: "==",
        operator.ne: "!=",
    }
    guppy_version = run_information.software_versions.guppy_connected_version
    if not op(parse_version(guppy_version), parse_version(version)):
        extra_error = extra_error if extra_error is not None else ""
        raise RuntimeError(
            f"Cannot connect to base-caller {guppy_version}. This plugin requires a version of Dorado or Guppy {symbol[op]} {version}. {extra_error}"
        )
