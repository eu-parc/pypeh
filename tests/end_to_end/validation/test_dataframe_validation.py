import pytest
import peh_model.peh as peh
import logging

from pypeh.core.models.constants import ValidationErrorLevel
from tests.test_utils.dirutils import get_absolute_path
from typing import cast

from pypeh import Session
from pypeh.core.models.validation_errors import ValidationError, ValidationErrorReport, EntityLocation
from pypeh.core.models.settings import LocalFileConfig

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
            data_layout=layout,
        )
        assert isinstance(data_dict, dict)
        data_df = data_dict["SAMPLE"]
        assert data_df is not None
        layout_section_id = "SAMPLE_METADATA_SECTION_SAMPLE"
        layout_section = session.get_resource(layout_section_id, "DataLayoutSection")
        assert isinstance(layout_section, peh.DataLayoutSection)
        report_to_check = session.validate_tabular_data(data_df, data_layout_section=layout_section)

        assert isinstance(report_to_check, ValidationErrorReport)
        assert report_to_check.total_errors == 1
        assert report_to_check.groups[-1].errors[-1].type == "check_categorical"
        assert len(report_to_check.groups[-1].errors[-1].locations) == 1
        assert isinstance(report_to_check.groups[-1].errors[-1].locations[-1], EntityLocation)
        assert len(report_to_check.groups[-1].errors[-1].locations[-1].identifying_property_values) == 1
        assert isinstance(report_to_check.groups[-1].errors[-1].locations[-1].identifying_property_values[0], tuple)
        assert len(report_to_check.groups[-1].errors[-1].locations[-1].identifying_property_values[0]) == 1
        assert isinstance(report_to_check.groups[-1].errors[-1].locations[-1].identifying_property_values[0][0], int)
        assert report_to_check.groups[-1].errors[-1].locations[-1].identifying_property_values[0][0] == 31


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
            data_layout=layout,
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
            data_layout=layout,
        )
        assert isinstance(data_dict, dict)
        assert len(data_dict) > 0

        data_df = data_dict["SAMPLE"]
        assert data_df is not None
        layout_section_id = "SAMPLE_METADATA_SECTION_SAMPLE"
        layout_section = session.get_resource(layout_section_id, "DataLayoutSection")
        assert isinstance(layout_section, peh.DataLayoutSection)
        validation_report = session.validate_tabular_data(
            data=data_df,
            data_layout_section=layout_section,
        )
        assert validation_report is not None
        assert isinstance(validation_report, ValidationErrorReport)
        assert validation_report.error_counts[ValidationErrorLevel.FATAL] == 0
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
            data_layout=layout,
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
            data_layout=layout,
        )
        assert isinstance(data_dict, dict)
        assert len(data_dict) > 0

        section_label_to_section_id = {
            "SAMPLE": "SAMPLE_METADATA_SECTION_SAMPLE",
            "SAMPLETIMEPOINT_BSS": "SAMPLE_METADATA_SECTION_SAMPLETIMEPOINT_BSS",
        }
        observable_property_id_to_layout_section_label = {"matrix": "SAMPLE"}
        for sheet_label, data_df in data_dict.items():
            section_id = section_label_to_section_id[sheet_label]
            layout_section = session.get_resource(resource_identifier=section_id, resource_type="DataLayoutSection")
            layout_section = cast(peh.DataLayoutSection, layout_section)
            validation_report = session.validate_tabular_data(
                data=data_df,
                data_layout_section=layout_section,
                dependent_data=data_dict,
                observable_property_id_to_layout_section_label=observable_property_id_to_layout_section_label,
            )
            assert isinstance(validation_report, ValidationErrorReport)
            assert validation_report.error_counts[ValidationErrorLevel.FATAL] == 0
            assert validation_report.total_errors == 0

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
            data_layout=layout,
        )
        assert isinstance(data_dict, dict)
        assert len(data_dict) > 0

        section_label_to_section_id = {
            "SAMPLE": "peh:SAMPLE_METADATA_SECTION_SAMPLE",
            "SUBJECTUNIQUE": "peh:SAMPLE_METADATA_SECTION_SUBJECTUNIQUE",
            "SUBJECTTIMEPOINT": "peh:SAMPLE_METADATA_SECTION_SUBJECTTIMEPOINT",
            "SAMPLETIMEPOINT_BWB": "peh:SAMPLE_METADATA_SECTION_SAMPLETIMEPOINT_BWB",
        }
        observable_property_id_to_layout_section_label = {
            "matrix": "SAMPLE",
            "lipidassessment": "SAMPLE",
        }
        unexpected_errors = 0
        for sheet_label in section_label_to_section_id.keys():
            data_df = data_dict.get(sheet_label, None)
            if data_df is not None:
                section_id = section_label_to_section_id[sheet_label]
                layout_section = session.get_resource(resource_identifier=section_id, resource_type="DataLayoutSection")
                assert layout_section is not None
                layout_section = cast(peh.DataLayoutSection, layout_section)
                validation_report = session.validate_tabular_data(
                    data=data_df,
                    data_layout_section=layout_section,
                    dependent_data=data_dict,
                    observable_property_id_to_layout_section_label=observable_property_id_to_layout_section_label,
                )
                assert validation_report is not None
                assert isinstance(validation_report, ValidationErrorReport)
                if sheet_label == "SAMPLETIMEPOINT_BWB":
                    assert validation_report.error_counts[ValidationErrorLevel.ERROR] == 0
                else:
                    assert validation_report.error_counts[ValidationErrorLevel.ERROR] >= 1
                assert validation_report.error_counts[ValidationErrorLevel.FATAL] == 0
                unexpected_errors += len(validation_report.unexpected_errors)

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
            data_layout=layout,
        )
        assert isinstance(data_dict, dict)
        assert len(data_dict) > 0

        section_label_to_section_id = {
            "SAMPLE": "peh:SAMPLE_METADATA_SECTION_SAMPLE",
            "SUBJECTUNIQUE": "peh:SAMPLE_METADATA_SECTION_SUBJECTUNIQUE",
            "SUBJECTTIMEPOINT": "peh:SAMPLE_METADATA_SECTION_SUBJECTTIMEPOINT",
            "SAMPLETIMEPOINT_BWB": "peh:SAMPLE_METADATA_SECTION_SAMPLETIMEPOINT_BWB",
        }
        observable_property_id_to_layout_section_label = {
            "matrix": "SAMPLE",
            "lipidassessment": "SAMPLE",
        }
        unexpected_errors = 0
        for sheet_label in section_label_to_section_id.keys():
            data_df = data_dict.get(sheet_label, None)
            if data_df is not None:
                section_id = section_label_to_section_id[sheet_label]
                layout_section = session.get_resource(resource_identifier=section_id, resource_type="DataLayoutSection")
                assert layout_section is not None
                layout_section = cast(peh.DataLayoutSection, layout_section)
                validation_report = session.validate_tabular_data(
                    data=data_df,
                    data_layout_section=layout_section,
                    dependent_data=data_dict,
                    observable_property_id_to_layout_section_label=observable_property_id_to_layout_section_label,
                )
                assert validation_report is not None
                assert isinstance(validation_report, ValidationErrorReport)
                assert validation_report.error_counts[ValidationErrorLevel.FATAL] == 0
                if sheet_label == "SUBJECTTIMEPOINT":
                    assert validation_report.error_counts[ValidationErrorLevel.ERROR] == 1
                else:
                    assert validation_report.error_counts[ValidationErrorLevel.ERROR] == 0
                unexpected_errors += len(validation_report.unexpected_errors)

        assert unexpected_errors == 0


