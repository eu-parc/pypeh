import pytest
import peh_model.peh as peh

from tests.test_utils.dirutils import get_absolute_path

from pypeh import Session
from pypeh.core.models.validation_errors import ValidationErrorReport


@pytest.mark.end_to_end
class TestSessionDefaultLocalFile:
    def test_end_to_end_dataframe_validation(self, monkeypatch):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path("./input/test_01/config"))

        session = Session()
        session.load_persisted_cache()

        layout = session.cache.get("peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA", "DataLayout")
        assert isinstance(layout, peh.DataLayout)

        excel_path = get_absolute_path("./input/test_01/validation_test_01_data.xlsx")
        data_dict = session.load_tabular_data(
            source=excel_path,
            validation_layout=layout,
        )
        assert isinstance(data_dict, dict)
        data_df = data_dict["SAMPLE"]
        assert data_df is not None

        validation_result = session.validate_tabular_data(data_df, observation_id="peh:VALIDATION_TEST_SAMPLE_METADATA")

        report_to_check = list(validation_result.values())[0]

        assert isinstance(report_to_check, ValidationErrorReport)
        assert report_to_check.total_errors == 1
        assert report_to_check.groups[-1].errors[-1].type == "check_categorical"
