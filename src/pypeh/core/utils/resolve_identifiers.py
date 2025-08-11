from __future__ import annotations

import logging
import re

from pathlib import Path
from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from pypeh.core.models.uri_regex import PID_PATTERN
from pypeh.core.models.constants import DomainNameEnum, LocationEnum
from pypeh.core.models import uri_regex

if TYPE_CHECKING:
    from typing import Optional, Mapping, Union

logger = logging.getLogger(__name__)


def validate_uri(input):
    return uri_regex.uri_validator.match(input)


def validate_uri_reference(input):
    return uri_regex.uri_validator.match(input) or uri_regex.uri_relative_ref_validator.match(input)


def validate_curie(input):
    return uri_regex.curie_validator.match(input)


def validate_rel_path(input):
    return uri_regex.relative_path_pattern.match(input)


def is_url(input: str) -> bool:
    return bool(uri_regex.url_validator.match(input))


def _resolve_local_path(path: str, base_path: Optional[Path] = None) -> bool:
    """
    Validate if a local path exists relative to the base path.
    """
    if base_path is None:
        full_path = Path(path)
    else:
        full_path = base_path / path

    if not full_path.exists():
        logger.error(f"Provided path {full_path} could not be resolved. No such file or directory.")
        raise FileNotFoundError()

    return True


def identifier_to_locator(identifier: str, identifier_type: LocationEnum) -> str:
    if identifier_type == LocationEnum.PID:
        url = f"{DomainNameEnum.RESOLVE_PID.value}/{identifier}"
    else:
        url = identifier

    return url


def _resolve_response_code(response_code: int, identifier: str, identifier_type: LocationEnum) -> bool:
    if identifier_type == LocationEnum.PID:
        if response_code == 2:
            raise ValueError(f"Something unexpected went wrong during handle resolution of {identifier}.")
        elif response_code == 100:
            raise ValueError(f"Handle {identifier} Not Found.")
        elif response_code == 200:
            raise ValueError(
                f"Values Not Found. The handle {identifier} exists but has no values (or no values according to the types and "
                f"indices specified)."
            )
        elif response_code == 1:
            return True
        else:
            raise SystemError("An unexpected server error occurred.")
    elif identifier_type == LocationEnum.LOCAL:
        raise ValueError("Cannot resolve response for local file.")
    else:
        return response_code == HTTPStatus.OK


def assign_location_enum(s: str) -> Optional[LocationEnum]:
    # Check for URI
    if validate_uri(s):
        return LocationEnum.URI

    elif validate_rel_path(s):
        return LocationEnum.LOCAL

    # Check for CURIE
    elif validate_curie(s):
        return LocationEnum.CURIE

    # Check for PID (basic check for common PID patterns)
    # TODO: check this, this is very superficial
    elif re.match(PID_PATTERN, s):
        return LocationEnum.PID

    else:
        # assuming path is local
        return LocationEnum.LOCAL


def resolve_curie(input_str: str, namespaces: Mapping[str, str|None]) -> str:
    prefix, suffix = input_str.split(":")
    resolved_prefix = namespaces.get(prefix, None)
    if resolved_prefix is None:
        raise ValueError("Namespace of provided CURIE {input_str} not part of context.")
    return f"{resolved_prefix} / {suffix}"


def resource_path(path_or_url: Union[str, Path]) -> Union[Path, str]:
    """Return a Path object for local paths, or keep URLs as strings."""
    parsed = urlparse(str(path_or_url))
    if parsed.scheme and parsed.netloc:
        return path_or_url  # It's a URL
    else:
        return Path(path_or_url)  # It's a local path
