import fsspec
import ntpath
import pytest

from types import SimpleNamespace

import pypeh.adapters.persistence.filesystem as filesystem

from pypeh.adapters.persistence.filesystem import (
    ensure_filesystem_directory,
    ensure_filesystem_parent_directory,
    filesystem_parent,
    join_filesystem_path,
)


def test_join_filesystem_path_preserves_absolute_prefix():
    file_system = fsspec.filesystem("file")

    assert join_filesystem_path(file_system, "/tmp", "pypeh", "file.xlsx") == (
        "/tmp/pypeh/file.xlsx"
    )


def test_filesystem_parent():
    file_system = fsspec.filesystem("memory")

    assert filesystem_parent(file_system, "bucket/path/file.xlsx") == (
        "bucket/path"
    )
    assert filesystem_parent(file_system, "file.xlsx") == ""


@pytest.mark.core
def test_local_filesystem_parent_handles_windows_separators(monkeypatch):
    file_system = fsspec.filesystem("file")
    monkeypatch.setattr(filesystem, "os", SimpleNamespace(path=ntpath))

    assert filesystem_parent(
        file_system, r"C:\Users\runner\nested\study.yaml"
    ) == (r"C:\Users\runner\nested")
    assert (
        filesystem_parent(file_system, "C:/Users/runner/nested/study.json")
        == "C:/Users/runner/nested"
    )


def test_ensure_filesystem_directories():
    file_system = fsspec.filesystem("memory")

    ensure_filesystem_directory(file_system, "bucket/data")
    ensure_filesystem_parent_directory(file_system, "bucket/export/file.xlsx")

    assert file_system.isdir("bucket/data")
    assert file_system.isdir("bucket/export")
