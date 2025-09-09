import pytest
import peh_model.peh as peh
import logging

from pypeh.core.models.constants import ValidationErrorLevel
from tests.test_utils.dirutils import get_absolute_path

from pypeh import Session
from pypeh.core.models.settings import LocalFileConfig
from pypeh.core.models.validation_errors import ValidationErrorReport

logger = logging.getLogger(__name__)


@pytest.mark.end_to_end_consistency
class TestConsistency:
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
            default_persisted_cache="local_file_validation_config",
        )
        session.load_persisted_cache()
        layout = session.cache.get("peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA", "DataLayout")
        assert layout.id == "peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA"
        data_dict = session.load_tabular_data(
            source="validation_test_06_data.xlsx",
            connection_label="local_file_validation_files",
            validation_layout=layout,
        )
        assert isinstance(data_dict, dict)
        assert len(data_dict) > 0

        # Configure the combination of data content and layout, specific to the observation dataset
        set_mapping = {
            "SAMPLE": {
                "layout_section_id": "peh:SAMPLE_METADATA_SECTION_SAMPLE",
                "observation_id": "peh:VALIDATION_TEST_SAMPLE_SAMPLE",
                "oep_set_index": 0,
            },
            "SUBJECTUNIQUE": {
                "layout_section_id": "peh:SAMPLE_METADATA_SECTION_SUBJECTUNIQUE",
                "observation_id": "peh:VALIDATION_TEST_SAMPLE_SUBJECTUNIQUE",
                "oep_set_index": 0,
            },
            "SAMPLETIMEPOINT_BWB": {
                "layout_section_id": "peh:SAMPLE_METADATA_SECTION_SAMPLETIMEPOINT_BWB",
                "observation_id": "peh:VALIDATION_TEST_SAMPLE_SAMPLETIMEPOINT_BWB",
                "oep_set_index": 0,
            },
        }

        observation_list = [session.cache.get(m["observation_id"], "Observation") for m in set_mapping.values()]
        dataset_validations_dict = session.get_dataset_validations_dict(
            observation_list=observation_list, layout=layout, set_mapping=set_mapping, data_dict=data_dict
        )

        def validate_set(set_key):
            sheet_label = set_mapping[set_key].get("sheet_label", None)
            observation_id = set_mapping[set_key].get("observation_id", None)
            dataset_validations = dataset_validations_dict.get(set_key, None)

            data_df = data_dict.get(sheet_label, None)
            observation = session.get_resource(observation_id, "Observation")
            assert isinstance(observation, peh.Observation)
            validation_result = session.validate_tabular_data(
                data_df, observation_list=[observation], dataset_validations=dataset_validations
            )
            assert validation_result is not None
            assert isinstance(validation_result, dict)
            assert len(validation_result.values()) == 1
            validation_report = list(validation_result.values())[0]
            assert isinstance(validation_report, ValidationErrorReport)
            assert validation_report.error_counts[ValidationErrorLevel.WARNING] == 0
            return validation_report

        report = validate_set("SAMPLE")
        assert report.error_counts[ValidationErrorLevel.ERROR] == 3
        assert len(report.unexpected_errors) == 0

        report = validate_set("SUBJECTUNIQUE")
        assert report.error_counts[ValidationErrorLevel.ERROR] == 3
        assert len(report.unexpected_errors) == 0

        report = validate_set("SAMPLETIMEPOINT_BWB")
        assert report.error_counts[ValidationErrorLevel.ERROR] == 4
        assert len(report.unexpected_errors) == 0
