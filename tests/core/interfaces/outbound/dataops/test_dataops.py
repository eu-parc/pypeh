import pytest
import abc
import yaml

from typing import Protocol, Any, Generic
from peh_model.peh import (
    DataImportConfig,
    DataImportSectionMapping,
    DataImportSectionMappingLink,
    DataLayout,
    Observation,
)

from pypeh.core.cache.containers import CacheContainer, CacheContainerFactory, CacheContainerView
from pypeh.core.cache.utils import load_entities_from_tree
from pypeh.core.interfaces.outbound.dataops import T_DataType, ValidationInterface, DataEnrichmentInterface
from pypeh.core.models.internal_data_layout import (
    InternalDataLayout,
    ObservationResultProxy,
)
from pypeh.core.models.validation_errors import ValidationErrorReport
from pypeh.core.models.constants import ValidationErrorLevel
from pypeh.core.models.validation_dto import (
    ValidationExpression,
    ValidationDesign,
    ColumnValidation,
    ValidationConfig,
)
from pypeh.core.models.graph import Graph
from pypeh.core.models.settings import LocalFileSettings
from pypeh.adapters.outbound.persistence.hosts import DirectoryIO
from tests.test_utils.dirutils import get_absolute_path


class DataOpsProtocol(Protocol, Generic[T_DataType]):
    data_format: T_DataType

    def _validate(self, data, config) -> ValidationErrorReport: ...

    def validate(self, data, config) -> ValidationErrorReport: ...

    def import_data(self, source, config) -> Any: ...

    def import_data_layout(self, source, config) -> Any: ...

    def _data_layout_to_observation_results(
        self, raw_data, data_import_config, cache_view, internal_data_layout
    ) -> dict[str, ObservationResultProxy]: ...


