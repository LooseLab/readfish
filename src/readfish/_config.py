from __future__ import annotations
from collections import defaultdict
import sys
import traceback
import importlib
from pathlib import Path
from typing import Any, Dict, Tuple, List, Optional
import logging

import attrs
import cattrs
import rtoml

from readfish._utils import (
    generate_flowcell,
    compress_and_encode_string,
    nice_join,
    draw_flowcell_split,
)

from readfish.plugins.utils import Targets, Action, Decision, Result


def make_decision(conf: Conf, result: Result) -> Decision:
    """
    The main decision making function for readfish.
    Chooses the decision that is looked up in the TOML based
    on the mapped coordinates of the read, checked against the targets.
    Decision is one of single_on, multi_on, single_off, multi_off, no_map, no_seq.

    :param conf: The Conf object for the experiment
    :param result: The result of the alignment and base calling for the read
    :raises ValueError: If readfish fails to make a decision based on
        the passed Result object length
    :return: The decision that readfish has made for this read
    """
    if result.alignment_data is None:
        result.alignment_data = []
    targets = conf.get_targets(result.channel, result.barcode)
    results = result.alignment_data
    matches = []
    for al in results:
        contig = al.ctg
        strand = al.strand
        coord = al.r_st if al.strand == -1 else al.r_en
        matches.append(targets.check_coord(contig, strand, coord))
    coord_match = any(matches)

    if not results:
        if len(result.seq) > 0:
            return Decision.no_map
        else:
            return Decision.no_seq
    elif len(results) == 1:
        return Decision.single_on if coord_match else Decision.single_off
    elif len(results) > 1:
        return Decision.multi_on if coord_match else Decision.multi_off
    raise ValueError()


@attrs.define
class _Condition:
    """Representation of an experimental condition.
    This can either be a :class:`Barcode` or an experimental :class:`Region` of the flow cell.

    :param name: The name of the condition.
    :param single_on: The :class:`Action` to perform when a read has a single, on-target, alignment
    :param single_off: The :class:`Action` to perform when a read has a single, off-target, alignment
    :param multi_on: The :class:`Action` to perform when a read has multiple alignments, with at least one on-target
    :param multi_off: The :class:`Action` to perform when a read has multiple aligments, with all off-target
    :param no_map: The :class:`Action` to perform when a read has no aligments
    :param no_seq: The :class:`Action` to perform when a read did not basecall
    :param control: Whether the region should be treated as a control. Defaults to False
    :param targets: The target sequences for the condition. See :class:`Targets` for details
    :param min_chunks: The minimum number of chunks required before a decision will be made. Defaults to 1
    :param max_chunks: The maximum number of chunks that readfish will assess for any single read. Defaults to 2
    :param below_min_chunks: The :class:`Action` to take when we haven't evaluated at least ``min_chunks``. Defaults to ``Action.proceed``
    :param above_max_chunks: The :class:`Action` to take when we have exceeded ``max_chunks``. Defaults to ``Action.unblock``
    """

    name: str
    single_on: Action
    single_off: Action
    multi_on: Action
    multi_off: Action
    no_map: Action
    no_seq: Action
    control: bool = attrs.field(default=False)
    targets: Targets = attrs.field(default=attrs.Factory(Targets))
    min_chunks: int = attrs.field(repr=False, default=1)
    max_chunks: int = attrs.field(repr=False, default=2)
    below_min_chunks: Action = attrs.field(default=Action.proceed)
    above_max_chunks: Action = attrs.field(default=Action.unblock)

    def get_action(self, decision: Decision) -> Action:
        """Get the :class:`Action` that corresponds to ``decision``.

        :param decision: :class:`Decision` for a read
        """
        return getattr(self, decision.name)

    def pretty_print(self) -> str:
        """
        Pretty print how the conditions match up to the resulting Actions. Used in the describe function.

        :return: A pretty format string containing all the variables
        """
        d = defaultdict(list)
        for decision in [
            "single_on",
            "single_off",
            "multi_on",
            "multi_off",
            "no_map",
            "no_seq",
            "below_min_chunks",
            "above_max_chunks",
        ]:
            d[getattr(self, decision)].append(decision)
        s = [
            f"Read will be sent {k.name} when classed as:\n\t{nice_join(v)}."
            for k, v in d.items()
        ]
        return "\n".join(s)


