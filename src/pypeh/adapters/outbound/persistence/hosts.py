"""
# TODO: add in support for other ManifestRepositories: ROCrate, ...
"""

from __future__ import annotations

import fsspec
import json
import logging
import os
import requests
import urllib3

from abc import abstractmethod
from contextlib import contextmanager
from pathlib import Path
from requests.adapters import HTTPAdapter
from typing import TYPE_CHECKING, Generic, Callable, Any, Optional, Dict
from urllib3.util.retry import Retry
from urllib.parse import urlparse, urljoin

from pypeh.core.interfaces.outbound.persistence import PersistenceInterface
from pypeh.adapters.outbound.persistence import serializations
from pypeh.core.models.typing import T_Dataclass
from pypeh.core.models.settings import LocalFileSettings, S3Settings

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from typing import Optional, Any, Dict, List, Generator, Type, Union
    from pydantic import BaseModel
    from pydantic_settings import BaseSettings
    from pypeh.core.models.transform import FieldMapping


class HostAdapter(PersistenceInterface):
    pass


## fsspec-based file interactions: local or cloud


class FileIO(HostAdapter):
    def __init__(self, file_system: fsspec.AbstractFileSystem | None = None):
        self.file_system = file_system

    @classmethod
    def get_format(cls, path: Union[str, Path]) -> str:
        return os.path.splitext(str(path))[1].lower().lstrip(".")

    def load(self, source: Union[str, Path], format: Optional[str] = None, **kwargs) -> Any:
        """Load data from file using the appropriate adapter."""
        if format is None:
            format = self.get_format(source)
        adapter = serializations.IOAdapterFactory.create(format.lower())
        open_func = self.file_system.open if self.file_system is not None else fsspec.open

        with open_func(source, adapter.read_mode) as f:
            try:
                return adapter.load(f, **kwargs)  # type: ignore ## fsspec does not provide type hints
            except Exception as e:
                logger.error(f"Error in FileIO: {e}")
                raise

    def dump(self, destination: str, entity: BaseModel, **kwargs) -> None:
        raise NotImplementedError


class DirectoryIO(HostAdapter):
    """The DirectoryIO logic only accepts absolute paths"""

    supported_formats = serializations.IOAdapterFactory._adapters.keys()

    def __init__(self, root: str | None = None, protocol: str = "file", **storage_options):
        self.root = root.rstrip("/") if root is not None else None
        self.file_system: fsspec.AbstractFileSystem = fsspec.filesystem(protocol, **storage_options)

    def _resolve_path(self, path: Union[str, Path]) -> str:
        if self.root is not None:
            return f"{self.root}/{str(path)}"
        else:
            return f"{str(path)}"

    def _join_paths(self, root: Any, path: str) -> str:
        return f"{root}/{path}"

    def walk(
        self, source: Union[str, Path], format: Optional[str] = None, maxdepth: int | None = None, **load_options
    ) -> Generator[Any, None, None]:
        """
        Yield data loaded from files in a directory and its subdirectories.
        This implementation assumes that all supported file formats (jsonn, yaml, csv, xslx, xls)
        should be loaded.
        """
        full_source = self._resolve_path(source)
        file_io = FileIO(file_system=self.file_system)

        for root, _, files in self.file_system.walk(full_source, maxdepth=maxdepth):
            for file in files:
                file_path = self._join_paths(root, file)
                inferred_format = FileIO.get_format(file_path)
                if format is not None:
                    if inferred_format != format:
                        continue  # Skip formats other than format
                    yield file_io.load(file_path, format=format, **load_options)

                else:
                    if inferred_format in self.supported_formats:
                        yield file_io.load(file_path, format=inferred_format, **load_options)
                    else:
                        continue  # Skip unsupported formats

    def load(self, source: Union[str, Path], format: Optional[str] = None, maxdepth: int = 1, **load_options) -> Any:
        full_source = self._resolve_path(source)
        file_io = FileIO(file_system=self.file_system)
        if self.file_system.isfile(full_source):
            return file_io.load(full_source, format=format, **load_options)
        elif self.file_system.isdir(full_source):
            return list(self.walk(source=source, format=format, maxdepth=maxdepth, **load_options))
        else:
            logger.error(f"Source {source} could not be resolved as a path")
            raise ValueError

    def dump(self, destination: str, entities: List[BaseModel], **kwargs) -> None:
        pass