class TestValidation(abc.ABC):
    """Abstract base class for testing dataops adapters."""

    @abc.abstractmethod
    def get_adapter(self) -> DataOpsProtocol:
        """Return the adapter implementation to test."""
        raise NotImplementedError

    def test_getting_default_adapter_from_interface(self):
        adapter_class = ValidationInterface.get_default_adapter_class()
        adapter = adapter_class()
        assert isinstance(adapter, ValidationInterface)
        assert isinstance(adapter, type(self.get_adapter()))

    @pytest.mark.parametrize(
        "config, data, expected_output",
        [
            # Simple validation using integers
            (
                ValidationConfig(
                    name="simple_validation_integer",
                    columns=[
                        ColumnValidation(
                            unique_name="col1",
                            data_type="integer",
                            required=True,
                            nullable=False,
                            validations=[
                                ValidationDesign(
                                    name="is_greater_than_other_column",
                                    error_level=ValidationErrorLevel.ERROR,
                                    expression=ValidationExpression(
                                        command="is_greater_than",
                                        arg_columns=["col2"],
                                    ),
                                ),
                                ValidationDesign(
                                    name="is_greater_than_number",
                                    error_level=ValidationErrorLevel.WARNING,
                                    expression=ValidationExpression(
                                        command="is_greater_than",
                                        arg_values=[2],
                                    ),
                                ),
                            ],
                        )
                    ],
                    identifying_column_names=["col1"],
                    validations=[],
                ),
                {
                    "col1": [3, 1],
                    "col2": [1, 2],
                },
                {
                    "name": "simple_validation_integer",
                    "total_errors": 2,
                    "errors_counts": {
                        ValidationErrorLevel.INFO: 0,
                        ValidationErrorLevel.WARNING: 1,
                        ValidationErrorLevel.ERROR: 1,
                        ValidationErrorLevel.FATAL: 0,
                    },
                },
            ),
            # Simple validation using integers at df level
            (
                ValidationConfig(
                    name="simple_validation_integer_df_level",
                    columns=[
                        ColumnValidation(
                            unique_name="col1",
                            data_type="integer",
                            required=True,
                            nullable=False,
                            validations=[],
                        )
                    ],
                    identifying_column_names=["col1"],
                    validations=[
                        ValidationDesign(
                            name="name",
                            error_level=ValidationErrorLevel.ERROR,
                            expression=ValidationExpression(
                                command="is_greater_than",
                                arg_columns=["col2"],
                                subject=["col1"],
                            ),
                        )
                    ],
                ),
                {
                    "col1": [3, 1],
                    "col2": [1, 2],
                },
                {
                    "name": "simple_validation_integer_df_level",
                    "total_errors": 1,
                    "errors_counts": {
                        ValidationErrorLevel.INFO: 0,
                        ValidationErrorLevel.WARNING: 0,
                        ValidationErrorLevel.ERROR: 1,
                        ValidationErrorLevel.FATAL: 0,
                    },
                },
            ),
            # disjunction validation using integers
            (
                ValidationConfig(
                    name="disjunction_validation",
                    columns=[
                        ColumnValidation(
                            unique_name="col1",
                            data_type="integer",
                            required=True,
                            nullable=False,
                            validations=[
                                ValidationDesign(
                                    name="name",
                                    error_level=ValidationErrorLevel.ERROR,
                                    expression=ValidationExpression(
                                        command="disjunction",
                                        arg_expressions=[
                                            ValidationExpression(
                                                command="is_greater_than",
                                                arg_columns=["col2"],
                                            ),
                                            ValidationExpression(
                                                command="is_less_than",
                                                subject=["col2"],
                                                arg_values=[0],
                                            ),
                                        ],
                                    ),
                                )
                            ],
                        )
                    ],
                    identifying_column_names=["col1"],
                    validations=[],
                ),
                {
                    "col1": [3, 1],
                    "col2": [1, 2],
                },
                {
                    "name": "disjunction_validation",
                    "total_errors": 1,
                    "errors_counts": {
                        ValidationErrorLevel.INFO: 0,
                        ValidationErrorLevel.WARNING: 0,
                        ValidationErrorLevel.ERROR: 1,
                        ValidationErrorLevel.FATAL: 0,
                    },
                },
            ),
            # Conjunction validation using integers
            (
                ValidationConfig(
                    name="conjunction_validation",
                    columns=[
                        ColumnValidation(
                            unique_name="col1",
                            data_type="integer",
                            required=True,
                            nullable=False,
                            validations=[
                                ValidationDesign(
                                    name="name",
                                    error_level=ValidationErrorLevel.WARNING,
                                    expression=ValidationExpression(
                                        command="conjunction",
                                        arg_expressions=[
                                            ValidationExpression(
                                                command="is_greater_than",
                                                arg_columns=["col2"],
                                            ),
                                            ValidationExpression(
                                                command="is_less_than",
                                                subject=["col2"],
                                                arg_values=[1],
                                            ),
                                        ],
                                    ),
                                )
                            ],
                        )
                    ],
                    identifying_column_names=["col1"],
                    validations=[],
                ),
                {
                    "col1": [3, 0],
                    "col2": [1, -1],
                },
                {
                    "name": "conjunction_validation",
                    "total_errors": 1,
                    "errors_counts": {
                        ValidationErrorLevel.INFO: 0,
                        ValidationErrorLevel.WARNING: 1,
                        ValidationErrorLevel.ERROR: 0,
                        ValidationErrorLevel.FATAL: 0,
                    },
                },
            ),
            # Simple validation using strings
            (
                ValidationConfig(
                    name="simple_validation_strings",
                    columns=[
                        ColumnValidation(
                            unique_name="col1",
                            data_type="string",
                            required=True,
                            nullable=False,
                            validations=[
                                ValidationDesign(
                                    name="name",
                                    error_level=ValidationErrorLevel.ERROR,
                                    expression=ValidationExpression(
                                        command="is_in",
                                        arg_values=["value1", "value2"],
                                    ),
                                )
                            ],
                        ),
                        ColumnValidation(
                            unique_name="col2",
                            data_type="integer",
                            required=True,
                            nullable=False,
                            validations=[],
                        ),
                    ],
                    identifying_column_names=["col1", "col2"],
                    validations=[],
                ),
                {
                    "col1": ["value1", "value2", "value3"],
                    "col2": [1, -1, None],
                },
                {
                    "name": "simple_validation_strings",
                    "total_errors": 2,
                    "errors_counts": {
                        ValidationErrorLevel.INFO: 0,
                        ValidationErrorLevel.WARNING: 0,
                        ValidationErrorLevel.ERROR: 2,
                        ValidationErrorLevel.FATAL: 0,
                    },
                },
            ),
            # Duplicated ID
            (
                ValidationConfig(
                    name="duplicate_id_validation",
                    columns=[
                        ColumnValidation(
                            unique_name="col1",
                            data_type="string",
                            required=True,
                            nullable=False,
                            validations=[],
                        ),
                        ColumnValidation(
                            unique_name="col2",
                            data_type="integer",
                            required=True,
                            nullable=False,
                            validations=[],
                        ),
                    ],
                    identifying_column_names=["col1", "col2"],
                    validations=[],
                ),
                {
                    "col1": ["value1", "value2", "value1"],
                    "col2": [1, -1, 1],
                },
                {
                    "name": "duplicate_id_validation",
                    "total_errors": 1,
                    "errors_counts": {
                        ValidationErrorLevel.INFO: 0,
                        ValidationErrorLevel.WARNING: 0,
                        ValidationErrorLevel.ERROR: 1,
                        ValidationErrorLevel.FATAL: 0,
                    },
                },
            ),
            # function implementation test
            (
                ValidationConfig(
                    name="function implementation test",
                    columns=[
                        ColumnValidation(
                            unique_name="col1",
                            data_type="float",
                            required=True,
                            nullable=False,
                            # decimals_precision
                            validations=[
                                ValidationDesign(
                                    name="fn",
                                    error_level=ValidationErrorLevel.ERROR,
                                    expression=ValidationExpression(
                                        command="decimals_precision",
                                        arg_values=[3],
                                    ),
                                )
                            ],
                        ),
                        ColumnValidation(
                            unique_name="col2",
                            data_type="integer",
                            required=True,
                            nullable=False,
                            validations=[],
                        ),
                    ],
                    identifying_column_names=["col2"],
                    validations=[],
                ),
                {
                    "col1": [1.234, 1.0, 1.123456],
                    "col2": [1, 2, 3],
                },
                {
                    "name": "function implementation test",
                    "total_errors": 1,
                    "errors_counts": {
                        ValidationErrorLevel.INFO: 0,
                        ValidationErrorLevel.WARNING: 0,
                        ValidationErrorLevel.ERROR: 1,
                        ValidationErrorLevel.FATAL: 0,
                    },
                },
            ),
            # conditional
            (
                ValidationConfig(
                    name="conditional test",
                    columns=[
                        ColumnValidation(
                            unique_name="col1",
                            data_type="integer",
                            required=True,
                            nullable=False,
                            validations=[
                                ValidationDesign(
                                    name="conditional",
                                    error_level=ValidationErrorLevel.ERROR,
                                    expression=ValidationExpression(
                                        conditional_expression=ValidationExpression(
                                            command="is_greater_than",
                                            arg_columns=["col2"],
                                        ),
                                        command="is_equal_to",
                                        arg_values=[5],
                                    ),
                                )
                            ],
                        ),
                        ColumnValidation(
                            unique_name="col2",
                            data_type="integer",
                            required=True,
                            nullable=False,
                            validations=[],
                        ),
                    ],
                    identifying_column_names=["col2"],
                    validations=[],
                ),
                {
                    "col1": [20, 1, 5],
                    "col2": [15, 20, 3],
                },
                {
                    "name": "conditional test",
                    "total_errors": 1,
                    "errors_counts": {
                        ValidationErrorLevel.INFO: 0,
                        ValidationErrorLevel.WARNING: 0,
                        ValidationErrorLevel.ERROR: 1,
                        ValidationErrorLevel.FATAL: 0,
                    },
                },
            ),
        ],
    )
    def test_validate(self, config, data, expected_output):
        adapter = self.get_adapter()
        result = adapter._validate(data, config)

        assert result is not None
        assert result.groups[0].name == expected_output.get("name")
        assert result.total_errors == expected_output.get("total_errors")
        assert result.error_counts == expected_output.get("errors_counts")


