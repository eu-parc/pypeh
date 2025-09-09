from typing import TypeVar, Union, Sequence, List, Dict, Any, Mapping, TextIO, BinaryIO, Protocol
from pydantic import BaseModel
from peh_model.peh import EntityList, YAMLRoot, NamedThingId, NamedThing
from pathlib import Path

from pypeh.core.models.proxy import TypedLazyProxy

import io

# IO Types

T_Dataclass = TypeVar("T_Dataclass", bound=Union[EntityList, BaseModel])
T_DataType = TypeVar("T_DataType")
T_Root = Union[YAMLRoot, NamedThingId]
T_RootStream = Union[T_Root, Mapping[Any, T_Root], Sequence[T_Root]]
JSONLike = Union[str, List, List[Dict], TextIO]

# Data model types
T_NamedThingLike = Union[NamedThing, TypedLazyProxy]


class ReadableText(Protocol):
    def read(self) -> str: ...


class ReadableBinary(Protocol):
    def read(self) -> bytes: ...


IOLike = Union[
    str,
    Path,
    ReadableText,
    ReadableBinary,
    io.StringIO,
    io.BytesIO,
    TextIO,
    BinaryIO,
]