class LocalStorageProvider(DirectoryIO):
    def __init__(self, settings: LocalFileSettings, **storage_options):
        super().__init__(root=settings.root_folder, protocol="file", **storage_options)


class S3StorageProvider(DirectoryIO):
    def __init__(self, settings: S3Settings, **storage_options):
        session_kwargs = {**storage_options, **settings.to_s3fs()}
        self.bucket = settings.bucket_name
        super().__init__(root=settings.bucket_name, protocol="s3", **session_kwargs)


## WebIO implementation

CONTENT_TYPE_MAPPING = {
    "application/json": "json",
    "application/xml": "xml",
    "text/xml": "xml",
    "text/csv": "csv",
    "application/rdf+xml": "rdf",
    "application/trig": "trig",
    "text/turtle": "ttl",
    "application/ld+json": "jsonld",
}


class WebIO(HostAdapter):
    def __init__(
        self,
        timeout: int = 30,
        max_retries: int = 3,
        custom_ca_bundle: Optional[str] = None,
        verify_ssl: bool = True,
        user_agent: str | None = None,
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.custom_ca_bundle = custom_ca_bundle
        self.user_agent = user_agent

        # Dictionary to store format adapters
        self.adapters: Dict[str, Callable] = serializations.IOAdapterFactory._adapters
        self.verify_ssl = verify_ssl
        # Create a session with retry strategy
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        retry_strategy = Retry(
            total=self.max_retries,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        if self.user_agent is not None:
            session.headers.update({"User-Agent": self.user_agent})
        if self.custom_ca_bundle:
            session.verify = self.custom_ca_bundle
        elif not self.verify_ssl:
            session.verify = False
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self._open_session = True
        return session

    def _detect_format(self, url: str, content_type: str | None) -> str | None:
        # First try to detect from Content-Type header
        if content_type:
            return CONTENT_TYPE_MAPPING.get(content_type, None)

        # Try to detect from URL extension
        parsed_url = urlparse(url)
        path = Path(parsed_url.path)
        extension = path.suffix.lower().lstrip(".")
        if extension in serializations.IOAdapterFactory._adapters:
            return extension

        return

    def resolve_url(
        self, url: str, format_type: str | None = None, follow_redirects: bool = True, max_redirects: int = 5
    ) -> requests.Response:
        try:
            headers = None
            if format_type:
                headers = {"Accept": format_type}

            response = self.session.get(
                url,
                timeout=self.timeout,
                allow_redirects=follow_redirects,
                stream=True,
                headers=headers,
            )

            # OPTIONAL: Check for manual redirect handling if needed
            if not follow_redirects and response.status_code in [301, 302, 303, 307, 308]:
                redirect_url = response.headers.get("Location")
                if redirect_url:
                    # Handle relative redirects
                    redirect_url = urljoin(url, redirect_url)
                    logger.info(f"Redirect detected: {url} -> {redirect_url}")
                    if max_redirects > 0:
                        return self.resolve_url(
                            redirect_url, follow_redirects=follow_redirects, max_redirects=max_redirects - 1
                        )
                    else:
                        raise requests.exceptions.TooManyRedirects("Maximum redirects exceeded")

            response.raise_for_status()
            return response

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to resolve URL {url}: {e}")
            raise

    def retrieve_data(self, url: str, format_type: Optional[str] = None, **adapter_kwargs) -> Any:
        logger.info(f"Retrieving data from: {url}")

        # Resolve the URL
        response = self.resolve_url(url, format_type=format_type)

        # Get content and metadata
        content = response.content
        content_type = response.headers.get("Content-Type", None)

        # Detect format if not specified
        if format_type is None:
            format_type = self._detect_format(url, content_type)
        else:
            if format_type in CONTENT_TYPE_MAPPING:
                format_type = CONTENT_TYPE_MAPPING[format_type]
            format_type = format_type.lower()
        logger.info(f"Detected format: {format_type}")

        # Check if we have an adapter for this format
        if format_type is not None:
            if format_type not in self.adapters:
                raise ValueError(f"No adapter registered for format: {format_type}")

            else:
                result = serializations.IOAdapterFactory.create(format_type).load(content, target_class=None)
        else:
            raise ValueError("Could not detect format type of request")
        logger.info(f"Successfully processed data with {format_type} adapter")
        return result

    def load(self, source: str, format: str = "json", **kwargs):
        return self.retrieve_data(source, format_type=format, **kwargs)

    def get_metadata(self, url: str) -> Dict[str, Any]:
        try:
            response = self.session.head(url, timeout=self.timeout)
            response.raise_for_status()

            return {
                "url": url,
                "status_code": response.status_code,
                "content_type": response.headers.get("Content-Type"),
                "content_length": response.headers.get("Content-Length"),
                "last_modified": response.headers.get("Last-Modified"),
                "headers": dict(response.headers),
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get metadata for {url}: {e}")
            raise

    def test_connectivity(self, url: str) -> bool:
        try:
            response = self.session.head(url, timeout=self.timeout)
            return response.status_code < 400
        except Exception:
            return False

    def close(self):
        self.session.close()
        self._open_session = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


## initial implementation to database adapter: UNDER CONSTRUCTION


class DatabaseAdapter(HostAdapter, Generic[T_Dataclass]):
    def __init__(self, registry: ResourceRegistry, connection: Optional[Any] = None, **kwargs):
        self.config = kwargs
        self.conn = connection

    @abstractmethod
    def connect(self, **kwargs) -> None:
        pass

    @abstractmethod
    def disconnect(self) -> None:
        pass

    @contextmanager
    def connection(self, **kwargs) -> Generator[None, None, None]:
        try:
            self.connect(**kwargs)
            yield
        finally:
            self.disconnect()

    @abstractmethod
    def query(self, resource_type: str, query_params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def get(self, resource_type: str, resource_id: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def save(self, resource_type: str, data: Dict[str, Any]) -> str:
        pass

    @abstractmethod
    def update(self, resource_type: str, resource_id: str, data: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    def delete(self, resource_type: str, resource_id: str) -> None:
        pass

    def load(self, source: str, target_class: Optional[Type[T_Dataclass]] = None, **kwargs) -> T_Dataclass:
        if "/" not in source:
            raise ValueError(f"Invalid source format: {source}. Expected 'resource_type/resource_id'")

        resource_type, resource_id = source.split("/", 1)
        data = self.get(resource_type, resource_id)

        if target_class is None:
            return data  # type: ignore

        # Use the model validation from your existing code
        if hasattr(target_class, "model_validate"):
            return target_class.model_validate(data)  # type: ignore
        else:
            # Fall back to your existing validation methods
            from pypeh.adapters.outbound.persistence.serializations import validate_dataclass, validate_pydantic
            from dataclasses import is_dataclass

            if is_dataclass(target_class):
                return validate_dataclass(json.dumps(data), target_class)  # type: ignore
            else:
                return validate_pydantic(json.dumps(data), target_class)  # type: ignore

    def dump(self, destination: str, entity: Union[Dict[str, Any], BaseModel], **kwargs) -> None:
        raise NotImplementedError


class ResourceRegistry:
    def __init__(self):
        self.resources = {}

    def register_resource(
        self,
        resource_type: str,
        endpoint: Optional[str] = None,
        field_mapping: Optional[FieldMapping] = None,
        id_field: str = "id",
    ):
        self.resources[resource_type] = {
            "endpoint": endpoint or resource_type,
            "mapping": field_mapping or FieldMapping(),
            "id_field": id_field,
        }


class HostFactory:
    @classmethod
    def default(cls, **kwargs):
        return WebIO(**kwargs)

    @classmethod
    def create(cls, settings: BaseSettings | None, **kwargs) -> HostAdapter:
        if settings is None:
            return cls.default(**kwargs)

        else:
            if isinstance(settings, S3Settings):
                return S3StorageProvider(settings, **kwargs)
            elif isinstance(settings, LocalFileSettings):
                return LocalStorageProvider(settings, **kwargs)
            else:
                me = f"No adapter registered for settings: {type(settings)}"
                logger.warning(me)
                return cls.default()