@attrs.define
class _PluginModule:
    """A plugin module

    :param name: The name of the plugin module.
    :param parameters: A dictionary of parameters to be passed to the plugin module.
    """

    name: str
    parameters: dict

    @classmethod
    def from_dict(cls, params: Dict[str, Dict]) -> _PluginModule:
        """Creates an instance of the _PluginModule class from a dictionary.

        :param params: A dictionary containing a single key-value pair, where the key is
                       the name of the plugin module and the value is a dictionary of
                       parameters to be passed to the plugin module.
        :raises ValueError: If more than one key value pair is provided in the ``params``
        :return: An instance of the ``_PluginModule`` class with the specified name and parameters.
        """

        if len(params) != 1:
            raise ValueError("A single key-value pair should be provided")
        k = next(iter(params.keys()))
        return cls(k, params[k])

    def load_module(self, override=False):
        """Load a plugin module with the given name.

        If the module is a built-in plugin (as specified in the builtins dictionary), it is loaded from the readfish.plugins package.
        Otherwise, it is loaded using the importlib library.

        :param override: If True, the built-in module names are ignored. Default is False.

        :return: The loaded module.

        :raises ModuleNotFoundError: If the plugin module cannot be found or loaded.

        Note that this method is intended to be used as part of a plugin system, where
        plugin modules are loaded dynamically at runtime. The builtins dictionary maps
        the names of built-in plugins to the actual module names, and is used to avoid
        having to specify the full module name when loading a built-in plugin. If
        override=True, the builtin module names are ignored.
        """
        builtins = {
            "guppy": "guppy",
            "mappy": "mappy",
            "mappy_rs": "mappy_rs",
            "no_op": "_no_op",
        }
        if self.name in builtins and not override:
            return importlib.import_module(f"readfish.plugins.{builtins[self.name]}")
        return importlib.import_module(self.name)

    def load_object(
        self, obj: str, *, init: bool = True, override: bool = False, **kwargs
    ):
        """Load a specified object from a plugin module.

        First :meth:`load_module` is called to load the plugin module, then the
        specified object is retreived from the module.

        :param obj: The name of the object to load from the plugin module.
        :param init: If True, the returned object is initialized with the parameters provided to the constructor of the parent class, as well as any additional keyword arguments passed in via the ``**kwargs`` parameter.
        :param override: If True, ignore builtin readfish plugins.
        :param kwargs: Additional keyword arguments to pass to the constructor of the loaded object.

        :returns: The specified object from the plugin module. If init=True, the object is initialized with the provided parameters and returned.

        :raises ModuleNotFoundError: If the plugin module cannot be found or loaded.
        :raises AttributeError: If the specified object cannot be found in the plugin module.
        :raises TypeError:  If the runtime ``**kwargs`` conflict with the module parameters from the TOML file.
        """
        mod = self.load_module(override=override)
        obj_ = getattr(mod, obj)
        if init:
            overlap = kwargs.keys() & self.parameters.keys()
            if overlap:
                raise TypeError(
                    f"Attempting to initalise `{obj}` with conflicting keys: {overlap}"
                )
            return obj_(**kwargs, **self.parameters)
        return obj_


# fmt: off
# Aliases to defined classes, make for nicer printing
class CallerSettings(_PluginModule):
    """See :class:`_PluginModule` for details"""
class MapperSettings(_PluginModule):
    """See :class:`_PluginModule` for details"""
class Region(_Condition):
    """See :class:`_Condition` for details"""
class Barcode(_Condition):
    """See :class:`_Condition` for details"""
# fmt: on


