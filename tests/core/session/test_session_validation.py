import pytest
import pathlib

from peh_model.peh import DataImportConfig, DataImportSectionMapping, DataImportSectionMappingLink

from pypeh import Session
from pypeh.core.models.internal_data_layout import Dataset, DatasetSeries, ObservationResultProxy
from pypeh.core.models.settings import LocalFileConfig

from tests.test_utils.dirutils import get_absolute_path


@pytest.mark.dataframe
class TestSessionValidation:
    def test_invalid_file(self, monkeypatch):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path("./input/validation_config"))
        excel_path = get_absolute_path("./input/validation_files/invalid_excel.xlsx")
        assert pathlib.Path(excel_path).is_file()

        session = Session()
        session.load_persisted_cache()
        data_import_config = session.cache.get("peh:IMPORT_CONFIG_TEST_DATA_LAYOUT", "DataImportConfig")
        assert isinstance(data_import_config, DataImportConfig)
        with pytest.raises(Exception, match="calamine error: Cannot detect file format.*"):
            session.load_tabular_data_collection(source=excel_path, data_import_config=data_import_config)

    def test_valid_file(self, monkeypatch):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path("./input/validation_config"))
        excel_path = get_absolute_path("./input/validation_files/valid_excel_wrong_format.xlsx")

        session = Session()
        session.load_persisted_cache()
        data_import_config = session.cache.get("peh:IMPORT_CONFIG_TEST_DATA_LAYOUT", "DataImportConfig")
        assert isinstance(data_import_config, DataImportConfig)
        with pytest.raises(Exception, match=r"Sheet name\(s\) Template do not correspond with provided data layout"):
            session.load_tabular_data_collection(source=excel_path, data_import_config=data_import_config)

    def test_load_data_collection_from_layout(self):
        from polars import DataFrame

        session = Session(
            connection_config=[
                LocalFileConfig(
                    label="local_file",
                    config_dict={
                        "root_folder": get_absolute_path("./input/load_data_collection_basic"),
                    },
                ),
            ],
            default_connection="local_file",
            load_from_default_connection="",
        )
        data_import_config = DataImportConfig(
            id="peh:IMPORT_CONFIG_CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA",
            layout="peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA",
            section_mapping=DataImportSectionMapping(
                section_mapping_links=[
                    DataImportSectionMappingLink(
                        section="SAMPLE_METADATA_SECTION_SAMPLE",
                        observation_id_list=["peh:VALIDATION_TEST_SAMPLE_METADATA"],
                    ),
                    DataImportSectionMappingLink(
                        section="SAMPLE_METADATA_SECTION_SAMPLETIMEPOINT_BSS",
                        observation_id_list=["peh:VALIDATION_TEST_SAMPLE_TIMEPOINT"],
                    ),
                ]
            ),
        )
        result = session._load_tabular_dataset_series(
            source="validation_test_03_data.xlsx", data_import_config=data_import_config, connection_label="local_file"
        )

        assert isinstance(result, DatasetSeries)
        assert result.described_by == data_import_config.layout

        section_id = "SAMPLE_METADATA_SECTION_SAMPLE"
        section = session.cache.get(section_id, "DataLayoutSection")
        section_label = section.ui_label
        assert section_label in result.parts
        dataset = result.parts[section_label]
        assert isinstance(dataset, Dataset)
        assert dataset.described_by == section_id
        assert isinstance(dataset.data, DataFrame)
        assert dataset.data.shape == (1, 7)

        section_id = "SAMPLE_METADATA_SECTION_SAMPLETIMEPOINT_BSS"
        section = session.cache.get(section_id, "DataLayoutSection")
        section_label = section.ui_label
        assert section_label in result.parts
        dataset = result.parts[section_label]
        assert isinstance(dataset, Dataset)
        assert dataset.described_by == section_id
        assert isinstance(dataset.data, DataFrame)
        assert dataset.data.shape == (1, 4)

    def test_load_data_collection_basic(self):
        session = Session(
            connection_config=[
                LocalFileConfig(
                    label="local_file",
                    config_dict={
                        "root_folder": get_absolute_path("./input/load_data_collection_basic"),
                    },
                ),
            ],
            default_connection="local_file",
            load_from_default_connection="",
        )
        data_import_config = DataImportConfig(
            id="peh:IMPORT_CONFIG_CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA",
            layout="peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA",
            section_mapping=DataImportSectionMapping(
                section_mapping_links=[
                    DataImportSectionMappingLink(
                        section="SAMPLE_METADATA_SECTION_SAMPLE",
                        observation_id_list=["peh:VALIDATION_TEST_SAMPLE_METADATA"],
                    ),
                    DataImportSectionMappingLink(
                        section="SAMPLE_METADATA_SECTION_SAMPLETIMEPOINT_BSS",
                        observation_id_list=["peh:VALIDATION_TEST_SAMPLE_TIMEPOINT"],
                    ),
                ]
            ),
        )
        result = session.load_tabular_data_collection(
            source="validation_test_03_data.xlsx", data_import_config=data_import_config, connection_label="local_file"
        )
        assert isinstance(result, dict)
        assert "peh:VALIDATION_TEST_SAMPLE_METADATA" in result
        observation_result = result["peh:VALIDATION_TEST_SAMPLE_METADATA"]
        assert isinstance(observation_result, ObservationResultProxy)
        assert observation_result.observed_data.shape == (1, 7)
        assert "peh:VALIDATION_TEST_SAMPLE_TIMEPOINT" in result
        observation_result = result["peh:VALIDATION_TEST_SAMPLE_TIMEPOINT"]
        assert isinstance(observation_result, ObservationResultProxy)
        assert observation_result.observed_data.shape == (1, 4)

    def test_invalid_sheets(self, monkeypatch):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path("./input/validation_config"))
        excel_path = get_absolute_path("./input/validation_files/valid_excel_wrong_format.xlsx")

        session = Session()
        session.load_persisted_cache()
        data_import_config = session.cache.get("peh:IMPORT_CONFIG_TEST_DATA_LAYOUT", "DataImportConfig")
        assert isinstance(data_import_config, DataImportConfig)
        with pytest.raises(Exception, match=r"Sheet name\(s\) Template do not correspond with provided data layout"):
            session.load_tabular_data_collection(source=excel_path, data_import_config=data_import_config)

    def test_multiple_connections(self):
        session = Session(
            connection_config=[
                LocalFileConfig(
                    label="local_file_validation_config",
                    config_dict={
                        "root_folder": get_absolute_path("./input/default_localfile_data"),
                    },
                ),
                LocalFileConfig(
                    label="local_file_validation_files",
                    config_dict={
                        "root_folder": get_absolute_path("./input/validation_files"),
                    },
                ),
            ],
            default_connection="local_file_validation_config",
        )
        session.load_persisted_cache()
        observation = session.cache.get("peh:OBSERVATION_ADULTS_ANALYTICALINFO", "Observation")
        assert observation.id == "peh:OBSERVATION_ADULTS_ANALYTICALINFO"
        data_import_config = session.cache.get("peh:IMPORT_CONFIG_TEST_DATA_LAYOUT", "DataImportConfig")
        assert isinstance(data_import_config, DataImportConfig)
        data = session.load_tabular_data_collection(
            source="multi_connection_valid_excel.xlsx",
            data_import_config=data_import_config,
            connection_label="local_file_validation_files",
        )
        assert isinstance(data, dict)
        assert len(data) == 1