class TestDataImport(abc.ABC):
    """Abstract base class for testing dataops adapters."""

    @abc.abstractmethod
    def get_adapter(self) -> DataOpsProtocol:
        """Return the adapter implementation to test."""
        raise NotImplementedError

    def test_import_data_layout(self):
        adapter = self.get_adapter()
        source = "./input/datalayout.yaml"
        path = get_absolute_path(source)
        config = LocalFileSettings()
        data = adapter.import_data_layout(path, config)
        if isinstance(data, list):
            assert all(isinstance(dl, DataLayout) for dl in data)
        else:
            assert isinstance(data, DataLayout)

    def test_import_csv(self):
        adapter = self.get_adapter()
        source = "./input/data.csv"
        path = get_absolute_path(source)
        config = LocalFileSettings()
        data = adapter.import_data(path, config)
        assert isinstance(data, adapter.data_format)

    def test_import_excel(self):
        adapter = self.get_adapter()
        source = "./input/data.xlsx"
        path = get_absolute_path(source)
        config = LocalFileSettings()
        data = adapter.import_data(path, config)
        assert all(isinstance(d, adapter.data_format) for d in data.values())

    @pytest.fixture(scope="function")
    def data_layout_container(self):
        source = get_absolute_path("./input")
        container = CacheContainerFactory.new()
        host = DirectoryIO()
        roots = host.load(source, format="yaml")
        for root in roots:
            for entity in load_entities_from_tree(root):
                container.add(entity)
        return container

    def test_data_layout_to_observation_results(self, data_layout_container, raw_data):
        data_import_config = DataImportConfig(
            id="peh:IMPORT_CONFIG_PARC_ALIGNED_STUDIES_LAYOUT_ADULTS",
            layout="peh:PARC_ALIGNED_STUDIES_LAYOUT_ADULTS",
            section_mapping=DataImportSectionMapping(
                section_mapping_links=[
                    DataImportSectionMappingLink(
                        section="peh:PARC_ALIGNED_STUDIES_LAYOUT_ADULTS_SECTION_urine_lab",
                        observation_id_list=["peh:SAMPLE_DATA"],
                    ),
                    DataImportSectionMappingLink(
                        section="peh:PARC_ALIGNED_STUDIES_LAYOUT_ADULTS_SECTION_analyticalinfo",
                        observation_id_list=["peh:SAMPLE_METADATA"],
                    ),
                ],
            ),
        )
        cache_view = CacheContainerView(container=data_layout_container)
        data_layout = cache_view.get("peh:PARC_ALIGNED_STUDIES_LAYOUT_ADULTS", "DataLayout")
        assert isinstance(data_layout, DataLayout)
        internal_data_layout = InternalDataLayout.from_peh(data_layout=data_layout)
        adapter = self.get_adapter()
        ret = adapter._data_layout_to_observation_results(
            raw_data=raw_data,
            data_import_config=data_import_config,
            cache_view=cache_view,
            internal_data_layout=internal_data_layout,
        )

        assert isinstance(ret, dict)
        assert len(ret) == 2
        observation_result = ret["peh:SAMPLE_DATA"]
        assert isinstance(observation_result, ObservationResultProxy)
        assert observation_result.observed_data.shape == (2, 3)

        observation_result = ret["peh:SAMPLE_METADATA"]
        assert isinstance(observation_result, ObservationResultProxy)
        assert observation_result.observed_data.shape == (2, 4)


