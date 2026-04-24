import pytest

from peh_model.peh import DataImportConfig, DataImportSectionMapping, DataImportSectionMappingLink, DataLayout

from pypeh import Session
from pypeh.core.models.internal_data_layout import Dataset, DatasetSeries
from pypeh.core.models.settings import LocalFileConfig

from pypeh.core.models.validation_dto import ValidationConfig
from pypeh.core.utils.namespaces import NamespaceManager
from tests.test_utils.dirutils import get_absolute_path
from tests.test_utils.xlsx import write_minimal_xlsx


@pytest.mark.dataframe
class TestSessionValidation:
    @pytest.mark.skip(reason="ObservableProperty info is lacking")
    def test_invalid_file(self, monkeypatch):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path("./input"))
        excel_path = "validation_files/invalid_excel.xlsx"

        session = Session()
        session.load_persisted_cache(source="validation_config")
        data_import_config = session.cache.get("peh:IMPORT_CONFIG_TEST_DATA_LAYOUT", "DataImportConfig")
        assert isinstance(data_import_config, DataImportConfig)
        with pytest.raises(Exception, match="calamine error: Cannot detect file format.*"):
            session.load_tabular_dataset_series(source=excel_path, data_import_config=data_import_config)

    @pytest.mark.skip(reason="ObservableProperty info is lacking")
    def test_valid_file(self, monkeypatch):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path("./input"))
        excel_path = "validation_files/valid_excel_wrong_format.xlsx"

        session = Session()
        session.load_persisted_cache(source="validation_config")
        data_import_config = session.cache.get("peh:IMPORT_CONFIG_TEST_DATA_LAYOUT", "DataImportConfig")
        assert isinstance(data_import_config, DataImportConfig)
        with pytest.raises(Exception, match=r"Sheet name\(s\) Template do not correspond with provided data layout"):
            session.load_tabular_dataset_series(source=excel_path, data_import_config=data_import_config)

    @pytest.mark.parametrize("use_namespace_manager", [True, False])
    def test_load_dataset_series_from_layout(self, use_namespace_manager):
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
        if use_namespace_manager:
            base_uri = "https://example.org/"
            namespace_manager = NamespaceManager(default_base_uri=base_uri)
            session.bind_namespace_manager(namespace_manager=namespace_manager)
        result = session.load_tabular_dataset_series(
            source="validation_test_03_data.test",
            file_format="xlsx",
            data_import_config=data_import_config,
            connection_label="local_file",
        )

        assert isinstance(result, DatasetSeries)
        assert result.described_by == data_import_config.layout
        if use_namespace_manager:
            assert result.identifier.startswith(base_uri)

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

    def test_load_dataset_series_basic(self):
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
        result = session.load_tabular_dataset_series(
            source="validation_test_03_data.xlsx", data_import_config=data_import_config, connection_label="local_file"
        )
        assert isinstance(result, DatasetSeries)
        assert "SAMPLETIMEPOINT_BSS" in result
        dataset = result["SAMPLETIMEPOINT_BSS"]
        assert isinstance(dataset, Dataset)
        assert dataset.data.shape == (1, 4)
        assert "SAMPLE" in result
        dataset = result["SAMPLE"]
        assert isinstance(dataset, Dataset)
        assert dataset.data.shape == (1, 7)

    def test_load_dataset_series_cast_error_policy_raise(self, tmp_path):
        from pypeh.adapters.persistence.dataframe import DataFrameTypeCastError

        source = tmp_path / "typed_mismatch.xlsx"
        write_minimal_xlsx(
            source,
            sheet_name="SAMPLETIMEPOINT_BSS",
            headers=["id_sample", "chol", "chol_loq", "chol_lod"],
            rows=[
                [1, 1.2, 0.1, 0.01],
                [2, "oops", 0.1, 0.01],
            ],
        )

        session = Session(
            connection_config=[
                LocalFileConfig(
                    label="local_file",
                    config_dict={
                        "root_folder": get_absolute_path(
                            "./input/load_data_collection_basic"
                        ),
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
                        section="SAMPLE_METADATA_SECTION_SAMPLETIMEPOINT_BSS",
                        observation_id_list=[
                            "peh:VALIDATION_TEST_SAMPLE_TIMEPOINT"
                        ],
                    ),
                ]
            ),
        )

        with pytest.raises(
            DataFrameTypeCastError,
            match="Failed to cast Excel sheet 'SAMPLETIMEPOINT_BSS'",
        ):
            session.load_tabular_dataset_series(
                source=str(source),
                file_format="xlsx",
                data_import_config=data_import_config,
                connection_label="local_file",
                cast_error_policy="raise",
            )

    @pytest.mark.skip(reason="ObservableProperty info is lacking")
    def test_invalid_sheets(self, monkeypatch):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path("./input"))
        excel_path = "validation_files/valid_excel_wrong_format.xlsx"

        session = Session()
        session.load_persisted_cache(source="validation_config")
        data_import_config = session.cache.get("peh:IMPORT_CONFIG_TEST_DATA_LAYOUT", "DataImportConfig")
        assert isinstance(data_import_config, DataImportConfig)
        # with pytest.raises(Exception, match=r"Sheet name\(s\) Template do not correspond with provided data layout"):
        session.load_tabular_dataset_series(source=excel_path, data_import_config=data_import_config)

    @pytest.mark.skip("ObservableProperty info is lacking")
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
        data = session.load_tabular_dataset_series(
            source="multi_connection_valid_excel.xlsx",
            data_import_config=data_import_config,
            connection_label="local_file_validation_files",
        )
        assert isinstance(data, dict)
        assert len(data) == 1


@pytest.mark.core
class TestBuildConfigs:
    def test_build_validation_config(self):
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
        data_layout_id = "peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA"
        data_layout = session.load_resource(data_layout_id, "DataLayout")
        assert isinstance(data_layout, DataLayout)
        config_dict = session.build_validation_config(
            data_layout=data_layout,
        )
        for config in config_dict.values():
            assert isinstance(config, ValidationConfig)
