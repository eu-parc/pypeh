import pytest
import peh_model.peh as peh
import logging

from pypeh.core.models.constants import ValidationErrorLevel
from tests.test_utils.dirutils import get_absolute_path
from typing import cast

from pypeh import Session
from pypeh.core.models.validation_errors import ValidationError, ValidationErrorReport

logger = logging.getLogger(__name__)


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
        observation_id = "peh:VALIDATION_TEST_SAMPLE_METADATA"
        observation = session.get_resource(resource_identifier=observation_id, resource_type="Observation")
        observation = cast(peh.Observation, observation)
        validation_result = session.validate_tabular_data(data_df, [observation])

        report_to_check = list(validation_result.values())[0]

        assert isinstance(report_to_check, ValidationErrorReport)
        assert report_to_check.total_errors == 1
        assert report_to_check.groups[-1].errors[-1].type == "check_categorical"


@pytest.mark.end_to_end
class TestRoundTrip:
    @pytest.fixture(scope="class")
    def layout_label(self):
        return "peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA"

    @pytest.mark.parametrize("test_label", ["01", "02", "04", "05", "06"])
    def test_load_data(self, monkeypatch, layout_label, test_label):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path(f"./input/test_{test_label}"))
        excel_path = f"validation_test_{test_label}_data.xlsx"

        session = Session()
        cache_path = "config"
        session.load_persisted_cache(source=cache_path)
        layout = session.cache.get(layout_label, "DataLayout")
        assert isinstance(layout, peh.DataLayout)
        data_dict = session.load_tabular_data(
            source=excel_path,
            validation_layout=layout,
        )
        assert isinstance(data_dict, dict)
        assert len(data_dict) > 0

    @pytest.mark.parametrize("test_label", ["01", "02"])
    def test_basic_roundtrip(self, monkeypatch, layout_label, test_label):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path(f"./input/test_{test_label}"))
        excel_path = f"validation_test_{test_label}_data.xlsx"

        session = Session()
        cache_path = "config"
        session.load_persisted_cache(source=cache_path)
        layout = session.cache.get(layout_label, "DataLayout")
        assert isinstance(layout, peh.DataLayout)
        data_dict = session.load_tabular_data(
            source=excel_path,
            validation_layout=layout,
        )
        assert isinstance(data_dict, dict)
        assert len(data_dict) > 0

        data_df = data_dict["SAMPLE"]
        assert data_df is not None

        observation_id = "peh:VALIDATION_TEST_SAMPLE_METADATA"
        observation = session.get_resource(resource_identifier=observation_id, resource_type="Observation")
        observation = cast(peh.Observation, observation)
        validation_result = session.validate_tabular_data(data_df, observation_list=[observation])
        assert validation_result is not None
        assert isinstance(validation_result, dict)
        for validation_report in validation_result.values():
            assert isinstance(validation_report, ValidationErrorReport)
            assert validation_report.total_errors >= 1
            assert len(validation_report.unexpected_errors) == 0
            assert sum(v for v in validation_report.error_counts.values()) == validation_report.total_errors

    @pytest.mark.parametrize(
        "test_label",
        [
            "03",
        ],
    )
    def test_sheet_name_round_trip(self, monkeypatch, layout_label, test_label):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path(f"./input/test_{test_label}"))
        excel_path = f"validation_test_{test_label}_data.xlsx"

        session = Session()
        cache_path = "config"
        session.load_persisted_cache(source=cache_path)
        layout = session.cache.get(layout_label, "DataLayout")
        assert isinstance(layout, peh.DataLayout)
        ret = session.load_tabular_data(
            source=excel_path,
            validation_layout=layout,
        )
        assert isinstance(ret, ValidationError)
        assert "SAMPLETIMEPOINT_BS" in ret.message

    @pytest.mark.parametrize(
        "test_label",
        [
            "03",
        ],
    )
    def test_sheet_name_round_trip_continued(self, monkeypatch, layout_label, test_label):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path(f"./input/test_{test_label}"))
        excel_path = f"validation_test_{test_label}_data.xlsx"

        session = Session()
        cache_path = "config_corrected"
        session.load_persisted_cache(source=cache_path)
        layout = session.cache.get(layout_label, "DataLayout")
        assert isinstance(layout, peh.DataLayout)
        data_dict = session.load_tabular_data(
            source=excel_path,
            validation_layout=layout,
        )
        assert isinstance(data_dict, dict)
        assert len(data_dict) > 0

        sheet_label_to_observation_id = {
            "SAMPLE": "peh:VALIDATION_TEST_SAMPLE_METADATA",
            "SAMPLETIMEPOINT_BSS": "peh:VALIDATION_TEST_SAMPLE_METADATA",
        }

        for sheet_label, data_df in data_dict.items():
            observation_id = sheet_label_to_observation_id[sheet_label]
            observation = session.get_resource(resource_identifier=observation_id, resource_type="Observation")
            observation = cast(peh.Observation, observation)
            validation_result = session.validate_tabular_data(data_df, observation_list=[observation])
            assert isinstance(validation_result, dict)
            for validation_report in validation_result.values():
                assert isinstance(validation_report, ValidationErrorReport)
                logger.info(f"Validation completed for {sheet_label}")

    @pytest.mark.parametrize(
        "test_label",
        [
            "04",
        ],
    )
    def test_full(self, monkeypatch, layout_label, test_label):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path(f"./input/test_{test_label}"))
        excel_path = f"validation_test_{test_label}_data.xlsx"

        session = Session()
        cache_path = "config"
        session.load_persisted_cache(source=cache_path)
        layout = session.cache.get(layout_label, "DataLayout")
        assert isinstance(layout, peh.DataLayout)
        data_dict = session.load_tabular_data(
            source=excel_path,
            validation_layout=layout,
        )
        assert isinstance(data_dict, dict)
        assert len(data_dict) > 0

        observation_id = "peh:VALIDATION_TEST_SAMPLE_METADATA"

        sheet_label_to_observation_id = {
            "SAMPLE": "peh:VALIDATION_TEST_SAMPLE_SAMPLE",
            "SUBJECTUNIQUE": "peh:VALIDATION_TEST_SAMPLE_SUBJECTUNIQUE",
            "SUBJECTTIMEPOINT": "peh:VALIDATION_TEST_SAMPLE_SUBJECTTIMEPOINT",
            "SAMPLETIMEPOINT_BWB": "peh:VALIDATION_TEST_SAMPLE_SAMPLETIMEPOINT_BWB",
        }
        unexpected_errors = 0
        for sheet_label in sheet_label_to_observation_id.keys():
            data_df = data_dict.get(sheet_label, None)
            if data_df is not None:
                observation_id = sheet_label_to_observation_id[sheet_label]
                observation = session.get_resource(observation_id, "Observation")
                assert isinstance(observation, peh.Observation)
                validation_result = session.validate_tabular_data(data_df, observation_list=[observation])
                assert validation_result is not None
                assert isinstance(validation_result, dict)
                for report in validation_result.values():
                    assert isinstance(report, ValidationErrorReport)
                    assert report.error_counts[ValidationErrorLevel.ERROR] >= 1
                    unexpected_errors += len(report.unexpected_errors)

        assert unexpected_errors == 0

    @pytest.mark.parametrize(
        "test_label",
        [
            "05",
        ],
    )
    def test_fuzzy(self, monkeypatch, layout_label, test_label):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path(f"./input/test_{test_label}"))
        excel_path = f"validation_test_{test_label}_data.xlsx"

        session = Session()
        cache_path = "config"
        session.load_persisted_cache(source=cache_path)
        layout = session.cache.get(layout_label, "DataLayout")
        assert isinstance(layout, peh.DataLayout)
        data_dict = session.load_tabular_data(
            source=excel_path,
            validation_layout=layout,
        )
        assert isinstance(data_dict, dict)
        assert len(data_dict) > 0

        observation_id = "peh:VALIDATION_TEST_SAMPLE_METADATA"

        sheet_label_to_observation_id = {
            "SAMPLE": "peh:VALIDATION_TEST_SAMPLE_SAMPLE",
            "SUBJECTUNIQUE": "peh:VALIDATION_TEST_SAMPLE_SUBJECTUNIQUE",
            "SUBJECTTIMEPOINT": "peh:VALIDATION_TEST_SAMPLE_SUBJECTTIMEPOINT",
            "SAMPLETIMEPOINT_BWB": "peh:VALIDATION_TEST_SAMPLE_SAMPLETIMEPOINT_BWB",
        }
        unexpected_errors = 0
        for sheet_label in sheet_label_to_observation_id.keys():
            data_df = data_dict.get(sheet_label, None)
            if data_df is not None:
                observation_id = sheet_label_to_observation_id[sheet_label]
                observation = session.get_resource(observation_id, "Observation")
                assert isinstance(observation, peh.Observation)
                validation_result = session.validate_tabular_data(data_df, observation_list=[observation])
                assert validation_result is not None
                assert isinstance(validation_result, dict)
                for report in validation_result.values():
                    assert isinstance(report, ValidationErrorReport)
                    assert report.error_counts[ValidationErrorLevel.ERROR] >= 1
                    unexpected_errors += len(report.unexpected_errors)

        assert unexpected_errors == 0
