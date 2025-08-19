from __future__ import annotations

import dataclasses
import logging

from abc import abstractmethod
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource
from pydantic import BaseModel, Field, ValidationError
from typing import Optional, Type, TypeVar, Generic, cast

from pypeh.core.utils.namespaces import ImportMap

logger = logging.getLogger(__name__)

T_BaseSettings = TypeVar("T_BaseSettings", bound=BaseSettings)


class FileSystemSettings(BaseSettings):
    pass


class DataBaseSettings(BaseSettings):
    pass


class LocalFileSettings(FileSystemSettings):
    root_folder: Optional[str] = None


class S3Settings(FileSystemSettings):
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_session_token: Optional[str] = None
    aws_region: Optional[str] = "us-east-1"
    endpoint_url: Optional[str] = None
    bucket_name: str

    def to_s3fs(self):
        return {
            "key": self.aws_access_key_id,
            "secret": self.aws_secret_access_key,
            "token": self.aws_session_token,
            "client_kwargs": {"region_name": self.aws_region},
            "endpoint_url": self.endpoint_url,
        }


class ConnectionConfig(BaseModel, Generic[T_BaseSettings]):
    """
    ConnectionConfigs can be given a label as well as a list of namespaces
    the connection will be used for.
    """

    label: str = "default"
    namespaces: list | None = None
    env_prefix: str = "DEFAULT_"
    config_dict: Optional[dict[str, str]] = Field(default_factory=dict)

    @abstractmethod
    def settings_class(cls) -> Type[T_BaseSettings]:
        """Return the settings class this config is for."""
        ...

    def _create_customised_settings_class(self, _env_file: Optional[str]) -> Type[T_BaseSettings]:
        base_cls = self.settings_class()
        env_prefix = self.env_prefix

        class CustomisedSettings(base_cls):  # type: ignore
            model_config = SettingsConfigDict(
                env_prefix=env_prefix,
                env_file=_env_file,
                extra="ignore",
            )

            @classmethod
            def settings_customise_sources(
                cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings
            ) -> tuple[PydanticBaseSettingsSource, ...]:
                if _env_file is not None:
                    return (
                        init_settings,
                        dotenv_settings,
                        env_settings,
                        file_secret_settings,
                    )
                else:
                    return (
                        init_settings,
                        env_settings,
                        file_secret_settings,
                    )

        return cast(Type[T_BaseSettings], CustomisedSettings)

    def make_settings(self, _env_file: Optional[str] = ".env") -> T_BaseSettings:
        config_data = self.config_dict or {}

        settings_cls = self._create_customised_settings_class(_env_file)

        try:
            return settings_cls.model_validate(config_data)
        except ValidationError as e:
            raise ValueError(f"Failed to load config with prefix '{self.env_prefix}': {e}") from e


class LocalFileConfig(ConnectionConfig[LocalFileSettings]):
    env_prefix: str = "LOCALFILE_"
    config_dict: dict[str, str] = Field(default_factory=dict)

    def settings_class(self) -> Type[LocalFileSettings]:
        return LocalFileSettings


class S3Config(ConnectionConfig[S3Settings]):
    env_prefix: str = "S3_"
    config_dict: dict[str, str] = Field(default_factory=dict)

    def settings_class(self) -> Type[S3Settings]:
        return S3Settings


@dataclasses.dataclass
class ValidatedImportConfig:
    connection_map: dict[str, BaseSettings]
    import_map: ImportMap | None

    def get_connection(self, namespace: str) -> BaseSettings | None:
        if self.import_map is not None:
            connection_str = self.import_map.get(namespace)
        else:
            logger.debug(f"ImportMap is empty, cannot resolve {namespace}")
            return None
        if connection_str is not None:
            return self.connection_map.get(connection_str, None)


class ImportConfig(BaseModel):
    connection_map: dict[str, ConnectionConfig]

    @classmethod
    def dict_to_trie(cls, namespace_map: dict[str, str]) -> ImportMap:
        new_import_map = ImportMap()
        for key, value in namespace_map.items():
            new_import_map[key] = value
        return new_import_map

    @classmethod
    def config_to_settings(cls, connection_map: dict[str, ConnectionConfig]) -> dict[str, BaseSettings]:
        return {key: value.make_settings() for key, value in connection_map.items()}

    def to_validated_import_config(self) -> ValidatedImportConfig:
        import_map = {}
        if self.connection_map is not None:
            for label, config in self.connection_map.items():
                if config.namespaces is not None:
                    for namespace in config.namespaces:
                        import_map[namespace] = label
        connection_map = self.config_to_settings(self.connection_map)
        import_trie = None
        if len(import_map) > 0:
            import_trie = self.dict_to_trie(import_map)
        return ValidatedImportConfig(connection_map=connection_map, import_map=import_trie)
