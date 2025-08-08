from __future__ import annotations

import logging
import os
import fsspec

from peh_model.peh import DataLayout

from pypeh.core.cache.containers import CacheContainer, CacheContainerFactory
from pypeh.core.models.settings import LocalFileConfig, ImportConfig, SettingsConfig, ValidatedImportConfig
from pypeh.core.models.settings import LocalFileSettings
from pypeh.core.models.typing import T_NamedThingLike
from pypeh.core.models.validation_errors import ValidationError, ValidationErrorLevel

from typing import TYPE_CHECKING

from pypeh.adapters.outbound.persistence.hosts import DirectoryIO, FileIO
from pypeh.core.interfaces.outbound.persistence import PersistenceInterface

from tests.test_utils.dirutils import get_absolute_path
from pypeh.core.cache.utils import load_entities_from_tree

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from typing import Dict
    from pydantic_settings import BaseSettings


class Session:
    def __init__(
        self,
        *,
        connection_config: SettingsConfig | Dict[str, SettingsConfig] | None = None,
        import_map: Dict[str, str] | None = None,
        default_storage: str | SettingsConfig | None = None,
        cache_type: str | None = None,
    ):
        """
        Initializes a new pypeh Session.

        Args:
            connection_config (SettingsConfig] | Dict[str, SettingsConfig] | None):
                A mapping of connection identifiers to SettingsConfig instances. Or
                a single SettingsConfig if all identifiers can be resolved by means of
                a single connection.
                Required if using an import_map or a string-based default_storage.
            import_map (Dict[str, str] | None):
                Optional mapping relating namespaces to connection instances in the connection_config.
                Requires connection_config to be provided. If import_map is provided then the length of
                import_map should be the same as the length of the connection_config.
            default_storage (str | SettingsConfig | None):
                Specifies the default storage for the session. Can either be:
                    - A string key referring to a connection in connection_config,
                    - A SettingsConfig instance to directly generate BaseSettings.
            cache_type (str | None):
                Indicates the type of caching strategy to use. Defaults to dictionnary-based cache.
        """

        if connection_config is None:
            if "DEFAULT_PERSISTED_CACHE_TYPE" in os.environ:
                if os.environ["DEFAULT_PERSISTED_CACHE_TYPE"].upper()=="LOCALFILE":
                    connection_config = LocalFileConfig(env_prefix="DEFAULT_PERSISTED_CACHE_")
                else:
                    raise NotImplementedError
            else:
                logger.debug("All resources will be loaded as linked open data")

        else:
            if import_map is not None and connection_config is None:
                raise ValueError("If import_map is provided, connection_config cannot be None")

        if isinstance(default_storage, str):
            if (
                connection_config is None
                or not isinstance(connection_config, dict)
                or default_storage not in connection_config
            ):
                raise ValueError("Default storage string must refer to an entry in connection_config")

        if connection_config is not None:
            if isinstance(connection_config, SettingsConfig):
                default_storage = connection_config
            else:
                self.import_config: ValidatedImportConfig = ImportConfig(
                    connection_map=connection_config,
                    import_map=import_map,
                ).to_validated_import_config()

        if isinstance(default_storage, SettingsConfig):
            self.default_storage: BaseSettings = default_storage.make_settings()
        elif isinstance(default_storage, str):
            if connection_config is not None:  # KEEPING TYPER HAPPY
                connection = connection_config[default_storage]
                assert isinstance(connection, BaseSettings)
                self.default_storage: BaseSettings = connection

        self.cache: CacheContainer = CacheContainerFactory.new(cache_type)

    def load_cache(self):
        """Load all resources from the default cache persistence location into cache"""
        if isinstance(self.default_storage, LocalFileSettings):
            host = DirectoryIO()
            roots = host.load(self.default_storage.root_folder, format="yaml")
            for root in roots:
                for entity in load_entities_from_tree(root):
                    self.cache.add(entity)
        else:
            raise NotImplementedError

    def load_tabular_data(self, persistence_adapter: PersistenceInterface, path: str, validation_layout: DataLayout = None):
        """Load a binary resource and return its content as tabular data in a dataframe"""
        try:
            io_adapter = persistence_adapter()
            return io_adapter.load(path, validation_layout=validation_layout)
        except:
            return ValidationError(message="File could not be read or validated", type="File Processing Error", level=ValidationErrorLevel.FATAL)

    def get_resource(self, resource_identifier: str, resource_type: str) -> T_NamedThingLike | None:
        """Get resource from cache"""
        ret = self.cache.get(resource_identifier, resource_type)
        if ret is None:
            logger.debug(f"No resource found with identifier {resource_identifier}")

        return ret

    def load_resource(self, resource_identifier: str, resource_type: str) -> T_NamedThingLike | None:
        """Load resource into cache. First checks the cache,
        then configured persisted cache, and finally the `ImportConfig`"""
        # cache
        ret = self.get_resource(resource_identifier, resource_type)
        if ret is not None:
            return ret
        # setup ContextService

        # check importmap
        if self.import_config is not None:
            connection = self.import_config.get_connection(resource_identifier)
            # connection.do_stuff()

        # TODO: final step resolve as linked data

        return ret

    def load_project(self, project_identifier: str) -> T_NamedThingLike | None:
        return self.load_resource(project_identifier, resource_type="Project")

    def dump_resource(self, resource_identifier: str, resource_type: str, version: str | None) -> bool:
        return True

    def dump_project(self, project_identifier: str, version: str | None) -> bool:
        return self.dump_resource(project_identifier, resource_type="Project", version=version)
