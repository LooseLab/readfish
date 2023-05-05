from __future__ import annotations
import sys
import traceback
import importlib
from pathlib import Path
from typing import Optional, Union, List, Tuple, Dict
import logging

import attrs
import cattrs
import rtoml

from readfish._utils import generate_flowcell, compress_and_encode_string

from readfish.plugins.utils import Targets, Action, Decision


@attrs.define
class _Condition:
    """
    Representation of an experimental condition. This can either be a :class:`Barcode`
    or an experimental :class:`Region` of the flow cell.

    :param name: The name of the condition.
    :param single_on: The :class:`Action` to perform when a single sequence is to be processed.
    :param single_off: The :class:`Action` to perform when single sequences are not to be processed.
    :param multi_on: The :class:`Action` to perform when multiple sequences are to be processed.
    :param multi_off: The :class:`Action` to perform when multiple sequences are not to be processed.
    :param no_map: The :class:`Action` to perform when sequence mapping is not required.
    :param no_seq: The :class:`Action` to perform when no input sequences are provided.
    :param control: Whether the input data should be treated as a control. Defaults to False.
    :param targets: The target sequences for the condition. Defaults to empty :class:`Targets` object.
    :param min_chunks: The minimum number of chunks required for sequence processing. Defaults to 1.
    :param max_chunks: The maximum number of chunks allowed for sequence processing. Defaults to 2.
    :param below_min_chunks: The :class:`Action` to take when we haven't evaluated at least this many chunks. Defaults to ``Action.proceed``
    :param above_max_chunks: The :class:`Action` to take when we haven't evaluated at least this many chunks. Defaults to ``Action.unblock``
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
        """
        Get the :class:`Action` that corresponds to ``decision``.

        :param decision: :class:`Decision` for a molecule
        """
        return getattr(self, decision.name)


@attrs.define
class _PluginModule:
    """A plugin module

    :param name: The name of the plugin module.
    :param parameters: A dictionary of parameters to be passed to the plugin module.
    """

    name: str
    parameters: dict

    @classmethod
    def from_dict(cls, dict_: Dict[str, Dict]) -> "_PluginModule":
        """Creates an instance of the _PluginModule class from a dictionary.

        :param dict_: A dictionary containing a single key-value pair, where the key is
                      the name of the plugin module and the value is a dictionary of
                      parameters to be passed to the plugin module.

        :returns: An instance of the ``_PluginModule`` class with the specified name and parameters.
        """
        if len(dict_) != 1:
            raise ValueError("A single key-value pair should be provided")
        k = next(iter(dict_.keys()))
        return cls(k, dict_[k])

    def load_module(self, override=False):
        """
        This method loads a plugin module with the given name. If the module is a
        built-in plugin (as specified in the builtins dictionary), it is loaded from the
        readfish.plugins package. Otherwise, it is loaded using the importlib library.

        Parameters:
        override (bool, optional): If True, the module is reloaded even if it has already been loaded. Default is False.

        Returns:
        The loaded module.

        Raises:
        ModuleNotFoundError: If the plugin module cannot be found or loaded.

        Note that this method is intended to be used as part of a plugin system, where
        plugin modules are loaded dynamically at runtime. The builtins dictionary maps
        the names of built-in plugins to the actual module names, and is used to avoid
        having to specify the full module name when loading a built-in plugin. If
        override=True, the module is reloaded even if it has already been loaded. This
        can be useful during development, but should generally be avoided in production
        code for performance reasons.
        """
        builtins = {
            "guppy": "guppy",
            "mappy": "mappy",
            "mappy_rs": "mappy",
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
    """
    TODO: Add ``class`` level documentation for ``Conf``. This should link extensively to the TOML documentation.
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
        if not self.regions:
            # There are no analysis/control regions defined in this TOML file.

            if not all(k in self.barcodes for k in required_barcodes):
                # There are also no `unclassified` or `classified` tables

                raise Exception()

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
        if self.regions and self._channel_map:
            return self.regions[self._channel_map[channel]]

    def get_barcode(self, barcode: Optional[str]) -> Optional[Barcode]:
        if barcode is not None and self.barcodes is not None:
            return self.barcodes.get(barcode, self.barcodes["classified"])

    def get_targets(self, channel: int, barcode: Optional[str]) -> Targets:
        _, condition = self.get_conditions(channel, barcode)
        return condition.targets

    @classmethod
    def from_file(
        cls,
        path: Union[str, Path],
        channels: int,
        logger: Optional[logging.Logger] = None,
    ) -> Conf:
        with open(path, "rt") as fh:
            text = fh.read()
        if logger is not None:
            logger.info(compress_and_encode_string(text))
        dict_ = rtoml.loads(text)
        return cls.from_dict(dict_, channels, logger)

    @classmethod
    def from_dict(
        cls, dict_: dict, channels: int, logger: Optional[logging.Logger] = None
    ) -> Conf:
        if "channels" in dict_:
            raise ValueError("Key 'channels' cannot be present in TOML file")
        dict_["channels"] = channels
        conv = cattrs.GenConverter()
        conv.register_structure_hook(Targets, lambda d, t: t.from_str(d))
        conv.register_structure_hook(_PluginModule, lambda d, t: t.from_dict(d))
        return conv.structure(dict_, cls)

    def to_file(self, path: Union[str, Path]) -> None:
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
        with open(path, "wt") as fh:
            rtoml.dump(d, fh, pretty=True)


# TODO: Docs! (barcodes have higher precedence for targets than regions)
# TODO: Validation is baked in, need a pretty-printer for it though (https://github.com/python-attrs/cattrs/issues/258)


if __name__ == "__main__":
    try:
        obj = Conf.from_file(sys.argv[1], 512)
        print(obj)
    except Exception as e:
        if hasattr(e, "exceptions"):
            print(getattr(e, "exceptions"))
        sys.exit(traceback.format_exc())
