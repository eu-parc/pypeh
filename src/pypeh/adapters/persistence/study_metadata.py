"""Lossless YAML/JSON serialization for the study-metadata tree."""

from __future__ import annotations

import json
import math
import yaml

from typing import Any, Literal


def _validate_metadata_value(
    value: Any, path: str, open_containers: set[int]
) -> None:
    if type(value) in (str, int, bool, type(None)):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError(f"Study metadata {path} contains {value!r}.")
        return
    if type(value) not in (dict, list):
        raise ValueError(
            f"Study metadata {path} has unsupported type "
            f"{type(value).__name__}; expected JSON-compatible values."
        )
    if id(value) in open_containers:
        raise ValueError(f"Study metadata {path} contains a cycle.")
    open_containers.add(id(value))
    if isinstance(value, dict):
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError(
                    f"Study metadata {path} has a non-string key "
                    f"of type {type(key).__name__}."
                )
            _validate_metadata_value(item, f"{path}[{key!r}]", open_containers)
    else:
        for index, item in enumerate(value):
            _validate_metadata_value(item, f"{path}[{index}]", open_containers)
    open_containers.remove(id(value))


def serialize_study_metadata(
    metadata: dict[str, Any], file_format: Literal["yaml", "json"]
) -> str:
    """Serialize a plain metadata tree without the lossy PEH dumper."""
    if file_format not in {"yaml", "json"}:
        raise NotImplementedError(
            "Study metadata serialization supports file_format='yaml' "
            f"or 'json'. Got {file_format!r}."
        )
    if type(metadata) is not dict:
        raise ValueError("Study metadata must be a dict.")
    _validate_metadata_value(metadata, "metadata", set())
    if file_format == "json":
        return json.dumps(
            metadata, indent=2, ensure_ascii=True, allow_nan=False
        )
    return yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True)
