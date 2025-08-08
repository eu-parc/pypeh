import pytest

import logging

from pypeh import Session

from pypeh.adapters.outbound.persistence.serializations import ExcelIO
from pypeh.core.models.validation_errors import ValidationError

from tests.test_utils.dirutils import get_absolute_path

@pytest.mark.session
class TestSessionValidation:
    def test_invalid_file(self):
        excel_path = get_absolute_path("./input/validation_files/invalid_excel.xlsx")
        session = Session()
        result = session.load_tabular_data(ExcelIO, excel_path)
        assert isinstance(result, ValidationError)
        assert result.type == "File Processing Error"

    def test_valid_file(self):
        excel_path = get_absolute_path("./input/validation_files/valid_excel_wrong_format.xlsx")
        session = Session()
        result = session.load_tabular_data(ExcelIO, excel_path)
        assert isinstance(result, dict)
        assert len(result) == 1

    def test_invalid_sheets(self, monkeypatch):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path("./input/validation_config"))
        excel_path = get_absolute_path("./input/validation_files/valid_excel_wrong_format.xlsx")

        session = Session()
        session.load_cache()
        layout = session.cache.get("TEST_DATA_LAYOUT", "DataLayout")
        result = session.load_tabular_data(ExcelIO, excel_path, validation_layout=layout)
        assert isinstance(result, ValidationError)
        assert result.type == "File Processing Error"
