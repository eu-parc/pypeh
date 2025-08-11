import pytest

from pypeh import Session
from tests.test_utils.dirutils import get_absolute_path

from pypeh.adapters.outbound.export.xlsx import ExportXlsxAdapter

STUDYINFO_HEADERS = ["THIS INFORMATION IS PROVIDED BY PARC DATA MANAGEMENT TEAM", "...2", "...3"]
CODEBOOK_METADATA = {
    "Codebook Reference": "PARCAlignedStudies_adults_v2.4",
    "Codebook Name": "PARCAlignedStudies_adults",
    "Codebook Version": "2.4",
}


class TestExportXlsx:
    @pytest.mark.export
    def test_export_data_template(self, monkeypatch):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path("./input/data_template"))
        session = Session()
        session.load_persisted_cache()
        data_layout = session.cache.get("TEST_DATA_LAYOUT", "DataLayout")

        output_path = get_absolute_path("./output/data_template/test.xlsx")
        adapter = ExportXlsxAdapter()
        result = adapter.export_data_template(
            data_layout, output_path, studyinfo_header_list=STUDYINFO_HEADERS, codebook_metadata_dict=CODEBOOK_METADATA
        )
        assert isinstance(result, bool)
        assert result
