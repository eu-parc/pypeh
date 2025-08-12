from __future__ import annotations

import logging
import os

from peh_model.peh import DataLayout, Observation, NamedThing
from typing import TYPE_CHECKING, cast

from pypeh.adapters.outbound.validation.pandera_adapter.dataops import DataFrameAdapter
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
from pypeh.adapters.outbound.persistence.hosts import HostFactory, LocalStorageProvider
from pypeh.core.interfaces.outbound.persistence import PersistenceInterface
from pypeh.core.cache.utils import load_entities_from_tree

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
        self, persistence_adapter: PersistenceInterface, path: str, validation_layout: DataLayout | None = None
    ):
        """Load a binary resource and return its content as tabular data in a dataframe"""
        try:
            io_adapter = persistence_adapter()
            return io_adapter.load(path, validation_layout=validation_layout)
        except Exception as _:
            return ValidationError(
                message="File could not be read or validated",
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

    def load_resource(self, resource_identifier: str, resource_type: str) -> NamedThing | None:
        """Load resource into cache. First checks the cache,
        then configured persisted cache, and finally the `ImportConfig`"""
        ret = self.get_resource(resource_identifier, resource_type)
        if isinstance(ret, TypedLazyProxy):
            ret = self.resolve_typed_lazy_proxy(ret)
        if ret is not None:
            return ret

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
        # run validation
        adapter = DataFrameAdapter()
        return adapter.validate(data, observation, self.cache)
