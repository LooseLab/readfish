"""Guppy plugin module

Extension of pyguppy Caller that maintains a connection to the basecaller
"""
from __future__ import annotations
import logging
import os
import time
from collections import namedtuple
from pathlib import Path
from typing import Iterable, TYPE_CHECKING

import numpy as np
import numpy.typing as npt
from pyguppy_client_lib.helper_functions import package_read
from pyguppy_client_lib.pyclient import PyGuppyClient

from readfish._loggers import setup_debug_logger
from readfish.plugins.abc import CallerABC
from readfish.plugins.utils import Result
from readfish._config import Conf


if TYPE_CHECKING:
    import minknow_api

__all__ = ["Caller"]

logger = logging.getLogger("RU_basecaller")
CALIBRATION = namedtuple("calibration", "scaling offset")


class DefaultDAQValues:
    """Provides default calibration values

    Mimics the read_until_api calibration dict value from
    https://github.com/nanoporetech/read_until_api/blob/2319bbe/read_until/base.py#L34
    all keys return scaling=1.0 and offset=0.0
    """

    calibration = CALIBRATION(1.0, 0.0)

    def __getitem__(self, _):
        return self.calibration


_DefaultDAQValues = DefaultDAQValues()


class Caller(CallerABC):
    def __init__(
        self, readfish_config: Conf, readuntil_connection=None, debug_log=None, **kwargs
    ):
        self.logger = setup_debug_logger("readfish_guppy_logger", log_file=debug_log)
        self.config = readfish_config
        self.readuntil_connection = readuntil_connection

        # Set our own priority
        self.guppy_params = kwargs
        self.guppy_params["priority"] = PyGuppyClient.high_priority
        # Set our own client name to appear in the guppy server logs
        self.guppy_params["client_name"] = "Readfish_connection"
        self.validate()
        self.caller = PyGuppyClient(**self.guppy_params)
        self.caller.connect()

    def validate(self) -> None:
        """Validate the parameters passed to Guppy to ensure they will initialise PyGuppy Client correctly

        Currently checks:
            1. That the socket file exists
            2. That the Socket file has the correct permissions
            3. That the version of py guppy client lib installed matches the system version
        :return: None, if the parameters pass all the checks
        """
        for key in ("address", "config"):
            if key not in self.guppy_params:
                raise KeyError(
                    f"Required `caller_settings.guppy` {key} was not found in provided TOML. Please add."
                )
        if self.guppy_params["address"].startswith("ipc://"):
            # User is attempting to connect to an IPC socket
            socket_path = Path(self.guppy_params["address"][6:])
            if not socket_path.exists():
                raise FileNotFoundError(
                    f"The provided guppy base-caller socket address doesn't appear to exist. Please check your Guppy Settings. {self.guppy_params['address']}"
                )

            # check user permissions:
            if not os.access(socket_path, os.R_OK):
                raise RuntimeError(
                    f"The user account running readfish doesn't appear to have permissions to read the guppy base-caller socket. Please check permissions on {self.guppy_params['address']}. See https://github.com/LooseLab/readfish/issues/221#issuecomment-1375673490 for more information."
                )
            if not os.access(socket_path, os.W_OK):
                raise RuntimeError(
                    f"The user account running readfish doesn't appear to have permissions to write to the guppy base-caller socket. Please check permissions on {self.guppy_params['address']}. See https://github.com/LooseLab/readfish/issues/221#issuecomment-1375673490 for more information."
                )
        ### If we are connected to a live run, test if the basecaller model is acceptable.
        if self.readuntil_connection:
            if (
                self.guppy_params["config"]
                not in self.readuntil_connection.connection.protocol.get_run_info()
                .meta_info.tags["available basecall models"]
                .array_value
            ):
                raise RuntimeError(
                    f"The basecalling model you have selected is not suitable for this flowcell and kit. Please check your settings.\n You selected {self.guppy_params['config']}.\n It should be one of {self.readuntil_connection.connection.protocol.get_run_info().meta_info.tags['available basecall models'].array_value}"
                )
        return None

    def disconnect(self) -> None:
        """Call the disconnect method on the PyGuppyClient"""
        return self.caller.disconnect()

    def basecall(
        self,
        reads: Iterable[tuple[int, minknow_api.data_pb2.GetLiveReadsResponse.ReadData]],
        signal_dtype: npt.DTypeLike,
        daq_values: dict[int, namedtuple] = None,
    ):
        """Basecall live data from minknow RPC

        :param reads: List or generator of tuples containing (channel, MinKNOW.rpc.Read)
        :param signal_dtype: Numpy dtype of the raw data
        :param daq_values: Dictionary mapping channel to offset and scaling values.
                           If not provided default values of 1.0 and 0.0 are used.
        :yield:
        :rtype: readfish.plugins.utils.Result
        """
        # FIXME: Occasionally guppy can report a read as not sent when it is
        #        successfully sent. Therefore we capture not sent reads
        cache, skipped = {}, {}
        reads_received, reads_sent = 0, 0
        daq_values = _DefaultDAQValues if daq_values is None else daq_values

        for channel, read in reads:
            # Attach the "RF-" prefix
            read_id = f"RF-{read.id}"
            t0 = time.time()
            cache[read_id] = (channel, read.number, t0)
            success = self.caller.pass_read(
                package_read(
                    read_id=read_id,
                    raw_data=np.frombuffer(read.raw_data, signal_dtype),
                    daq_offset=daq_values[channel].offset,
                    daq_scaling=daq_values[channel].scaling,
                )
            )
            if not success:
                logging.warning(f"Could not send read {read_id!r} to Guppy")
                # FIXME: This is resolved in later versions of guppy.
                skipped[read_id] = cache.pop(read_id)
                continue
            else:
                reads_sent += 1

            sleep_time = self.caller.throttle - t0
            if sleep_time > 0:
                time.sleep(sleep_time)

        while reads_received < reads_sent:
            results = self.caller.get_completed_reads()
            # TODO: incorporate time_received into logging?
            # time_received = time.time()

            if not results:
                time.sleep(self.caller.throttle)
                continue

            for res_batch in results:
                for res in res_batch:
                    read_id = res["metadata"]["read_id"]
                    try:
                        channel, read_number, time_sent = cache.pop(read_id)
                    except KeyError:
                        # FIXME: This is resolved in later versions of guppy.
                        channel, read_number, time_sent = skipped.pop(read_id)
                        reads_sent += 1
                    res["metadata"]["read_id"] = read_id[3:]
                    self.logger.debug(
                        "@%s ch=%s\n%s\n+\n%s",
                        res["metadata"]["read_id"],
                        channel,
                        res["datasets"]["sequence"],
                        res["datasets"]["qstring"],
                    )
                    barcode = res["metadata"].get("barcode_arrangement", None)
                    # TODO: Add Filter here
                    yield Result(
                        channel=channel,
                        read_number=read_number,
                        read_id=res["metadata"]["read_id"],
                        seq=res["datasets"]["sequence"],
                        barcode=barcode if barcode else None,
                        basecall_data=res,
                    )
                    reads_received += 1

    def describe(self) -> str:
        """
        Describe the guppy Caller

        :return: Description of parameters passed to this guppy Caller plugin
        """
        description = ["Utilising the Guppy base-caller plugin:"]
        for param in self.guppy_params.keys():
            description.append(f"\t- {param}: {self.guppy_params[param]}")
        return "\n".join(description)