@pytest.mark.dataframe
class TestDataFrameDataOps(TestValidation, TestDataImport):
    def get_adapter(self) -> DataOpsProtocol:
        try:
            from pypeh.adapters.outbound.validation.pandera_adapter import dataops as dfops

            return dfops.DataFrameAdapter()  # type: ignore
        except ImportError:
            pytest.skip("Necessary modules not installed")

    @pytest.fixture(scope="function")
    def raw_data(self):
        import polars as pl

        layout = {
            "urine_lab": pl.DataFrame(
                schema={
                    "id_subject": pl.String,
                    "matrix": pl.String,
                    "crt": pl.Float64,
                    "crt_lod": pl.Float64,
                    "crt_loq": pl.Float64,
                    "sg": pl.Float64,
                }
            ),
            "analyticalinfo": pl.DataFrame(
                schema={
                    "id_subject": pl.String,
                    "biomarkercode": pl.String,
                    "matrix": pl.String,
                    "labinstitution": pl.String,
                }
            ),
        }

        layout["urine_lab"] = pl.DataFrame(
            [
                {"id_subject": "001", "matrix": "urine", "crt": 1.2, "crt_lod": 0.1, "crt_loq": 0.2, "sg": 1.015},
                {"id_subject": "002", "matrix": "urine", "crt": 1.5, "crt_lod": 0.1, "crt_loq": 0.2, "sg": 1.020},
            ]
        )

        layout["analyticalinfo"] = pl.DataFrame(
            [
                {"id_subject": "001", "biomarkercode": "B001", "matrix": "urine", "labinstitution": "LabCorp"},
                {
                    "id_subject": "002",
                    "biomarkercode": "B002",
                    "matrix": "urine",
                    "labinstitution": "Quest Diagnostics",
                },
            ]
        )

        return layout


