from __future__ import annotations

import os


def join_filesystem_path(file_system, *parts: str) -> str:
    sep = getattr(file_system, "sep", "/")
    cleaned_parts = [str(part).strip(sep) for part in parts if str(part)]
    if not cleaned_parts:
        return ""
    first = str(parts[0])
    prefix = sep if first.startswith(sep) else ""
    return prefix + sep.join(cleaned_parts)


def ensure_filesystem_directory(file_system, path: str) -> None:
    try:
        file_system.makedirs(path, exist_ok=True)
    except TypeError:
        if not file_system.exists(path):
            file_system.makedirs(path)


def filesystem_parent(file_system, path: str) -> str:
    protocol = file_system.protocol
    if protocol == "file" or (
        isinstance(protocol, (list, tuple)) and "file" in protocol
    ):
        # Local paths use the host OS separator, which may differ from
        # fsspec's separator (notably for Windows drive paths).
        return os.path.dirname(path)

    sep = getattr(file_system, "sep", "/")
    stripped = path.rstrip(sep)
    if sep not in stripped:
        return ""
    return stripped.rsplit(sep, 1)[0]


def ensure_filesystem_parent_directory(file_system, path: str) -> None:
    parent = filesystem_parent(file_system, path)
    if not parent:
        return
    ensure_filesystem_directory(file_system, parent)