@attrs.define
class Conf:
    """Overall configuration for readfish experiments


    The Conf class is the mother if the adaptive sampling experiment.
    It is constructed from the provided ``TOML`` file, via a call to `from_file`.


    :param channels: The number of channels on the flow cell
    :param caller_settings: The caller settings as listed in the TOML
    :param mapper_settings: The mapper settings as listed in the TOML
    :param regions: The regions as listed in the Toml file.
    :param barcodes: A Dictionary of barcode names to Barcode Classes
    :param _channel_map: A map of channels number (1 to flowcell size) to the index of the Region (in self.regions) they are part of.
    """

    channels: int
    caller_settings: CallerSettings
    mapper_settings: MapperSettings
    regions: List[Region] = attrs.field(default=attrs.Factory(list))
    barcodes: Dict[str, Barcode] = attrs.field(default=attrs.Factory(dict))
    _channel_map: Dict[int, int] = attrs.field(
        repr=False,
        init=False,
        alias="_channel_map",
        default=attrs.Factory(dict),
    )

    def __attrs_post_init__(self):
        # There must be one of:
        #  - at least one region for the flow cell
        #  - barcode tables with "classified" and "unclassified"
        # TODO: Check that there's at least one region if no barcodes

        required_barcodes = ["unclassified", "classified"]

        # This check ensures that when there are no `regions` on the flow cell
        #   there are
        if not self.regions or self.barcodes:
            # There are no analysis/control regions defined in this TOML file.

            if not all(k in self.barcodes for k in required_barcodes):
                # There are also no `unclassified` or `classified` tables

                raise RuntimeError(
                    "This TOML configuration does not contain any `regions`"
                    "or `barcodes` and cannot be used by readfish"
                )

        if self.mapper_settings.name == "mappy" and self.channels > 512:
            raise RuntimeError(
                "We do not allow the use of the 'mappy' aligner with PromethION devices. "
                "Please use 'mapper_settings.mappy_rs' in your experiment TOML"
                " with n_threads set to at least 4."
            )

        split_channels = generate_flowcell(self.channels, len(self.regions) or 1)
        self._channel_map = {
            channel: pos
            for pos, (channels, region) in enumerate(zip(split_channels, self.regions))
            for channel in channels
        }

    def get_conditions(
        self, channel: int, barcode: Optional[str]
    ) -> Tuple[bool, Barcode | Region]:
        """Get the condition for this channel or barcode from the Conf TOML

        The barcoder should return the barcode name e.g. ``barcode01`` or
        ``unclassified`` if a barcode could not be assigned. If barcoding
        is not being done then the barcode should be ``None`` and channel
        will be used instead.

        :param channel: Channel number for this result
        :param barcode: Barcode classification from basecalling

        :returns control: Whether this channel/barcode combination is a ``control`` condition
        :returns condition: The :class:`Barcode` or :class:`Region` that this channel/barcode belongs to

        :raises ValueError: In the event that the channel/barcode combination does not find a :class:`Region` or a :class:`Barcode`
        """
        region_ = self.get_region(channel)
        barcode_ = self.get_barcode(barcode)

        if region_ is not None and barcode_ is not None:
            control = region_.control or barcode_.control
            condition = barcode_
        elif region_ is not None and barcode_ is None:
            control = region_.control
            condition = region_
        elif region_ is None and barcode_ is not None:
            control = barcode_.control
            condition = barcode_
        else:
            raise ValueError(
                f"Both region (channel={channel}) and barcode ({barcode}) were not found. This config is invalid!"
            )
        return control, condition

    def get_region(self, channel: int) -> Optional[Region]:
        """Get the region for a given channel

        :param channel: The channel number
        :return: Returns a region, if there is one, otherwise None
        """
        if self.regions and self._channel_map:
            return self.regions[self._channel_map[channel]]

    def get_barcode(self, barcode: Optional[str]) -> Optional[Barcode]:
        """Get a barcode for a given barcode name

        :param barcode: The name of the barcode, example "barcode01"
        :return: The barcode class instance for the given barcode name, if there is one
        """
        if barcode is not None and self.barcodes is not None:
            return self.barcodes.get(barcode, self.barcodes["classified"])

    def get_targets(self, channel: int, barcode: Optional[str]) -> Targets:
        """Get the targets for a given channel or barcode, via its condition

        :param channel: The channel number
        :param barcode: The barcode name, optional
        :return: The targets list for a given channel
        """
        _, condition = self.get_conditions(channel, barcode)
        return condition.targets

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        channels: int,
        logger: Optional[logging.Logger] = None,
    ) -> Conf:
        """Create a Conf from a TOML file.

        Loads the toml using rtoml then calls `from_dict` to create the class.

        :param path: Path to the toml file
        :param channels: Number of channels on the flow cell
        :param logger: Logger to write out a base64 encoded compressed toml, defaults to None
        :return: The Conf as constructed from this toml
        """
        with open(path) as fh:
            text = fh.read()
        if logger is not None:
            logger.info(compress_and_encode_string(text))
        dict_ = rtoml.loads(text)
        return cls.from_dict(dict_, channels)

    @classmethod
    def from_dict(cls, dict_: Dict[str, Any], channels: int) -> Conf:
        """
        Create the Conf class from a Dictionary

        :param dict_: The dictionary that contains the parsed TOML file
        :param channels: The number of channels on the flow cell
        :raises ValueError: If channel is present in the TOML file raise ValueError as it will overwrite something
        :return: The constructed Conf class
        """
        if "channels" in dict_:
            raise ValueError("Key 'channels' cannot be present in TOML file")
        dict_["channels"] = channels
        conv = cattrs.GenConverter()
        conv.register_structure_hook(Targets, lambda d, t: t.from_parsed_toml(d))
        conv.register_structure_hook(_PluginModule, lambda d, t: t.from_dict(d))
        return conv.structure(dict_, cls)

    def to_file(self, path: str | Path) -> None:
        """Write a conf to a TOML file

        :param path: File path to create the TOML file for
        """
        cattrs.register_unstructure_hook(
            Targets,
            lambda cls: cls.value if isinstance(cls.value, list) else str(cls.value),
        )
        cattrs.register_unstructure_hook(
            _PluginModule, lambda cls: {cls.name: cls.parameters}
        )
        d = cattrs.unstructure(self)
        # Pop dynamically added attributes
        d.pop("channels")
        d.pop("_channel_map")
        with open(path, "w") as fh:
            rtoml.dump(d, fh, pretty=True)

    def write_channels_toml(self, out_dir: Path) -> None:
        """
        Write out a channels toml file to the given directory.
        This file is a map of each channel number to the corresponding region name.

        :param out_dir: Read Until client we are connected to.
        """
        d = {"conditions": {}}

        for idx, r in enumerate(self.regions):
            g = d["conditions"].setdefault(str(idx), {})
            g["channels"] = [c for c, i in self._channel_map.items() if i == idx]
            g["name"] = r.name
        channels_out = out_dir / "channels.toml"
        with open(channels_out, "w") as fh:
            fh.write(
                "# This file is written as a record of the condition each channel is assigned.\n"
                "# It may be changed or overwritten if you restart readfish.\n"
                "# In the future this file may become a CSV file.\n"
            )
            rtoml.dump(d, fh)

    def describe_experiment(self) -> str:
        """
        Describe the experiment from the given Conf class.
        For Barcodes we describe the targets and the conditions, but not the region.

        :return: The description string, human readable.
        """
        split = len(self.regions)
        description = ["Configuration description:"]
        # - 2 so we do not include classified and unclassified
        num_barcodes = len(self.barcodes) - 2
        if len(self.barcodes):
            description.append(
                f"Number of barcodes in the Conf (excluding unclassified and classified): {num_barcodes}"
            )
            description.append(
                nice_join(
                    (
                        f"Barcode {barcode.name} (control={barcode.control})"
                        for barcode in self.barcodes.values()
                    ),
                    conjunction="and",
                )
            )
            # lazy way of adding a new line between barcodes and regions
            description.append("")

        for index, region in enumerate(self.regions):
            description.append(
                f"""Region {region.name} (control={region.control}).
Region applies to section of flow cell (# = applied, . = not applied):
{draw_flowcell_split(self.channels, split, index=index)}"""
            )
        return "\n".join(description)


if __name__ == "__main__":
    try:
        obj = Conf.from_file(sys.argv[1], 512)
        print(obj)
    except Exception as e:
        if hasattr(e, "exceptions"):
            print(getattr(e, "exceptions"))
        print(traceback.format_exc())
