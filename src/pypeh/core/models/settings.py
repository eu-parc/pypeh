from __future__ import annotations

import dataclasses
import logging
import os

from abc import abstractmethod
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource
from pydantic import BaseModel, Field, ValidationError, model_validator
from typing import Optional

from pypeh.core.utils.namespaces import ImportMap

logger = logging.getLogger(__name__)


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
    bucket_name: str

    model_config = SettingsConfigDict(env_file=".env")

    def to_s3fs(self):
        return {
            "key": self.aws_access_key_id,
            "secret": self.aws_secret_access_key,
            "token": self.aws_session_token,
            "client_kwargs": {"region_name": self.aws_region},
        }


class SettingsConfig(BaseModel):
    @abstractmethod
    def make_settings(self) -> FileSystemSettings:
        raise NotImplementedError


class LocalFileConfig(SettingsConfig):
    def make_settings(self) -> LocalFileSettings:
        settings = LocalFileSettings()
        if "DEFAULT_CACHE_PERSISTENCE_LOCALFILE_ROOT" in os.environ:
            settings.root_folder = os.environ["DEFAULT_CACHE_PERSISTENCE_LOCALFILE_ROOT"]
        return settings


class S3Config(SettingsConfig):
    env_prefix: str = "S3_"
    config_dict: Optional[dict[str, str]] = Field(default_factory=dict)

    def make_settings(self) -> S3Settings:
        """
        Translate config dict into S3Settings with the option to
        specify the prefix to be used to find the correct details in the .env
        Needed in case we need to connect to different S3 buckets.
        """
        config_data = self.config_dict or {}

        class CustomisedSettings(S3Settings):
            @classmethod
            def settings_customise_sources(
                cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings
            ) -> tuple[PydanticBaseSettingsSource, ...]:
                return (
                    init_settings,
                    dotenv_settings,
                    env_settings,
                    file_secret_settings,
                )

        CustomisedSettings.model_config = SettingsConfigDict(env_prefix=self.env_prefix, env_file=".env")

        try:
            return CustomisedSettings(**config_data)
        except ValidationError as e:
            raise ValueError(f"Failed to load config with prefix '{self.env_prefix}': {e}") from e


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
    connection_map: dict[str, SettingsConfig]
    import_map: dict[str, str] | None

    @classmethod
    def dict_to_trie(cls, namespace_map: dict[str, str]) -> ImportMap:
        new_import_map = ImportMap()
        for key, value in namespace_map.items():
            new_import_map[key] = value
        return new_import_map

    @classmethod
    def config_to_settings(cls, connection_map: dict[str, SettingsConfig]) -> dict[str, BaseSettings]:
        return {key: value.make_settings() for key, value in connection_map.items()}

    @model_validator(mode="after")
    def validate_import_targets(self):
        if self.import_map is not None:
            for target in self.import_map.values():
                if target not in self.connection_map:
                    raise ValueError(f"Import target {target} missing from connection_map")

        return self

    def to_validated_import_config(self) -> ValidatedImportConfig:
        connection_map = self.config_to_settings(self.connection_map)
        import_map = None
        if self.import_map is not None:
            import_map = self.dict_to_trie(self.import_map)
        return ValidatedImportConfig(connection_map=connection_map, import_map=import_map)
