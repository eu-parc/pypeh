import pytest
import peh_model.peh as peh
import logging

from pypeh.core.models.constants import ObservablePropertyValueType, ValidationErrorLevel
from tests.test_utils.dirutils import get_absolute_path

from pypeh import Session
from pypeh.core.models.validation_errors import ValidationErrorReport, EntityLocation, ValidationErrorReportCollection
from pypeh.core.models.internal_data_layout import Dataset, DatasetSchema, DatasetSchemaElement, DatasetSeries


logger = logging.getLogger(__name__)


@pytest.mark.end_to_end
class TestDatasetValidation:
    def test_end_to_end_dataframe_validation(self, monkeypatch):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path("./input/test_01"))

        session = Session()
        session.load_persisted_cache(source="config")

        data_import_config = session.cache.get(
            "peh:IMPORT_CONFIG_CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA", "DataImportConfig"
        )
        assert isinstance(data_import_config, peh.DataImportConfig)

        excel_path = "validation_test_01_data.xlsx"
        dataset_series = session.load_tabular_dataset_series(
            source=excel_path,
            data_import_config=data_import_config,
        )
        assert isinstance(dataset_series, DatasetSeries)
        dataset_label = "SAMPLE"
        report_to_check = session.validate_tabular_dataset(
            dataset_series.parts[dataset_label],
            dependent_data=dataset_series,
        )

        assert isinstance(report_to_check, ValidationErrorReport)
        assert report_to_check.total_errors == 1
        assert report_to_check.groups[-1].errors[-1].type == "check categorical"
        errors = report_to_check.groups[-1].errors
        locations = errors[-1].locations
        assert locations is not None
        assert len(locations) == 1
        assert isinstance(locations[-1], EntityLocation)
        identifying_property_values = locations[-1].identifying_property_values
        assert len(identifying_property_values) == 1
        assert isinstance(identifying_property_values[0], tuple)
        assert len(identifying_property_values[0]) == 1
        assert isinstance(identifying_property_values[0][0], int)
        assert identifying_property_values[0][0] == 31


