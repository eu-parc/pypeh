from __future__ import annotations

import logging
import os

from peh_model.peh import NamedThing, Observation, DataLayout
from typing import TYPE_CHECKING, Sequence, cast

from pypeh.core.cache.containers import CacheContainer, CacheContainerFactory
from pypeh.core.models.proxy import TypedLazyProxy
from pypeh.core.models.settings import (
    LocalFileConfig,
    ImportConfig,
    LocalFileSettings,
    SettingsConfig,
    ValidatedImportConfig,
)
from pypeh.core.models.typing import T_NamedThingLike
from pypeh.core.models.validation_errors import ValidationError, ValidationErrorLevel, ValidationErrorReportCollection
from pypeh.core.services.dataops import ValidationService
from pypeh.adapters.outbound.persistence.hosts import HostFactory, LocalStorageProvider
from pypeh.core.cache.utils import load_entities_from_tree
from pypeh.core.utils.resolve_identifiers import is_url

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from polars import DataFrame
    from pydantic_settings import BaseSettings
    from typing import Dict, Sequence


class Session:
    def __init__(
        self,
        *,
        connection_config: SettingsConfig | Dict[str, SettingsConfig] | None = None,
        import_map: Dict[str, str] | None = None,
        default_persisted_cache: str | SettingsConfig | None = None,
    ):
        """
        Initializes a new pypeh Session.

        Args:
            connection_config (SettingsConfig] | Dict[str, SettingsConfig] | None):
                A mapping of connection identifiers to SettingsConfig instances. Or
                a single SettingsConfig if all identifiers can be resolved by means of
                a single connection.
                Required if using an import_map or a string-based default_persisted_cache.
            import_map (Dict[str, str] | None):
                Optional mapping relating namespaces to connection instances in the connection_config.
                Requires connection_config to be provided. If import_map is provided then the length of
                import_map should be the same as the length of the connection_config.
            default_persisted_cache (str | SettingsConfig | None):
                Specifies the default storage for the session. Can either be:
                    - A string key referring to a connection in connection_config,
                    - A SettingsConfig instance to directly generate BaseSettings.
        """

        connection_config, default_persisted_cache = self._normalize_configs(
            connection_config, import_map, default_persisted_cache
        )

        self.import_config: ValidatedImportConfig | None = None
        if isinstance(connection_config, dict):
            self.import_config = ImportConfig(
                connection_map=connection_config,
                import_map=import_map,
            ).to_validated_import_config()

        self.default_persisted_cache: BaseSettings | None = self._init_default_persisted_cache(
            default_persisted_cache, connection_config
        )

        self.cache: CacheContainer = CacheContainerFactory.new()

    def _normalize_configs(
        self,
        connection_config,
        import_map,
        default_persisted_cache,
    ) -> tuple[SettingsConfig | dict[str, SettingsConfig] | None, str | SettingsConfig | None]:
        """Validates and normalizes configs before init proceeds."""
        # import_map dependency
        if import_map is not None and connection_config is None:
            raise ValueError("If import_map is provided, connection_config cannot be None")

        # Handle missing connection_config
        if connection_config is None:
            if default_persisted_cache is None:
                default_persisted_cache = self._env_default_persisted_cache()
            elif isinstance(default_persisted_cache, str):
                raise ValueError("String value for default_persisted_cache requires a connection_config")
            elif not isinstance(default_persisted_cache, SettingsConfig):
                logger.debug("All resources will be loaded as linked open data")

        # Validate string cache references
        if isinstance(default_persisted_cache, str):
            if not (isinstance(connection_config, dict) and default_persisted_cache in connection_config):
                raise ValueError("Default cache string must refer to a key in connection_config")

        return connection_config, default_persisted_cache

    def _env_default_persisted_cache(self) -> SettingsConfig | None:
        """Derives a default cache config from environment variables."""
        if os.environ.get("DEFAULT_PERSISTED_CACHE_TYPE", "").upper() == "LOCALFILE":
            return LocalFileConfig(env_prefix="DEFAULT_PERSISTED_CACHE_")

    def _init_default_persisted_cache(
        self,
        default_persisted_cache: str | SettingsConfig | None,
        connection_config: SettingsConfig | dict[str, SettingsConfig] | None,
    ) -> BaseSettings | None:
        """Creates the BaseSettings instance for the default cache."""
        if isinstance(default_persisted_cache, SettingsConfig):
            return default_persisted_cache.make_settings()
        if isinstance(default_persisted_cache, str) and isinstance(connection_config, dict):
            connection = connection_config[default_persisted_cache]
            assert isinstance(connection, BaseSettings)
            return connection
        if isinstance(connection_config, SettingsConfig):
            return connection_config.make_settings()
        return None

    def load_persisted_cache(self):
        """Load all resources from the default cache persistence location into cache"""
        host = HostFactory.create(self.default_persisted_cache)
        if isinstance(host, LocalStorageProvider):
            assert isinstance(self.default_persisted_cache, LocalFileSettings)
            root_folder = self.default_persisted_cache.root_folder
            assert root_folder is not None
            roots = host.load("", format="yaml")
        else:
            raise NotImplementedError
        for root in roots:
            for entity in load_entities_from_tree(root):
                self.cache.add(entity)

    def load_tabular_data(
        self, source: str, connection_id: str | None = None, validation_layout: DataLayout | None = None
    ) -> dict[str, Sequence] | ValidationError:
        """
        Load a binary resource and return its content as tabular data in a dataframe
        Args:
            source (str): A path or url pointing to the data to be loaded in.
            connection_id (str | None):
                Optional key pointing to the connection to be used to
                load in the data source. The connection_id should be a key of the provided
                connection_config.
            validation_layout: (DataLayout | None)L Optional DataLayout object used for validation.
        """
        try:
            if is_url(source):
                host = HostFactory.default()
                return host.retrieve_data(source)
            elif connection_id is not None:
                # TODO: connect this to the connection_config created at setup
                raise NotImplementedError
            elif self.default_persisted_cache is not None:
                host = HostFactory.create(self.default_persisted_cache)
                return host.load(source, validation_layout=validation_layout)
            else:
                raise ValueError("Can't figure out how to load the data")

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

    def resolve_typed_lazy_proxy(self, proxy: TypedLazyProxy) -> NamedThing:
        raise NotImplementedError()

    def load_resource(self, resource_identifier: str, resource_type: str) -> T_NamedThingLike | None:
        """Load resource into cache. First checks the cache,
        then configured persisted cache, and finally the `ImportConfig`"""
        # cache
        ret = self.get_resource(resource_identifier, resource_type)
        if ret is not None:
            return ret
        # setup ContextService

        # TODO: check importmap and create connection
        # if self.import_config is not None:
        # connection = self.import_config.get_connection(resource_identifier)
        # connection.do_stuff()

        # TODO: final step resolve as linked data

        return ret

    def load_project(self, project_identifier: str) -> T_NamedThingLike | None:
        return self.load_resource(project_identifier, resource_type="Project")

    def dump_resource(self, resource_identifier: str, resource_type: str, version: str | None) -> bool:
        return True

    def dump_project(self, project_identifier: str, version: str | None) -> bool:
        return self.dump_resource(project_identifier, resource_type="Project", version=version)

    def validate_tabular_data(
        self,
        data: dict[str, Sequence] | DataFrame,
        observation: Observation | None = None,
        observation_id: str | None = None,
    ) -> ValidationErrorReportCollection:
        # input checks
        if observation is None and observation_id is None:
            raise ValueError("Either observation or observation_id should be provided")
        elif observation is not None and observation_id is not None:
            raise ValueError("Either observation or observation_id should be provided")

        # make objects
        if observation_id is not None:
            resource = self.load_resource(observation_id, "Observation")
            if not isinstance(resource, Observation):
                raise TypeError(f"Resource with id {observation_id} did not return an Observation object")
            observation = cast(Observation, resource)
        assert observation is not None

        observable_property_ids = set()
        for oep_set in observation.observation_design.observable_entity_property_sets:
            observable_property_ids.update(
                oep_set.identifying_observable_property_id_list,
                oep_set.optional_observable_property_id_list,
                oep_set.required_observable_property_id_list,
            )
        observable_properties = [
            op for op in self.cache.get_all("ObservableProperty") if op.id in observable_property_ids
        ]
        assert len(observable_properties) > 0

        # run validation
        # from pypeh.adapters.outbound.validation.pandera_adapter.dataops import DataFrameAdapter
        # adapter = DataFrameAdapter()
        # return adapter.validate(data, observation, observable_properties)

        validation_service = ValidationService()
        return validation_service.validate(data, observation, observable_properties)
