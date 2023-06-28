"""basecall.py

Extension of pyguppy Caller that maintains a connection to the basecaller

"""
import logging
import time
from collections import namedtuple
import pathlib
import os

import numpy as np
from pyguppy_client_lib.helper_functions import package_read
from pyguppy_client_lib.pyclient import PyGuppyClient

from readfish._loggers import setup_debug_logger
from readfish.plugins.abc import CallerABC
from readfish.plugins.utils import Result

__all__ = ["Caller"]

logger = logging.getLogger("RU_basecaller")
CALIBRATION = namedtuple("calibration", "scaling offset")


class DefaultDAQValues:
    """Provides default calibration values

    Mimics the read_until_api calibration dict value from
    https://github.com/nanoporetech/read_until_api/blob/2319bbe80889a17c4b38dc9cdb45b59558232a7e/read_until/base.py#L34
    all keys return scaling=1.0 and offset=0.0
    """

    calibration = CALIBRATION(1.0, 0.0)

    def __getitem__(self, _):
        return self.calibration


_DefaultDAQValues = DefaultDAQValues()


# TODO: Simplify base call functions
class Caller(CallerABC):
    def __init__(self, debug_log, **kwargs):
        self.logger = setup_debug_logger("readfish_guppy_logger", log_file=debug_log)
        # Set our own priority
        self.guppy_params = kwargs
        self.validate_caller()
        self.guppy_params["priority"] = PyGuppyClient.high_priority
        self.caller = PyGuppyClient(**self.guppy_params)
        self.caller.connect()

    def validate_caller(self):
        """Validate the caller is available to connect to."""
        # We will check the existence of the "address" key.
        # We will also check the permissions of the "address" key.
        # ToDo: Work out how to log this in the tui.
        # ToDo: hack to remove ipc:// from the address
        caller_path = pathlib.Path(self.guppy_params["address"][6:])

        if not caller_path.exists():
            raise RuntimeError(
                f"The guppy basecaller path doesn't appear to exist. Please check your Guppy Settings. {self.guppy_params['address']}"
            )
        # check user permissions:
        if not os.access(caller_path, os.R_OK):
            raise RuntimeError(
                f"The user account running ReadFish doesn't appear to have permissions to read the guppy basecaller. Please check permissions on {self.guppy_params['address']}"
            )
        if not os.access(caller_path, os.W_OK):
            raise RuntimeError(
                f"The user account running ReadFish doesn't appear to have permissions to write to the guppy basecaller. Please check permissions on {self.guppy_params['address']}"
            )

    def disconnect(self) -> None:
        return self.caller.disconnect()

    def basecall(self, reads, signal_dtype, daq_values=None):
        """Basecall live data from minknow RPC

        Parameters
        ----------
        reads : iterable[Tuple[int, rpc.Read]]
            List or generator of tuples containing (channel, MinKNOW.rpc.Read)
        signal_dtype
            Numpy dtype of the raw data
        daq_values : Dict[int: namedtuple]
            Dictionary of channels with namedtuples containing offset and scaling.
            If not provided default values of 1.0 and 0.0 are used

        Yields
        ------
        result : readfish.plugings.utils.Result
        # read_info : tuple
        #     (channel, read_number)
        # data : dict
        #     All data returned from guppy server, this will contain different
        #     attributes depending on the client connection parameters
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
            time_received = time.time()

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
