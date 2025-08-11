from __future__ import annotations

import dataclasses
import logging
import json
import yaml

from dataclasses import is_dataclass
from linkml_runtime.loaders import YAMLLoader, JSONLoader, RDFLibLoader
from linkml_runtime.dumpers import YAMLDumper
from pydantic import TypeAdapter, BaseModel, ConfigDict
from pathlib import Path
from rdflib import Graph
from typing import TYPE_CHECKING, Union, Any, IO, get_type_hints, cast

from pypeh.core.interfaces.outbound.persistence import PersistenceInterface
from pypeh.core.utils.linkml_schema import get_schema_view
from peh_model.peh import EntityList, YAMLRoot, DataLayout
from pypeh.core.models.typing import T_Dataclass, IOLike

if TYPE_CHECKING:
    from typing import Callable, Type

logger = logging.getLogger(__name__)


def is_dataclass_type(cls: Any) -> bool:
    return dataclasses.is_dataclass(cls) and isinstance(cls, type)


def validate_dataclass(data: dict, target_class: Type[T_Dataclass] | Any) -> T_Dataclass | Any:
    if not dataclasses.is_dataclass(target_class):
        raise TypeError(f"{target_class} is not a dataclass")

    # Get type hints to resolve forward references and generic types
    type_hints = get_type_hints(target_class)

    processed_data = {}

    for field in dataclasses.fields(target_class):
        field_name = field.name
        field_type = type_hints.get(field_name)
        assert field_type is not None
        value = data.get(field_name)

        if is_dataclass_type(field_type) and isinstance(value, dict):
            # Recursively validate nested dataclass
            processed_data[field_name] = validate_dataclass(value, field_type)
        elif (
            hasattr(field_type, "__origin__")
            and field_type.__origin__ in (list, tuple)
            and is_dataclass_type(field_type.__args__[0])
        ):
            # Handle list/tuple of dataclasses
            assert value is not None
            processed_data[field_name] = [
                validate_dataclass(item, field_type.__args__[0]) if isinstance(item, dict) else item for item in value
            ]
        else:
            # Use Pydantic to validate scalar or complex non-dataclass field
            if value is not None:
                adapter = TypeAdapter(
                    field_type,
                    config=ConfigDict(arbitrary_types_allowed=True),
                )
                processed_data[field_name] = adapter.validate_python(value)
            else:
                processed_data[field_name] = None

    return target_class(**processed_data)


def validate_pydantic(
    data: dict,
    target_class: Type[BaseModel],
) -> BaseModel:
    """
    Validate data against a dataclass using Pydantic's TypeAdapter.
    """
    return target_class.model_validate(data)


def is_consistent_with_layout(data: dict, layout: DataLayout) -> bool:
    """
    Validate newly loaded data against a PEH DataLayout.
    """
    if layout.sections is not None:
        layout_section_names = {section.label for section in layout.sections}  # type: ignore
    ## FIXME: linkml dataclasses are making the typer behave weirdly
    return layout_section_names.issuperset(set(data.keys()))


class IOAdapter(PersistenceInterface):
    read_mode: str = NotImplementedError  # type: ignore
    write_mode: str = NotImplementedError  # type: ignore

    """Adapter for loading from file."""

    def _loads(self, data: Union[str, bytes]) -> Any:
        raise NotImplementedError

    def _load(self, stream: IO) -> Any:
        raise NotImplementedError

    def load(
        self,
        source: Union[str, Path, IO[str], IO[bytes], bytes],
        target_class: Type[T_Dataclass] | Any | None,
        **kwargs,
    ) -> Any:
        raise NotImplementedError

    def dump(self, destination: IOLike, entity: BaseModel) -> None:
        raise NotImplementedError


