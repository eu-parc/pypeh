import pytest
import peh_model.peh as peh
import logging

from tests.test_utils.dirutils import get_absolute_path

from pypeh import Session
from pypeh.core.models.settings import LocalFileConfig
from pypeh.core.models.internal_data_layout import DatasetSeries
from pypeh.core.models.validation_errors import ValidationErrorReport, ValidationErrorLevel

logger = logging.getLogger(__name__)


@pytest.mark.end_to_end_consistency
class TestDatasetConsistency:
    def test_entity_consistency(self, monkeypatch):
        session = Session(
            connection_config=[
                LocalFileConfig(
                    label="local_file_validation_config",
                    config_dict={
                        "root_folder": get_absolute_path("./input/test_06/config"),
                    },
                ),
                LocalFileConfig(
                    label="local_file_validation_files",
                    config_dict={
                        "root_folder": get_absolute_path("./input/test_06"),
                    },
                ),
            ],
            default_connection="local_file_validation_config",
        )
        session.load_persisted_cache()
        data_import_config = session.cache.get(
            "peh:IMPORT_CONFIG_CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA", "DataImportConfig"
        )
        assert data_import_config.id == "peh:IMPORT_CONFIG_CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA"
        assert isinstance(data_import_config, peh.DataImportConfig)
        data_layout = session.cache.get(data_import_config.layout, "DataLayout")
        assert data_layout.id == data_import_config.layout
        assert isinstance(data_layout, peh.DataLayout)
        dataset_series = session._load_tabular_dataset_series(
            source="validation_test_06_data.xlsx",
            connection_label="local_file_validation_files",
            data_import_config=data_import_config,
        )
        assert isinstance(dataset_series, DatasetSeries)
        assert len(dataset_series) > 0

        validation_report_collection = session.validate_tabular_dataset_series(
            dataset_series=dataset_series,
        )

        assert isinstance(validation_report_collection, dict)
        assert len(validation_report_collection) == 3
        assert isinstance(validation_report_collection["SAMPLE"], ValidationErrorReport)

        sample_errors = validation_report_collection["SAMPLE"]
        assert sample_errors.total_errors == 2
        assert sample_errors.error_counts[ValidationErrorLevel.WARNING] == 0
        assert sample_errors.error_counts[ValidationErrorLevel.ERROR] == 2
        assert len(sample_errors.unexpected_errors) == 0

        subject_errors = validation_report_collection["SUBJECTUNIQUE"]
        assert subject_errors.total_errors == 0
        assert subject_errors.error_counts[ValidationErrorLevel.WARNING] == 0
        assert subject_errors.error_counts[ValidationErrorLevel.ERROR] == 0
        assert len(subject_errors.unexpected_errors) == 0

        labresult_errors = validation_report_collection["SAMPLETIMEPOINT_BWB"]
        assert labresult_errors.total_errors == 1
        assert labresult_errors.error_counts[ValidationErrorLevel.WARNING] == 0
        assert labresult_errors.error_counts[ValidationErrorLevel.ERROR] == 1
        assert len(labresult_errors.unexpected_errors) == 0