@pytest.mark.end_to_end
class TestRoundTripDataset:
    @pytest.fixture(scope="class")
    def import_config_label(self):
        return "peh:IMPORT_CONFIG_CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA"

    @pytest.mark.parametrize("test_label", ["01", "02", "04", "05", "06"])
    def test_load_data(self, monkeypatch, import_config_label, test_label):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path(f"./input/test_{test_label}"))
        excel_path = f"validation_test_{test_label}_data.xlsx"

        session = Session()
        cache_path = "config"
        session.load_persisted_cache(source=cache_path)
        data_import_config = session.cache.get(import_config_label, "DataImportConfig")
        assert isinstance(data_import_config, peh.DataImportConfig)
        dataset_series = session.load_tabular_dataset_series(
            source=excel_path,
            data_import_config=data_import_config,
        )
        assert isinstance(dataset_series, DatasetSeries)
        assert len(dataset_series) > 0

    @pytest.mark.parametrize("test_label", ["01", "02"])
    def test_basic_roundtrip(self, monkeypatch, import_config_label, test_label):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path(f"./input/test_{test_label}"))
        excel_path = f"validation_test_{test_label}_data.xlsx"

        session = Session()
        cache_path = "config"
        session.load_persisted_cache(source=cache_path)

        data_import_config = session.cache.get(import_config_label, "DataImportConfig")
        assert isinstance(data_import_config, peh.DataImportConfig)
        dataset_series = session.load_tabular_dataset_series(
            source=excel_path,
            data_import_config=data_import_config,
        )
        assert isinstance(dataset_series, DatasetSeries)
        assert len(dataset_series) > 0

        dataset_label = "SAMPLE"
        dataset = dataset_series[dataset_label]
        assert dataset is not None
        validation_report = session.validate_tabular_dataset(
            data=dataset,
            dependent_data=dataset_series,
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
    def test_sheet_name_round_trip(self, monkeypatch, import_config_label, test_label):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path(f"./input/test_{test_label}"))
        excel_path = f"validation_test_{test_label}_data.xlsx"

        session = Session()
        cache_path = "config"
        session.load_persisted_cache(source=cache_path)
        data_import_config = session.cache.get(import_config_label, "DataImportConfig")
        assert isinstance(data_import_config, peh.DataImportConfig)
        with pytest.raises(ValueError, match="no matching sheet found.*"):
            session.load_tabular_dataset_series(source=excel_path, data_import_config=data_import_config)

    @pytest.mark.parametrize(
        "test_label",
        [
            "03",
        ],
    )
    def test_sheet_name_round_trip_continued(self, monkeypatch, import_config_label, test_label):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path(f"./input/test_{test_label}"))
        excel_path = f"validation_test_{test_label}_data.xlsx"

        session = Session()
        cache_path = "config_corrected"
        session.load_persisted_cache(source=cache_path)
        data_import_config = session.cache.get(import_config_label, "DataImportConfig")

        assert isinstance(data_import_config, peh.DataImportConfig)
        dataset_series = session.load_tabular_dataset_series(
            source=excel_path,
            data_import_config=data_import_config,
        )
        assert isinstance(dataset_series, DatasetSeries)
        assert len(dataset_series) > 0

        for dataset_label in dataset_series:
            dataset = dataset_series[dataset_label]
            assert dataset is not None
            validation_report = session.validate_tabular_dataset(
                data=dataset,
                dependent_data=dataset_series,
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
    def test_full(self, monkeypatch, import_config_label, test_label):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path(f"./input/test_{test_label}"))
        excel_path = f"validation_test_{test_label}_data.xlsx"

        session = Session()
        cache_path = "config"
        session.load_persisted_cache(source=cache_path)
        data_import_config = session.cache.get(import_config_label, "DataImportConfig")
        assert isinstance(data_import_config, peh.DataImportConfig)
        dataset_series = session.load_tabular_dataset_series(
            source=excel_path,
            data_import_config=data_import_config,
        )
        assert isinstance(dataset_series, DatasetSeries)
        assert len(dataset_series) > 0

        unexpected_errors = 0
        for dataset_label in dataset_series:
            dataset = dataset_series[dataset_label]
            assert isinstance(dataset, Dataset)
            if dataset.data is None:
                continue
            validation_report = session.validate_tabular_dataset(
                data=dataset,
                dependent_data=dataset_series,
            )
            assert validation_report is not None
            assert isinstance(validation_report, ValidationErrorReport)
            if dataset_label == "SAMPLETIMEPOINT_BWB":
                assert validation_report.error_counts[ValidationErrorLevel.ERROR] == 0
            else:
                assert validation_report.error_counts[ValidationErrorLevel.ERROR] >= 1
            assert validation_report.error_counts[ValidationErrorLevel.FATAL] == 0
            unexpected_errors += len(validation_report.unexpected_errors)

        assert unexpected_errors == 0

        # validate entire dataset_series
        validation_report_collection = session.validate_tabular_dataset_series(
            dataset_series=dataset_series,
        )
        assert isinstance(validation_report_collection, ValidationErrorReportCollection)

    @pytest.mark.parametrize(
        "test_label",
        [
            "05",
        ],
    )
    def test_fuzzy(self, monkeypatch, import_config_label, test_label):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path(f"./input/test_{test_label}"))
        excel_path = f"validation_test_{test_label}_data.xlsx"

        session = Session()
        cache_path = "config"
        session.load_persisted_cache(source=cache_path)
        data_import_config = session.cache.get(import_config_label, "DataImportConfig")
        assert isinstance(data_import_config, peh.DataImportConfig)
        dataset_series = session.load_tabular_dataset_series(
            source=excel_path,
            data_import_config=data_import_config,
        )
        assert isinstance(dataset_series, DatasetSeries)
        assert len(dataset_series) > 0

        unexpected_errors = 0
        for dataset_label in dataset_series:
            dataset = dataset_series[dataset_label]
            assert dataset is not None
            if dataset.data is None:
                continue
            validation_report = session.validate_tabular_dataset(
                data=dataset,
                dependent_data=dataset_series,
            )
            assert validation_report is not None
            assert isinstance(validation_report, ValidationErrorReport)
            assert validation_report.error_counts[ValidationErrorLevel.FATAL] == 0
            if dataset_label == "SUBJECTTIMEPOINT":
                assert validation_report.error_counts[ValidationErrorLevel.ERROR] == 1
            else:
                assert validation_report.error_counts[ValidationErrorLevel.ERROR] == 0
            unexpected_errors += len(validation_report.unexpected_errors)

        assert unexpected_errors == 0

    def test_empty(self):
        session = Session()
        empty_dataset_series = DatasetSeries(
            label="test",
            parts={
                "test": Dataset(
                    label="test",
                    schema=DatasetSchema(
                        elements={
                            "test_element": DatasetSchemaElement(
                                label="test_label",
                                observable_property_id="test_obs_prop",
                                data_type=ObservablePropertyValueType.STRING,
                            )
                        }
                    ),
                )
            },
        )
        with pytest.raises(AssertionError):
            session.validate_tabular_dataset_series(empty_dataset_series)
