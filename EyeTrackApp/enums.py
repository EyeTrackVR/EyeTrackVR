"""
------------------------------------------------------------------------------------------------------

                                               ,@@@@@@
                                            @@@@@@@@@@@            @@@
                                          @@@@@@@@@@@@      @@@@@@@@@@@
                                        @@@@@@@@@@@@@   @@@@@@@@@@@@@@
                                      @@@@@@@/         ,@@@@@@@@@@@@@
                                         /@@@@@@@@@@@@@@@  @@@@@@@@
                                    @@@@@@@@@@@@@@@@@@@@@@@@ @@@@@
                                @@@@@@@@                @@@@@
                              ,@@@                        @@@@&
                                             @@@@@@.       @@@@
                                   @@@     @@@@@@@@@/      @@@@@
                                   ,@@@.     @@@@@@((@     @@@@(
                                   //@@@        ,,  @@@@  @@@@@
                                   @@@(                @@@@@@@
                                   @@@  @          @@@@@@@@#
                                       @@@@@@@@@@@@@@@@@
                                      @@@@@@@@@@@@@(

Copyright (c) 2025 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
------------------------------------------------------------------------------------------------------
"""

from __future__ import annotations

import types
from collections import namedtuple
from typing import (
    Any,
    ClassVar,
    Dict,
    List,
    TYPE_CHECKING,
    Tuple,
    Type,
    TypeVar,
    Iterator,
    Mapping,
)

__all__ = (
    "Enum",
    "EyeLR",
)

if TYPE_CHECKING:
    from typing_extensions import Self


def _create_value_cls(name: str, comparable: bool):
    # All the type ignores here are due to the type checker being unable to recognise
    # Runtime type creation without exploding.
    cls = namedtuple("_EnumValue_" + name, "name value")
    cls.__repr__ = lambda self: f"<{name}.{self.name}: {self.value!r}>"  # type: ignore
    cls.__str__ = lambda self: f"{name}.{self.name}"  # type: ignore
    if comparable:
        cls.__le__ = lambda self, other: isinstance(other, self.__class__) and self.value <= other.value  # type: ignore
        cls.__ge__ = lambda self, other: isinstance(other, self.__class__) and self.value >= other.value  # type: ignore
        cls.__lt__ = lambda self, other: isinstance(other, self.__class__) and self.value < other.value  # type: ignore
        cls.__gt__ = lambda self, other: isinstance(other, self.__class__) and self.value > other.value  # type: ignore
    return cls


def _is_descriptor(obj):
    return (
        hasattr(obj, "__get__") or hasattr(obj, "__set__") or hasattr(obj, "__delete__")
    )


class EnumMeta(type):
    if TYPE_CHECKING:
        __name__: ClassVar[str]
        _enum_member_names_: ClassVar[List[str]]
        _enum_member_map_: ClassVar[Dict[str, Any]]
        _enum_value_map_: ClassVar[Dict[Any, Any]]

    def __new__(
        cls,
        name: str,
        bases: Tuple[type, ...],
        attrs: Dict[str, Any],
        *,
        comparable: bool = False,
    ):
        value_mapping = {}
        member_mapping = {}
        member_names = []

        value_cls = _create_value_cls(name, comparable)
        for key, value in list(attrs.items()):
            is_descriptor = _is_descriptor(value)
            if key[0] == "_" and not is_descriptor:
                continue

            # Special case classmethod to just pass through
            if isinstance(value, classmethod):
                continue

            if is_descriptor:
                setattr(value_cls, key, value)
                del attrs[key]
                continue

            try:
                new_value = value_mapping[value]
            except KeyError:
                new_value = value_cls(name=key, value=value)
                value_mapping[value] = new_value
                member_names.append(key)

            member_mapping[key] = new_value
            attrs[key] = new_value

        attrs["_enum_value_map_"] = value_mapping
        attrs["_enum_member_map_"] = member_mapping
        attrs["_enum_member_names_"] = member_names
        attrs["_enum_value_cls_"] = value_cls
        actual_cls = super().__new__(cls, name, bases, attrs)
        value_cls._actual_enum_cls_ = actual_cls  # type: ignore # Runtime attribute isn't understood
        return actual_cls

    def __iter__(cls) -> Iterator[Any]:
        return (cls._enum_member_map_[name] for name in cls._enum_member_names_)

    def __reversed__(cls) -> Iterator[Any]:
        return (
            cls._enum_member_map_[name] for name in reversed(cls._enum_member_names_)
        )

    def __len__(cls) -> int:
        return len(cls._enum_member_names_)

    def __repr__(cls) -> str:
        return f"<enum {cls.__name__}>"

    @property
    def __members__(cls) -> Mapping[str, Any]:
        return types.MappingProxyType(cls._enum_member_map_)

    def __call__(cls, value: str) -> Any:
        try:
            return cls._enum_value_map_[value]
        except (KeyError, TypeError):
            raise ValueError(f"{value!r} is not a valid {cls.__name__}")

    def __getitem__(cls, key: str) -> Any:
        return cls._enum_member_map_[key]

    def __setattr__(cls, name: str, value: Any) -> None:
        raise TypeError("Enums are immutable.")

    def __delattr__(cls, attr: str) -> None:
        raise TypeError("Enums are immutable")

    def __instancecheck__(self, instance: Any) -> bool:
        # isinstance(x, Y)
        # -> __instancecheck__(Y, x)
        try:
            return instance._actual_enum_cls_ is self
        except AttributeError:
            return False


if TYPE_CHECKING:
    from enum import Enum, IntEnum
else:

    class Enum(metaclass=EnumMeta):
        @classmethod
        def try_value(cls, value):
            try:
                return cls._enum_value_map_[value]
            except (KeyError, TypeError):
                return value


E = TypeVar("E", bound="Enum")


def create_unknown_value(cls: Type[E], val: Any) -> E:
    value_cls = cls._enum_value_cls_  # type: ignore # This is narrowed below
    name = f"unknown_{val}"
    return value_cls(name=name, value=val)


def try_enum(cls: Type[E], val: Any) -> E:
    """A function that tries to turn the value into enum ``cls``.
    If it fails it returns a proxy invalid value instead.
    """

    try:
        return cls._enum_value_map_[val]  # type: ignore # All errors are caught below
    except (KeyError, TypeError, AttributeError):
        return create_unknown_value(cls, val)


# The line above is based on the code in the following url
# https://github.com/Rapptz/discord.py/blob/f7e97954950ffb0e34238d70813454caa6f1a3ae/discord/enums.py


class EyeLR(Enum):
    LEFT = 1
    RIGHT = 2

    def __str__(self) -> str:
        return self.name

    def __int__(self) -> int:
        return self.value