class JsonIO(IOAdapter):
    read_mode: str = "r"
    write_mode: str = "w"
    """
    Adapter for loading from json file/stream.
    Assuming jsonfiles can be directly loaded by linkml
    """

    def _validate(self, data_dict: dict, target_class: Type[T_Dataclass] | Any | None) -> T_Dataclass | Any | dict:
        if target_class is None:
            return data_dict  # return plain dict
        if issubclass(target_class, EntityList):
            return JSONLoader().load(data_dict, target_class)
            # Note we do not need to depend on linkml here
            # return validate_dataclass(data_dict, EntityList)
        elif is_dataclass(target_class):
            return validate_dataclass(data_dict, target_class)
        elif issubclass(target_class, BaseModel):
            return validate_pydantic(data_dict, target_class)
        else:
            return data_dict

    def _load(
        self,
        stream: IO,
        target_class: Type[T_Dataclass] | None = EntityList,
        **kwargs,
    ) -> dict | T_Dataclass | Any:
        """
        Load JSON data from a file-like object (e.g., a context manager).
        # TODO: test with: fake_file = StringIO('{"key": "value"}')

        """
        data_dict = json.load(stream)
        return self._validate(data_dict, target_class)

    def _loads(self, data: Union[str, bytes], target_class: Type[T_Dataclass] | None) -> dict | T_Dataclass | Any:
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        try:
            data_dict = json.loads(data)
            return self._validate(data_dict, target_class)
        except Exception as e:
            logger.error("Failed to parse JSON data from string or bytes.")
            raise e

    def load(
        self,
        source: Union[str, Path, IO[str], IO[bytes], bytes],
        target_class: Type[T_Dataclass] | None = EntityList,
        **kwargs,
    ) -> Any:
        """
        The load function handles:
        - file paths (str/Path)
        - file-like objects (IO)
        - raw JSON strings or bytes (e.g., from requests)
        """
        try:
            if isinstance(source, str):
                source_path = Path(source)
                if source_path.exists():
                    source = source_path

            if isinstance(source, Path):
                with open(source, self.read_mode, encoding="utf-8") as f:
                    return self._load(f, target_class)
            elif hasattr(source, "read"):
                # File-like object
                stream = cast(IO, source)
                return self._load(stream, target_class)
            elif isinstance(source, (bytes, str)):
                return self._loads(source, target_class)
            else:
                raise TypeError(f"Unsupported source type for JSON loading: {type(source)}")

        except ValueError as e:
            logger.error(f"Could not validate the provided data at {source} as {target_class}")
            raise e
        except Exception as e:
            logger.error(f"Error in JsonIO adapter: {e}")
            raise e

    def dump(self, destination: str, entity: BaseModel, **kwargs) -> None:
        # LinkML-based version JSONDumper().dump
        with open(destination, self.write_mode) as f:
            json.dump(entity.model_dump(), f, indent=2)


class YamlIO(IOAdapter):
    read_mode: str = "r"
    write_mode: str = "w"
    """
    Adapter for loading from Yaml file/stream
    Assuming yaml files can be directly loaded by linkml
    """

    def _validate(self, data_dict: dict, target_class: Type[T_Dataclass] | Any | None) -> T_Dataclass | Any | dict:
        if target_class is None:
            return data_dict  # return plain dict
        if issubclass(target_class, EntityList):
            return YAMLLoader().load(data_dict, target_class)
            # Note we do not need to depend on linkml here
            # return validate_dataclass(data_dict, EntityList)
        elif is_dataclass(target_class):
            return validate_dataclass(data_dict, target_class)
        elif issubclass(target_class, BaseModel):
            return validate_pydantic(data_dict, target_class)
        else:
            return data_dict

    def _load(
        self,
        stream: IO,
        target_class: Type[T_Dataclass] | None = EntityList,
        **kwargs,
    ) -> dict | T_Dataclass | Any:
        """
        Load YAML data from a file-like object (e.g., a context manager).
        # TODO: test with: fake_file = StringIO('{"key": "value"}')

        """
        data_dict = yaml.safe_load(stream)
        return self._validate(data_dict, target_class)

    def _loads(self, data: Union[str, bytes], target_class: Type[T_Dataclass] | None) -> dict | T_Dataclass | Any:
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        try:
            data_dict = json.loads(data)
            return self._validate(data_dict, target_class)
        except Exception as e:
            logger.error("Failed to parse JSON data from string or bytes.")
            raise e

    def load(
        self,
        source: Union[str, Path, IO[str], IO[bytes], bytes],
        target_class: Type[T_Dataclass] | None = EntityList,
        **kwargs,
    ) -> BaseModel | EntityList | dict | Any:
        """
        The load function handles:
        - file paths (str/Path)
        - file-like objects (IO)
        - raw YAML strings or bytes (e.g., from requests)
        """
        try:
            if isinstance(source, str):
                source_path = Path(source)
                if source_path.exists():
                    source = source_path

            if isinstance(source, Path):
                with open(source, self.read_mode, encoding="utf-8") as f:
                    return self._load(f, target_class)
            elif hasattr(source, "read"):
                # File-like object
                stream = cast(IO, source)
                return self._load(stream, target_class)
            elif isinstance(source, (bytes, str)):
                return self._loads(source, target_class)
            else:
                raise TypeError(f"Unsupported source type for YAML loading: {type(source)}")

        except ValueError as e:
            logger.error(f"Could not validate the provided data at {source} as {target_class}")
            raise e
        except Exception as e:
            logger.error(f"Error in YamlIO adapter: {e}")
            raise e

    def dump(self, destination: str, entity: EntityList, fn: Callable = YAMLDumper().dump, **kwargs):
        raise NotImplementedError


