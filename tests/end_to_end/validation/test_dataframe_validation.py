import pytest
import peh_model.peh as peh
import logging

from pypeh.core.models.constants import ValidationErrorLevel
from tests.test_utils.dirutils import get_absolute_path
from typing import cast

from pypeh import Session
from pypeh.core.models.validation_errors import ValidationErrorReport, EntityLocation
from pypeh.core.models.internal_data_layout import Dataset, DatasetSeries, get_observations_from_data_import_config
from pypeh.core.models.settings import LocalFileConfig

logger = logging.getLogger(__name__)


@pytest.mark.end_to_end
class TestSessionDefaultLocalFile:
    def test_end_to_end_dataframe_validation(self, monkeypatch):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path("./input/test_01/config"))

        session = Session()
        session.load_persisted_cache()

        observation_id = "peh:VALIDATION_TEST_SAMPLE_METADATA"
        observation = session.get_resource(observation_id, "Observation")
        assert isinstance(observation, peh.Observation)

        data_import_config = session.cache.get(
            "peh:IMPORT_CONFIG_CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA", "DataImportConfig"
        )
        assert isinstance(data_import_config, peh.DataImportConfig)

        excel_path = get_absolute_path("./input/test_01/validation_test_01_data.xlsx")
        data_dict = session.load_tabular_data_collection(
            source=excel_path,
            data_import_config=data_import_config,
        )
        assert isinstance(data_dict, dict)
        data_df = data_dict[observation_id].observed_data
        assert data_df is not None
        report_to_check = session.validate_tabular_data(data_df, observation=observation)

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
        data_dict = session.load_tabular_data_collection(
            source=excel_path,
            data_import_config=data_import_config,
        )
        assert isinstance(data_dict, dict)
        assert len(data_dict) > 0

    @pytest.mark.parametrize("test_label", ["01", "02"])
    def test_basic_roundtrip(self, monkeypatch, import_config_label, test_label):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path(f"./input/test_{test_label}"))
        excel_path = f"validation_test_{test_label}_data.xlsx"

        session = Session()
        cache_path = "config"
        session.load_persisted_cache(source=cache_path)

        observation_id = "peh:VALIDATION_TEST_SAMPLE_METADATA"
        observation = session.get_resource(observation_id, "Observation")
        assert isinstance(observation, peh.Observation)

        data_import_config = session.cache.get(import_config_label, "DataImportConfig")
        assert isinstance(data_import_config, peh.DataImportConfig)
        data_dict = session.load_tabular_data_collection(
            source=excel_path,
            data_import_config=data_import_config,
        )
        assert isinstance(data_dict, dict)
        assert len(data_dict) > 0

        data_df = data_dict[observation_id].observed_data
        assert data_df is not None
        validation_report = session.validate_tabular_data(
            data=data_df,
            observation=observation,
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
            session.load_tabular_data_collection(source=excel_path, data_import_config=data_import_config)

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
        data_dict = session.load_tabular_data_collection(
            source=excel_path,
            data_import_config=data_import_config,
        )
        assert isinstance(data_dict, dict)
        assert len(data_dict) > 0

        for observation_id, data_result in data_dict.items():
            observation = session.get_resource(resource_identifier=observation_id, resource_type="Observation")
            observation = cast(peh.Observation, observation)
            assert isinstance(observation, peh.Observation)
            validation_report = session.validate_tabular_data(
                data=data_result.observed_data,
                observation=observation,
                dependent_data=data_dict,
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
        data_dict = session.load_tabular_data_collection(
            source=excel_path,
            data_import_config=data_import_config,
        )
        assert isinstance(data_dict, dict)
        assert len(data_dict) > 0
        unexpected_errors = 0
        for observation_id, data_result in data_dict.items():
            data_df = data_result.observed_data
            if data_df is not None:
                observation = session.get_resource(resource_identifier=observation_id, resource_type="Observation")
                assert observation is not None
                observation = cast(peh.Observation, observation)
                validation_report = session.validate_tabular_data(
                    data=data_df,
                    observation=observation,
                    dependent_data=data_dict,
                )
                assert validation_report is not None
                assert isinstance(validation_report, ValidationErrorReport)
                if observation_id == "peh:VALIDATION_TEST_SAMPLE_SAMPLETIMEPOINT_BWB":
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
    def test_fuzzy(self, monkeypatch, import_config_label, test_label):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path(f"./input/test_{test_label}"))
        excel_path = f"validation_test_{test_label}_data.xlsx"

        session = Session()
        cache_path = "config"
        session.load_persisted_cache(source=cache_path)
        data_import_config = session.cache.get(import_config_label, "DataImportConfig")
        assert isinstance(data_import_config, peh.DataImportConfig)
        data_dict = session.load_tabular_data_collection(
            source=excel_path,
            data_import_config=data_import_config,
        )
        assert isinstance(data_dict, dict)
        assert len(data_dict) > 0

        unexpected_errors = 0
        for observation_id, data_result in data_dict.items():
            data_df = data_result.observed_data
            assert data_df is not None
            observation = session.get_resource(resource_identifier=observation_id, resource_type="Observation")
            assert observation is not None
            observation = cast(peh.Observation, observation)
            validation_report = session.validate_tabular_data(
                data=data_df,
                observation=observation,
                dependent_data=data_dict,
            )
            assert validation_report is not None
            assert isinstance(validation_report, ValidationErrorReport)
            assert validation_report.error_counts[ValidationErrorLevel.FATAL] == 0
            if observation_id == "peh:VALIDATION_TEST_SAMPLE_SUBJECTTIMEPOINT":
                assert validation_report.error_counts[ValidationErrorLevel.ERROR] == 1
            else:
                assert validation_report.error_counts[ValidationErrorLevel.ERROR] == 0
            unexpected_errors += len(validation_report.unexpected_errors)

        assert unexpected_errors == 0


@pytest.mark.end_to_end
class TestCollectionRoundTrip:
    @pytest.fixture(scope="class")
    def import_config_label(self):
        return "peh:IMPORT_CONFIG_CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA"

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
        data_dict = session.load_tabular_data_collection(
            source=excel_path,
            data_import_config=data_import_config,
        )
        assert isinstance(data_dict, dict)
        assert len(data_dict) > 0

        observations = get_observations_from_data_import_config(data_import_config, session.cache)
        validation_report_collection = session.validate_tabular_data_collection(
            data_collection=data_dict,
            observations=observations,
        )
        for validation_report in validation_report_collection.values():
            assert validation_report.error_counts[ValidationErrorLevel.FATAL] == 0
            assert len(validation_report.unexpected_errors) == 0


@pytest.mark.end_to_end
class TestCollectionRoundTripReference:
    @pytest.fixture(scope="class")
    def import_config_label(self):
        return "peh:IMPORT_CONFIG_CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA"

    def test_load_at_init(self, import_config_label):
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
            data_import_config_id=import_config_label,
        )
        for validation_report in validation_report_collection.values():
            assert validation_report.error_counts[ValidationErrorLevel.FATAL] == 0
            assert len(validation_report.unexpected_errors) == 0

    def test_load_by_reference(self, import_config_label):
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
            data_import_config_id=import_config_label,
            data_import_config_connection_label="local_file",
            data_import_config_path="config",
        )
        for validation_report in validation_report_collection.values():
            assert validation_report.error_counts[ValidationErrorLevel.FATAL] == 0
            assert len(validation_report.unexpected_errors) == 0


@pytest.mark.end_to_end
class TestDatasetValidation:
    def test_end_to_end_dataframe_validation(self, monkeypatch):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path("./input/test_01/config"))

        session = Session()
        session.load_persisted_cache()

        data_import_config = session.cache.get(
            "peh:IMPORT_CONFIG_CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA", "DataImportConfig"
        )
        assert isinstance(data_import_config, peh.DataImportConfig)

        excel_path = get_absolute_path("./input/test_01/validation_test_01_data.xlsx")
        dataset_series = session._load_tabular_dataset_series(
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
        assert report_to_check.groups[-1].errors[-1].type == "check_categorical"
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
        dataset_series = session._load_tabular_dataset_series(
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
        dataset_series = session._load_tabular_dataset_series(
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
            session._load_tabular_dataset_series(source=excel_path, data_import_config=data_import_config)

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
        dataset_series = session._load_tabular_dataset_series(
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
        dataset_series = session._load_tabular_dataset_series(
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
        dataset_series = session._load_tabular_dataset_series(
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
