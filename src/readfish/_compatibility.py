"""_compatibility.py

Contains utilities for checking readfish compatibility with various versions of MinKNOW.

Checks ranges of `readfish` against the `MinKNOW` version

Attributes:
    LATEST_TESTED (str): The latest tested version of MinKNOW.
    MINKNOW_COMPATIBILITY_RANGE (tuple): The compatibility range of MinKNOW versions for this version of readfish.
    DIRECTION (Enum): An enumeration representing upgrade, downgrade, or no change directions.

"""

from __future__ import annotations

from enum import Enum

from minknow_api.manager import Manager
from packaging.version import parse as parse_version
from packaging.version import Version

LATEST_TESTED = "5.9.7"

# The versions of MinKNOW which this version of readfish can connect to
# Format - (lowest minknow version, highest version of minknow supported as an upper bound)
MINKNOW_COMPATIBILITY_RANGE = (
    Version("5.0.0"),
    Version(LATEST_TESTED),
)


class DIRECTION(Enum):
    """
    Represents the direction in which the version of the readfish software should be changed
    to be compatible with the tested version of an external tool (likely MinKNOW).

    Attributes:
        UPGRADE: Indicates that the readfish software version should be upgraded.
        DOWNGRADE: Indicates that the readfish software version should be downgraded.
        JUST_RIGHT: Indicates that the readfish software version is already compatible
                     with the tested version of the external tool.
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
    version_range: tuple[Version, Version] = MINKNOW_COMPATIBILITY_RANGE,
) -> DIRECTION:
    """
    Check the compatibility of a given software version, between a given range,
    inclusive of the right edge.

    :param comparator: Version of the provided software, for example MinKNOW 5.9.7
    :param version_ranges: A tuple of lowest supported version, highest supported version

    :return: A direction variant indicating if this version of readfish needs to be changed.

    Examples:
    >>> from packaging.version import Version
    >>> check_compatibility(Version("5.9.5"), (Version("5.0.0"), Version("5.9.7")))
    <DIRECTION.JUST_RIGHT: 'do nothing'>
    >>> check_compatibility(Version("5.9.7"), (Version("5.0.0"), Version("5.9.7")))
    <DIRECTION.JUST_RIGHT: 'do nothing'>
    >>> check_compatibility(Version("5.9.8"), (Version("5.0.0"), Version("5.9.7")))
    <DIRECTION.UPGRADE: 'upgrade'>
    >>> check_compatibility(Version("4.9.0"), (Version("5.0.0"), Version("5.9.7")))
    <DIRECTION.DOWNGRADE: 'downgrade'>
    >>> if (action := check_compatibility(Version("6.0.0"), MINKNOW_COMPATIBILITY_RANGE)) in (
    ...     DIRECTION.UPGRADE,
    ...     DIRECTION.DOWNGRADE,
    ... ):
    ...     action
    <DIRECTION.UPGRADE: 'upgrade'>
    """
    (
        lowest_supported_version,
        highest_supported_version,
    ) = version_range
    if comparator < lowest_supported_version:
        return DIRECTION.DOWNGRADE
    return (
        DIRECTION.JUST_RIGHT
        if comparator <= highest_supported_version
        else DIRECTION.UPGRADE
    )