class CsvIO(IOAdapter):
    read_mode: str = "r"
    write_mode: str = "w"
    """
    Public interace for the Csv Adapter
    Actual implementation is in persistence/dataframe adapter
    """

    def load(self, source: Union[str, Path, IO[str], IO[bytes]], **kwargs):
        try:
            from pypeh.adapters.outbound.persistence.dataframe import CsvIOImpl
        except ImportError:
            message = "The CsvIO class requires the 'dataframe_adapter' module. Please install it."
            logging.error(message)
            raise ImportError(message)
        return CsvIOImpl().load(source, **kwargs)

    def dump(self, source: str, **kwargs):
        pass


class ExcelIO(IOAdapter):
    read_mode: str = "rb"
    write_mode: str = "wb"
    """
    Public interface for Excel repository
    Actual implementation is in external/persistence/dataframe adapter
    """

    # source = StringIO(response.text)
    # df = pd.read_csv(source)

    def load(
        self, source: Union[str, Path, IO[str], IO[bytes]], validation_layout: DataLayout | None = None, **kwargs
    ) -> dict:
        try:
            from pypeh.adapters.outbound.persistence.dataframe import ExcelIOImpl
        except ImportError:
            message = "The ExcelIO class requires the 'dataframe_adapter' module. Please install it."
            logging.error(message)
            raise
        return ExcelIOImpl().load(source, validation_layout=validation_layout, **kwargs)

    def dump(self, source: str, **kwargs):
        pass


class RdfIO(IOAdapter):
    read_mode: str = "r"
    write_mode: str = "w"

    def _validate(self, graph: Graph, target_class: Type[Union[BaseModel, YAMLRoot]]):
        schema_view = get_schema_view()
        # extract info from graph and transform to relevant dataclass
        rdf_loader = RDFLibLoader()
        entities = rdf_loader.from_rdf_graph(graph, schema_view, target_class)
        return entities

    def load(self, source: Union[str, bytes], **kwargs) -> Graph:
        if isinstance(source, bytes):
            source = source.decode("utf-8")
        format = "rdf"
        if format in kwargs:
            format = kwargs.pop("format")
        # Assume every graph consists of quads (required for nanopubs)
        g = Graph()
        # restrict dataset to single graph
        g.parse(source, format=format)
        return g


class JsonldIO(RdfIO):
    read_mode: str = "r"
    write_mode: str = "w"

    def load(self, source: Union[str, bytes], **kwargs) -> Graph:
        return super().load(source, format="json-ld", **kwargs)


class TrigIO(RdfIO):
    read_mode: str = "r"
    write_mode: str = "w"

    def load(self, source: Union[str, bytes], **kwargs) -> Graph:
        return super().load(source, format="trig", **kwargs)


class TurtleIO(RdfIO):
    read_mode: str = "r"
    write_mode: str = "w"

    def load(self, source: Union[str, bytes], **kwargs) -> Graph:
        return super().load(source, format="ttl", **kwargs)


class IOAdapterFactory:
    _adapters = {
        "json": JsonIO,
        "yaml": YamlIO,
        "yml": YamlIO,
        "csv": CsvIO,
        "xlsx": ExcelIO,
        "xls": ExcelIO,
        "rdf": RdfIO,
        "trig": TrigIO,
        "jsonld": JsonldIO,
        "ttl": TurtleIO,
    }

    @classmethod
    def register_adapter(cls, format: str, adapter_class: Type[IOAdapter]) -> None:
        cls._adapters[format.lower()] = adapter_class

    @classmethod
    def create(cls, format: str, **kwargs) -> IOAdapter:
        adapter_class = cls._adapters.get(format.lower())
        if not adapter_class:
            raise ValueError(f"No adapter registered for dataformat: {format}")
        return adapter_class(**kwargs)
