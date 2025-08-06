import pytest

import logging

from pypeh import Session
from pypeh.core.models.settings import SettingsConfig, LocalFileConfig, LocalFileSettings

from tests.test_utils.dirutils import get_absolute_path

@pytest.mark.session
class TestSessionDefaultLocalFile:
    def test_session_default_localfile_settings(self, monkeypatch):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", "/my/root/path")

        session = Session()
        assert isinstance(session.default_storage, LocalFileSettings)
        assert session.default_storage.root_folder == "/my/root/path"

    def test_session_default_localfile_cache(self, monkeypatch):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path("./input/default_localfile_data"))

        session = Session()
        session.load_cache()
        observation = session.cache.get("peh:OBSERVATION_ADULTS_ANALYTICALINFO", "Observation")
        assert observation.id == "peh:OBSERVATION_ADULTS_ANALYTICALINFO"
