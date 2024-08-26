"""Dorado plugin module

Extension of pyBaseCaller that maintains a connection to the basecaller
"""

from __future__ import annotations
import logging
import os
import time
from collections import namedtuple
from pathlib import Path
from typing import Iterable, TYPE_CHECKING
from packaging.version import parse as parse_version

import numpy as np
import numpy.typing as npt
from minknow_api.protocol_pb2 import ProtocolRunInfo
from minknow_api.device_pb2 import GetSampleRateResponse

try:
    from pybasecall_client_lib.helper_functions import package_read
    from pybasecall_client_lib.pyclient import PyBasecallClient
except ImportError:
    pass

from readfish._loggers import setup_logger
from readfish.plugins.abc import CallerABC
from readfish.plugins.utils import Result
from readfish._utils import nice_join


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
        self,
        run_information: ProtocolRunInfo = None,
        sample_rate: GetSampleRateResponse = None,
        debug_log=None,
        **kwargs,
    ):
        self.logger = setup_logger("readfish_dorado_logger", log_file=debug_log)
        self.supported_barcode_kits = None
        self.supported_basecall_models = None
        self.run_information = run_information

        if self.run_information:
            self.basecaller_version = (
                self.run_information.software_versions.basecaller_connected_version
            )

            if parse_version(self.basecaller_version) >= parse_version("7.4.12"):
                logging.info(f"Connected to caller version {self.basecaller_version}.")
            else:
                logging.info(
                    f"Trying to use minKNOW with a caller version {self.basecaller_version}."
                    " If this is causing readfish to crash, try using a version of Dorado >= 7.3.9."
                    " You should also check for any updates available to readfish."
                )

        # Set our own priority
        self.dorado_params = kwargs
        self.dorado_params["priority"] = PyBasecallClient.high_priority
        # Set our own client name to appear in the dorado server logs
        self.dorado_params["client_name"] = "Readfish_connection"

        if sample_rate:
            self.sample_rate = float(sample_rate)
        else:
            self.sample_rate = float(5000)

        self.validate()
        self.caller = PyBasecallClient(**self.dorado_params)
        self.caller.connect()

    def validate(self) -> None:
        """Validate the parameters passed to Dorado to ensure they will initialise py Basecall Client correctly

        Currently checks:
            1. That the socket file exists
            2. That the Socket file has the correct permissions
            3. That the version of py basecall client lib installed matches the system version

        :return: None, if the parameters pass all the checks

        """
        for key in ("address", "config"):
            if key not in self.dorado_params:
                raise KeyError(
                    f"Required `caller_settings.dorado` {key} was not found in provided TOML. Please add."
                )
        if self.dorado_params["address"].startswith("ipc://"):
            # User is attempting to connect to an IPC socket
            socket_path = Path(self.dorado_params["address"][6:])
            if not socket_path.exists():
                raise FileNotFoundError(
                    f"The provided dorado base-caller socket address doesn't appear to exist. Please check your dorado Settings. {self.dorado_params['address']}"
                )

            # check user permissions:
            if not os.access(socket_path, os.R_OK):
                raise RuntimeError(
                    f"The user account running readfish doesn't appear to have permissions to read the dorado base-caller socket. Please check permissions on {self.dorado_params['address']}. See https://github.com/LooseLab/readfish/issues/221#issuecomment-1375673490 for more information."
                )
            if not os.access(socket_path, os.W_OK):
                raise RuntimeError(
                    f"The user account running readfish doesn't appear to have permissions to write to the dorado base-caller socket. Please check permissions on {self.dorado_params['address']}. See https://github.com/LooseLab/readfish/issues/221#issuecomment-1375673490 for more information."
                )
        # If we are connected to a live run, test if the base-caller model is acceptable.
        # Connected to a live run via the minknow_api - get supported basecall and barcoding kits from the run info.
        #  Check them against provided values
        if self.run_information is not None:
            tags = self.run_information.meta_info.tags

            self.supported_basecall_models = tags[
                "available basecall models"
            ].array_value
            # Make a CSV str a list of strings, removing quotes and square brackets
            if self.supported_basecall_models and isinstance(
                self.supported_basecall_models, str
            ):
                self.supported_basecall_models = (
                    tags["available basecall models"]
                    .array_value[1:-1]
                    .replace('"', "")
                    .split(",")
                )
            # Faff on with sorting out available barcoding kits
            # See https://github.com/nanoporetech/minknow_api/blob/829dbe8ac8e49efdf268d385b50440c52473188b/python/minknow_api/tools/protocols.py#L97C1-L97C7
            self.supported_barcode_kits = tags["barcoding kits"].array_value
            # workaround for the set of barcoding kits being returned as a string rather
            # that array of strings
            if self.supported_barcode_kits and isinstance(
                self.supported_barcode_kits, str
            ):
                self.supported_barcode_kits = (
                    tags["barcoding kits"].array_value[1:-1].replace('"', "").split(",")
                )

            if tags["barcoding"].bool_value:
                self.supported_barcode_kits.append(tags["kit"].string_value)
            # If we are connected to a live run, and have suitable base calling models check the base-caller model is suitable for the flowcell and kit
            if (
                self.supported_basecall_models
                and f"{self.dorado_params['config'].replace('.cfg', '')}.cfg"
                not in self.supported_basecall_models
            ):
                raise RuntimeError(
                    """The {} base-calling config listed in the readfish config TOML is not suitable for this flowcell and kit combination.
    Please check the dorado value in the caller_settings.dorado section of your TOML file.
    The following models are are given by ONT as suitable for this flow cell/kit combo:\n\t{}""".format(
                        self.dorado_params["config"],
                        nice_join(
                            self.supported_basecall_models,
                            sep="\n\t",
                            conjunction="and",
                        ),
                    )
                )

            # If we are barcoding and have connected to a live run - try checking the listed barcode kit works with the flowcell and kit
            if (
                barcoding_kits := self.dorado_params.get("barcode_kits", None)
            ) is not None:
                barcoding_kits = barcoding_kits.split()
            if barcoding_kits and not set(barcoding_kits).issubset(
                self.supported_barcode_kits
            ):
                raise RuntimeError(
                    "Barcoding kits specified in TOML {} not amongst those supported by the selected kit and protocol.\nSupported kits are:\n\t{}".format(
                        nice_join(barcoding_kits, conjunction="and"),
                        nice_join(
                            self.supported_barcode_kits, sep="\n\t", conjunction="and"
                        ),
                    ),
                )
        return None

    def disconnect(self) -> None:
        """Call the disconnect method on the PyBasecallClient"""
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
        # FIXME: Occasionally dorado can report a read as not sent when it is
        #        successfully sent. Therefore we capture not sent reads
        cache, skipped = {}, {}
        reads_received, reads_sent = 0, 0
        reads_to_send = []
        daq_values = _DefaultDAQValues if daq_values is None else daq_values
        for channel, read in reads:
            # Attach the "RF-" prefix
            read_id = f"RF-{read.id}"
            t0 = time.time()
            # cache the read id without the RF tag
            cache[read_id] = (channel, read.id, t0)
            reads_to_send.append(
                package_read(
                    read_id=read_id,
                    raw_data=np.frombuffer(read.raw_data, signal_dtype),
                    daq_offset=daq_values[channel].offset,
                    daq_scaling=daq_values[channel].scaling,
                    sampling_rate=self.sample_rate,
                    start_time=int(read.start_sample),
                )
            )
            reads_sent += 1
        success_pass = False
        for _attempt in range(3):
            # Only attempt to pass reads if there are reads to be passed
            if not success_pass and reads_to_send:
                success_pass = self.caller.pass_reads(reads_to_send)
            else:
                break
        else:
            logging.warning(
                f"Could not send {len(reads_to_send)} reads to Dorado after 3 attempts, skipping!"
            )
            for read in reads_to_send:
                skipped[read["read_id"]] = cache.pop(read["read_id"])

            # sleep_time = self.caller.throttle - t0
            # if sleep_time > 0:
            #     time.sleep(sleep_time)
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
                    # Dorado sometimes returns two sub_tags for a read, where signal which was thought to be a single read has been split.
                    #
                    # An example result:
                    # RF-17774e44-8d3c-4bdd-8730-aaf8addd3e6c
                    # {'read_tag': 3605, 'sub_tag': 0, 'metadata': {'read_id': 'RF-17774e44-8d3c-4bdd-8730-aaf8addd3e6c'...},
                    #    'datasets': {'raw_data': array([306, 289, 300, ..., 526, 537, 540], dtype=int16),
                    #        'sequence': 'CTACAGTGGTCGTCAATACTATTGCAACTCCAGCCTGGGCAACAGAGTGAGACCCTGTCTCAAA...'.}}
                    # RF-17774e44-8d3c-4bdd-8730-aaf8addd3e6c
                    # {'read_tag': 3605, 'sub_tag': 1 , 'metadata': {'read_id': 'RF-17774e44-8d3c-4bdd-8730-aaf8addd3e6c'...}
                    #    'datasets': {'raw_data': array([306, 289, 300, ..., 526, 537, 540], dtype=int16),
                    #        'sequence': 'TTTTTGTGGGCTTTTA',}}
                    # The second sub_tag will cause the code to fail as it is not expected.
                    # Therefore we need to check for the sub_tag and if it is not 0, we need to skip the read.
                    if res["sub_tag"] > 0:
                        continue

                    try:
                        channel, read_id, _time_sent = cache.pop(read_id)
                    except KeyError:
                        channel, read_id, _time_sent = skipped.pop(read_id)
                        reads_sent += 1
                    self.logger.debug(
                        "@%s ch=%s\n%s\n+\n%s",
                        read_id,
                        channel,
                        res["datasets"]["sequence"],
                        res["datasets"]["qstring"],
                    )
                    barcode = res["metadata"].get("barcode_arrangement", None)
                    # TODO: Add Filter here
                    yield Result(
                        channel=channel,
                        read_id=read_id,
                        seq=res["datasets"]["sequence"],
                        barcode=barcode if barcode else None,
                        basecall_data=res,
                    )
                    reads_received += 1

    def describe(self) -> str:
        """
        Describe the Dorado Caller

        :return: Description of parameters passed to this Dorado Caller plugin
        """
        description = ["Utilising the Dorado base-caller plugin:"]
        for param in self.dorado_params.keys():
            description.append(f"\t- {param}: {self.dorado_params[param]}")
        return "\n".join(description)