@pytest.mark.end_to_end
class TestCollectionRoundTrip:
    @pytest.fixture(scope="class")
    def layout_label(self):
        return "peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA"

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
            data_layout=layout,
        )
        assert isinstance(data_dict, dict)
        assert len(data_dict) > 0

        validation_report_collection = session.validate_tabular_data_collection(
            data_collection=data_dict,
            data_layout=layout,
        )
        for validation_report in validation_report_collection.values():
            assert validation_report.error_counts[ValidationErrorLevel.FATAL] == 0
            assert len(validation_report.unexpected_errors) == 0


@pytest.mark.end_to_end
class TestCollectionRoundTripReference:
    @pytest.fixture(scope="class")
    def layout_label(self):
        return "peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA"

    def test_load_at_init(self, layout_label):
        test_label = "05"
        session = Session(
            connection_config=[
                LocalFileConfig(
                    label="local_file",
                    config_dict={
                        "root_folder": get_absolute_path(f"./input/test_{test_label}"),
                    },
                ),
            ],
            default_connection="local_file",
            load_from_default_connection="config",
        )

        excel_path = f"validation_test_{test_label}_data.xlsx"
        validation_report_collection = session.validate_tabular_data_collection_by_reference(
            data_collection_id=excel_path,
            data_layout_id=layout_label,
        )
        for validation_report in validation_report_collection.values():
            assert validation_report.error_counts[ValidationErrorLevel.FATAL] == 0
            assert len(validation_report.unexpected_errors) == 0

    def test_load_by_reference(self, layout_label):
        test_label = "05"
        session = Session(
            connection_config=[
                LocalFileConfig(
                    label="local_file",
                    config_dict={
                        "root_folder": get_absolute_path(f"./input/test_{test_label}"),
                    },
                ),
            ],
        )

        excel_path = f"validation_test_{test_label}_data.xlsx"
        validation_report_collection = session.validate_tabular_data_collection_by_reference(
            data_collection_id=excel_path,
            data_collection_connection_label="local_file",
            data_layout_id=layout_label,
            data_layout_connection_label="local_file",
            data_layout_path="config",
        )
        for validation_report in validation_report_collection.values():
            assert validation_report.error_counts[ValidationErrorLevel.FATAL] == 0
            assert len(validation_report.unexpected_errors) == 0