@pytest.mark.other
class TestUnknownDataOps(TestValidation):
    def get_adapter(self) -> DataOpsProtocol:
        raise NotImplementedError


@pytest.mark.dataframe
class TestEnrichmentInterface:
    @abc.abstractmethod
    def get_adapter(self) -> DataOpsProtocol:
        """Return the adapter implementation to test."""
        raise NotImplementedError

    def container(self, path: str) -> CacheContainer:
        source = get_absolute_path(path)
        container = CacheContainerFactory.new()
        host = DirectoryIO()
        roots = host.load(source, format="yaml", maxdepth=3)
        for root in roots:
            for entity in load_entities_from_tree(root):
                container.add(entity)

        return container

    def test_getting_default_adapter_from_interface(self):
        adapter_class = DataEnrichmentInterface.get_default_adapter_class()
        adapter = adapter_class()
        assert isinstance(adapter, DataEnrichmentInterface)
        # assert isinstance(adapter, type(self.get_adapter()))

    def load_data(self, observations_path):
        with open(observations_path, "r") as f:
            obs_prop_data = yaml.safe_load(f)
            observations = [Observation(**observation) for observation in obs_prop_data["observations"]]

        return observations

    def test_building_dependency_graph(self):
        adapter = DataEnrichmentInterface.get_default_adapter_class()()

        observations = self.load_data(
            get_absolute_path("./input/ProcessingExamples/Enrichment_01_SINGLE_SOURCE/_YAML_Config/ProjectConfig.yaml")
        )

        container = self.container("./input/ProcessingExamples/Enrichment_01_SINGLE_SOURCE")

        g = adapter.build_dependency_graph(observations, container)

        # Simple check to see if the dependency graph is built
        assert isinstance(g, Graph)

    def test_topological_sort_single_source(self):
        src_path = "./input/ProcessingExamples/Enrichment_01_SINGLE_SOURCE"
        observation_path = "_YAML_Config/ProjectConfig.yaml"
        adapter = DataEnrichmentInterface.get_default_adapter_class()()
        observations = self.load_data(get_absolute_path(src_path + "/" + observation_path))
        container = self.container(src_path)
        g = adapter.build_dependency_graph(observations, container)
        sorted_nodes = g.topological_sort()
        # Simple check to see if the sorted variables list is correct
        assert isinstance(g, Graph)
        assert all(isinstance(var, str) for var in sorted_nodes)
        assert len(sorted_nodes) == len(g.nodes)
        assert sorted_nodes.index(
            "peh:ENRICHMENT_TEST_OBSERVATION_SUBJECT_ENRICHED\\peh:agemonths"
        ) > sorted_nodes.index("peh:ENRICHMENT_TEST_OBSERVATION_SUBJECT_ENRICHED\\N1Birthdate")
        assert sorted_nodes.index(
            "peh:ENRICHMENT_TEST_OBSERVATION_SUBJECT_ENRICHED\\peh:agemonths"
        ) > sorted_nodes.index("peh:ENRICHMENT_TEST_OBSERVATION_SUBJECT_ENRICHED\\Todaysdate")

    def test_topological_sort_linked_source(self):
        src_path = "./input/ProcessingExamples/Enrichment_02_LINKED_SOURCE"
        observation_path = "_YAML_Config/ProjectConfig.yaml"
        adapter = DataEnrichmentInterface.get_default_adapter_class()()
        observations = self.load_data(get_absolute_path(src_path + "/" + observation_path))
        container = self.container(src_path)
        g = adapter.build_dependency_graph(observations, container)
        sorted_nodes = g.topological_sort()
        # Simple check to see if the sorted variables list is correct
        assert isinstance(g, Graph)
        assert all(isinstance(var, str) for var in sorted_nodes)
        assert len(sorted_nodes) == len(g.nodes)
        assert sorted_nodes.index(
            "peh:ENRICHMENT_TEST_OBSERVATION_SUBJECT_ENRICHED\\peh:agemonths"
        ) > sorted_nodes.index("peh:ENRICHMENT_TEST_OBSERVATION_SUBJECT_ENRICHED\\N1Birthdate")
        assert sorted_nodes.index(
            "peh:ENRICHMENT_TEST_OBSERVATION_SUBJECT_ENRICHED\\peh:agemonths"
        ) > sorted_nodes.index("peh:ENRICHMENT_TEST_OBSERVATION_HOUSEHOLD_INGESTED\\Todaysdate")

    def test_topological_sort_multi_steps(self):
        src_path = "./input/ProcessingExamples/Enrichment_03_MULTI_STEP"
        observation_path = "_YAML_Config/ProjectConfig.yaml"
        adapter = DataEnrichmentInterface.get_default_adapter_class()()
        observations = self.load_data(get_absolute_path(src_path + "/" + observation_path))
        container = self.container(src_path)
        g = adapter.build_dependency_graph(observations, container)
        sorted_nodes = g.topological_sort()

        # Simple check to see if the sorted variables list is correct
        assert isinstance(g, Graph)
        assert all(isinstance(var, str) for var in sorted_nodes)
        assert len(sorted_nodes) == len(g.nodes)
        assert sorted_nodes.index(
            "peh:ENRICHMENT_TEST_OBSERVATION_SUBJECT_ENRICHED\\peh:agemonths"
        ) > sorted_nodes.index("peh:ENRICHMENT_TEST_OBSERVATION_SUBJECTUNIQUE_INGESTED\\N1Birthdate")
        assert sorted_nodes.index(
            "peh:ENRICHMENT_TEST_OBSERVATION_SUBJECT_ENRICHED\\peh:agemonths"
        ) > sorted_nodes.index("peh:ENRICHMENT_TEST_OBSERVATION_SUBJECT_ENRICHED\\peh:Todaysdate")
        assert sorted_nodes.index(
            "peh:ENRICHMENT_TEST_OBSERVATION_SUBJECT_ENRICHED\\peh:Todaysdate"
        ) > sorted_nodes.index("peh:ENRICHMENT_TEST_OBSERVATION_SUBJECT_ENRICHED\\peh:current_day")
        assert sorted_nodes.index(
            "peh:ENRICHMENT_TEST_OBSERVATION_SUBJECT_ENRICHED\\peh:Todaysdate"
        ) > sorted_nodes.index("peh:ENRICHMENT_TEST_OBSERVATION_SUBJECT_ENRICHED\\peh:current_month")
        assert sorted_nodes.index(
            "peh:ENRICHMENT_TEST_OBSERVATION_SUBJECT_ENRICHED\\peh:Todaysdate"
        ) > sorted_nodes.index("peh:ENRICHMENT_TEST_OBSERVATION_SUBJECT_ENRICHED\\peh:current_year")
