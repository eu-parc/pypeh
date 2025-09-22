from __future__ import annotations

import os
import importlib
import logging
import peh_model.peh as peh

from typing import TYPE_CHECKING, TypeVar, Sequence, Dict, Generic

from pypeh.core.cache.containers import CacheContainer, CacheContainerFactory
from pypeh.core.models.constants import ObservablePropertyValueType
from pypeh.core.models.proxy import TypedLazyProxy
from pypeh.core.models.settings import (
    LocalFileConfig,
    ImportConfig,
    ConnectionConfig,
    ValidatedImportConfig,
    DEFAULT_CONNECTION_LABEL,
)
from pypeh.core.models.typing import T_NamedThingLike, T_DataType
from pypeh.core.models.validation_dto import ValidationConfig
from pypeh.core.models.validation_errors import ValidationError, ValidationErrorLevel, ValidationErrorReportCollection
from pypeh.core.interfaces.outbound.dataops import ValidationInterface
from pypeh.core.cache.utils import load_entities_from_tree
from pypeh.core.session.connections import ConnectionManager
from pypeh.core.utils.resolve_identifiers import is_url

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from polars import DataFrame
    from pydantic_settings import BaseSettings
    from typing import Sequence

T_AdapterType = TypeVar("T_AdapterType")


class Session(Generic[T_AdapterType, T_DataType]):
    _adapter_mapping: dict[str, T_AdapterType] = dict()

    def __init__(
        self,
        *,
        connection_config: ConnectionConfig | Sequence[ConnectionConfig] | None = None,
        default_persisted_cache: str | ConnectionConfig | None = None,
        env_file: str | None = None,
    ):
        """
        Initializes a new pypeh Session.

        Args:
            connection_config (ConnectionConfig | Sequence[ConnectionConfig] | None):
                A (list of) ConnectionConfig instance(s). Allows you to setup connection to local
                or remote repositories.
                Required if a string-based default_persisted_cache is used.
            default_persisted_cache (str | ConnectionConfig | None):
                Specifies the default storage for the session. Can either be:
                    - A string key referring to a connection in connection_config,
                    - A ConnectionConfig instance to directly generate BaseSettings.
        """

        connection_map, default_persisted_cache = self._normalize_configs(connection_config, default_persisted_cache)
        self.connection_manager: ConnectionManager = ConnectionManager(ValidatedImportConfig())
        validated_default_persisted_cache: BaseSettings | None = self._init_default_persisted_cache(
            default_persisted_cache, env_file
        )
        if connection_map is not None:
            import_config = ImportConfig(connection_map=connection_map).to_validated_import_config(_env_file=env_file)
            self.connection_manager = ConnectionManager(import_config)

        if validated_default_persisted_cache is not None:
            self.connection_manager._register_connection_label(
                DEFAULT_CONNECTION_LABEL, validated_default_persisted_cache
            )
        self.cache: CacheContainer = CacheContainerFactory.new()

    def _normalize_configs(
        self,
        connection_config,
        default_persisted_cache,
    ) -> tuple[dict[str, ConnectionConfig], ConnectionConfig | None]:
        """Validates and normalizes configs before init proceeds."""
        connection_map = {}
        # Handle missing connection_config
        if connection_config is None:
            if default_persisted_cache is None:
                default_persisted_cache = self._env_default_persisted_cache()
            elif isinstance(default_persisted_cache, str):
                raise ValueError("String value for default_persisted_cache requires a connection_config")
            elif not isinstance(default_persisted_cache, ConnectionConfig):
                logger.debug("All resources will be loaded as linked open data")
        else:
            if isinstance(connection_config, ConnectionConfig):
                connection_map = {connection_config.label: connection_config}
            elif isinstance(connection_config, Sequence):
                for config in connection_config:
                    if not isinstance(config, ConnectionConfig):
                        raise ValueError("connection_config argument is of wrong type")
                    connection_map[config.label] = config
            else:
                raise ValueError("connection_config argument is of wrong type")

        # Validate string cache references
        validated_default_persisted_cache = None
        if isinstance(default_persisted_cache, str):
            if default_persisted_cache not in connection_map:
                raise ValueError("Default cache string must refer to a key in connection_config")
            validated_default_persisted_cache = connection_map[default_persisted_cache]
        elif isinstance(default_persisted_cache, ConnectionConfig):
            if default_persisted_cache.namespaces is not None:
                logger.warning(
                    "default_persisted_cache has namespaces associated to it. These are ignored."
                    " Use the connection_config to achieve this"
                )
            validated_default_persisted_cache = default_persisted_cache

        return connection_map, validated_default_persisted_cache

    def _env_default_persisted_cache(self) -> ConnectionConfig | None:
        """Derives a default cache config from environment variables."""
        if os.environ.get("DEFAULT_PERSISTED_CACHE_TYPE", "").upper() == "LOCALFILE":
            return LocalFileConfig(env_prefix="DEFAULT_PERSISTED_CACHE_")

    def _init_default_persisted_cache(
        self,
        default_persisted_cache: ConnectionConfig | None,
        env_file: str | None,
    ) -> BaseSettings | None:
        """Creates the BaseSettings instance for the default cache."""
        if isinstance(default_persisted_cache, ConnectionConfig):
            return default_persisted_cache.make_settings(_env_file=env_file)
        return None

    def register_default_adapter(self, interface_functionality: str):
        adapter = None
        match interface_functionality:
            case "validation":
                adapter = ValidationInterface.get_default_adapter_class()
                self._adapter_mapping[interface_functionality] = adapter
            case _:
                raise NotImplementedError()

        return adapter

    def register_adapter(self, interface_functionality: str, adapter: T_AdapterType):
        self._adapter_mapping[interface_functionality] = adapter

    def register_adapter_by_name(
        self,
        interface_functionality: str,
        adapter_module_name: str | None = None,
        adapter_class_name: str | None = None,
    ):
        try:
            adapter_module = importlib.import_module(adapter_module_name)
            adapter = getattr(adapter_module, adapter_class_name)
        except Exception as e:
            logger.error(
                f"Exception encountered while attempting to import the requested {interface_functionality} adapter: {adapter_module_name} - {adapter_class_name}"
            )
            raise e
        self.register_adapter(interface_functionality, adapter)

    def get_adapter(self, interface_functionality: str):
        adapter = self._adapter_mapping.get(interface_functionality)
        if adapter is None:
            adapter = self.register_default_adapter(interface_functionality)
        assert adapter is not None

        return adapter()

    def _root_to_cache(self, root: peh.EntityList) -> bool:
        for entity in load_entities_from_tree(root):
            _ = self.cache.add(entity)

        return True

    def _source_to_cache(self, roots: list | peh.EntityList) -> bool:
        if isinstance(roots, list):
            for root in roots:
                ret = self._root_to_cache(root)
                assert ret
        else:
            ret = self._root_to_cache(roots)

        return True

    def load_persisted_cache(self, source: str | None = None, connection_label: str | None = None):
        """Load all resources from either the default cache persistence location or from the provided
        connection into cache. The provided connection_label takes precedence over the default"""
        # get host/connection
        # TODO: fix host calls with unified ConnectionManager
        if connection_label is None:
            logger.info("Using DEFAULT_CONNECTION_LABEL in absence of connection_label")
            connection_label = DEFAULT_CONNECTION_LABEL

        if source is None:
            # TEMP FIX: will only work with filesystems
            source = ""

        with self.connection_manager.get_connection(connection_label=connection_label) as connection:
            roots = connection.load(source, format="yaml")

        ret = self._source_to_cache(roots)
        assert ret

    def load_tabular_data(
        self, source: str, connection_label: str | None = None, validation_layout: peh.DataLayout | None = None
    ) -> dict[str, DataFrame] | ValidationError:
        """
        Load a binary resource and return its content as tabular data in a dataframe
        Args:
            source (str): A path or url pointing to the data to be loaded in.
            connection_label (str | None):
                Optional key pointing to the connection to be used to
                load in the data source. The connection_label should be a key of the provided
                connection_config.
            validation_layout: (DataLayout | None)L Optional DataLayout object used for validation.
        """
        data_schema = None
        if validation_layout is not None:
            data_schema = self.layout_section_elements_to_observable_property_value_types(
                layout=validation_layout,
            )
        try:
            # TODO: fix host calls with unified ConnectionManager
            if is_url(source):
                raise NotImplementedError
            elif connection_label is not None:
                pass
            else:
                connection_label = DEFAULT_CONNECTION_LABEL

            with self.connection_manager.get_connection(connection_label=connection_label) as connection:
                return connection.load(source, validation_layout=validation_layout, data_schema=data_schema)

        except Exception as e:
            return ValidationError(
                message=f"File could not be read or validated: {e}",
                type="File Processing Error",
                level=ValidationErrorLevel.FATAL,
            )

    def get_resource(self, resource_identifier: str, resource_type: str) -> T_NamedThingLike | None:
        """Get resource from cache"""
        ret = self.cache.get(resource_identifier, resource_type)
        if ret is None:
            logger.debug(f"No resource found with identifier {resource_identifier}")

        return ret

    def resolve_typed_lazy_proxy(self, proxy: TypedLazyProxy) -> peh.NamedThing:
        raise NotImplementedError()

    def load_resource(
        self,
        resource_identifier: str,
        resource_type: str,
        resource_path: str | None = None,
        connection_label: str | None = None,
    ) -> T_NamedThingLike | None:
        """Load resource into cache. First checks the cache,
        then configured persisted cache, and finally the `ImportConfig`"""
        # cache
        ret = self.get_resource(resource_identifier, resource_type)
        if ret is not None:
            return ret

        if connection_label is not None:
            with self.connection_manager.get_connection(connection_label=connection_label) as connection:
                # assuming connection points to a file-based system
                # loading entire directory
                logger.debug(f"Loading .yaml files recursively from {connection_label} root directory")
                if resource_path is None:
                    resource_path = ""
                    roots = connection.load(resource_path, format="yaml")
                else:
                    roots = connection.load(resource_path)
                ret = self._source_to_cache(roots)
                assert ret

            # resource should have been loaded into cache
            ret = self.get_resource(resource_identifier, resource_type)
            type_to_cast = getattr(peh, resource_type)
            assert isinstance(ret, type_to_cast)
        else:
            # TODO: use linked data approach
            raise NotImplementedError

        return ret

    def load_project(self, project_identifier: str, connection_label: str | None = None) -> T_NamedThingLike | None:
        return self.load_resource(project_identifier, resource_type="Project", connection_label=connection_label)

    def dump_resource(self, resource_identifier: str, resource_type: str, version: str | None) -> bool:
        return True

    def dump_project(self, project_identifier: str, version: str | None) -> bool:
        return self.dump_resource(project_identifier, resource_type="Project", version=version)

    def get_dataset_validations_dict(
        self,
        observation_list: Sequence[peh.Observation],
        layout: peh.DataLayout,
        dataset_mapping: Dict[str, Dict[str, str | int | Dict[str, Sequence[str]]]],
        data_dict: Dict[str, Dict[str, Sequence] | T_DataType],
    ) -> Dict[str, Sequence[peh.ValidationDesign]] | None:
        return ValidationConfig.get_dataset_validations_dict(observation_list, layout, dataset_mapping, data_dict)

    def get_dataset_identifier_consistency_validations_dict(
        self,
        observation_list: Sequence[peh.Observation],
        layout: peh.DataLayout,
        dataset_mapping: Dict[str, Dict[str, str | int | Dict[str, Sequence[str]]]],
        data_dict: Dict[str, Dict[str, Sequence] | T_DataType],
    ) -> Dict[str, Sequence[peh.ValidationDesign]] | None:
        return ValidationConfig.get_dataset_identifier_consistency_validations_dict(
            observation_list, layout, dataset_mapping, data_dict
        )

    def validate_tabular_data(
        self,
        data: dict[str, Sequence] | DataFrame,
        observation_list: Sequence[peh.Observation],
        dataset_validations: Sequence[peh.ValidationDesign] | None = None,
    ) -> ValidationErrorReportCollection:
        observable_property_ids = set()
        for observation in observation_list:
            if observation.observation_design is None:
                raise ValueError(f"Specified observation {observation.id} has no ObservationDesign")
            observable_property_ids.update(
                observation.observation_design.identifying_observable_property_id_list,
                observation.observation_design.optional_observable_property_id_list,
                observation.observation_design.required_observable_property_id_list,
            )
        observable_properties = [
            op for op in self.cache.get_all("ObservableProperty") if op.id in observable_property_ids
        ]
        assert len(observable_properties) > 0

        validation_adapter = self.get_adapter("validation")
        return validation_adapter.validate(data, observation_list, observable_properties, dataset_validations)

    def layout_section_elements_to_observable_property_value_types(
        self, layout: peh.DataLayout, flatten=False
    ) -> dict[str, ObservablePropertyValueType | dict[str, ObservablePropertyValueType]] | None:
        ret = {}

        sections = getattr(layout, "sections")
        if sections is None:
            raise ValueError("No sections found in DataLayout")
        for section in sections:
            label = getattr(section, "ui_label")
            elements = getattr(section, "elements")
            if elements is None:
                logger.info("DataLayout does not contain elements. Cannot determine observable_entity_value_types.")
                return None
            for element in elements:
                element_label = getattr(element, "label")
                observable_property_id = getattr(element, "observable_property")
                observable_property = self.cache.get(observable_property_id, "ObservableProperty")
                if observable_property is None:
                    logger.info(
                        f"Could not find {observable_property_id} in cache. Cannot determine observable_property_value_types. "
                    )
                    return None
                assert isinstance(label, str)
                value_type = getattr(observable_property, "value_type")
                if flatten:
                    ret[element_label] = ObservablePropertyValueType(value_type)
                else:
                    if label not in ret:
                        ret[label] = {}
                    ret[label][element_label] = ObservablePropertyValueType(value_type)

        return ret
