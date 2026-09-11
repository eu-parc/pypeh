import pytest
import abc
import importlib
import re
import peh_model.peh as peh

from datetime import date
from typing import Protocol, Generic
from peh_model.peh import (
    CalculationDesign,
    CalculationImplementation,
    CalculationKeywordArgument,
    ContextualFieldReference,
    DataLayout,
    Observation,
    ObservationDesign,
    FilterExpression,
    DataImportConfig,
    ObservableProperty,
    ObservablePropertySpecification,
    ObservablePropertySpecificationCategory,
)

from pypeh.core.cache.containers import (
    CacheContainerFactory,
    CacheContainerView,
)
from pypeh.core.cache.utils import load_entities_from_tree
from pypeh.core.interfaces.dataops import (
    DataExtractInterface,
    DataOpsInterface,
    SOURCE_FIELDS_BY_OBSERVABLE_PROPERTY_METADATA_KEY,
    T_DataType,
    ValidationInterface,
)
from pypeh.core.models.internal_data_layout import (
    Dataset,
    DatasetSchema,
    DatasetSchemaElement,
    DatasetSeries,
    ElementReference,
    ForeignKey,
)
from pypeh.core.models.validation_errors import (
    DatasetSchemaError,
    ValidationErrorReport,
)
from pypeh.core.models.constants import (
    ObservablePropertyValueType,
    ValidationErrorLevel,
)
from pypeh.core.models.validation_dto import (
    ValidationExpression,
    ValidationDesign,
    ColumnValidation,
    ValidationConfig,
)
from pypeh.core.models.extract_dto import FilterConfig
from pypeh.core.models.graph import ExecutionPlan, Graph
from pypeh.adapters.persistence.hosts import DirectoryIO
from tests.test_utils.dirutils import get_absolute_path


def add_one(measurement):
    return measurement + 1


class DataOpsProtocol(Protocol, Generic[T_DataType]):
    data_format: T_DataType

    def _validate(self, data, config) -> ValidationErrorReport: ...

    def validate(
        self, dataset, dependent_dataset_series, cache_view, allow_incomplete
    ) -> ValidationErrorReport: ...

    def build_column_validation(
        self, dataset_schema_element, type_annotations, cache_view
    ) -> ColumnValidation: ...

    def build_validation_config(
        self, dataset, dataset_series, cache_view, allow_incomplete=False
    ) -> ValidationConfig: ...

    def build_dependency_graph(
        self, observations, context_index, cache_view, join_spec_mapping
    ): ...

    def compile_dependency_graph(self, dependency_graph) -> ExecutionPlan: ...

    def compute_with_dependency_graph(self, dependency_graph, datasets): ...

    def split_by_observation(
        self,
        dataset_series: DatasetSeries[T_DataType],
        *,
        new_label: str | None = None,
        cache_view: CacheContainerView | None = None,
        label_collision_strategy="prefix_source_dataset",
    ) -> DatasetSeries[T_DataType]: ...

    def enrich(
        self,
        source_dataset_series,
        target_observations,
        target_derived_from,
        cache_view,
        target_label_collision_strategy="error",
    ): ...

    def summarize(
        self,
        source_dataset_series,
        target_observations,
        target_derived_from,
        cache_view,
        target_label_collision_strategy="error",
    ): ...

    def matches_schema(self, raw_data_dict, dataset_series) -> bool: ...


class TestValidation(abc.ABC):
    """Abstract base class for testing dataops adapters."""

    __test__ = False

    @abc.abstractmethod
    def get_adapter(self) -> DataOpsProtocol:
        """Return the adapter implementation to test."""
        raise NotImplementedError

    def get_container(self, path: str, is_file=True) -> CacheContainerView:
        source = get_absolute_path(path)
        container = CacheContainerFactory.new()
        host = DirectoryIO()
        roots = host.load(source, format="yaml")
        if is_file:
            roots = [roots]
        for root in roots:
            for entity in load_entities_from_tree(root):
                container.add(entity)

        return CacheContainerView(container)

    def get_container_validation_example_03(self) -> CacheContainerView:
        src_path = "./input/ValidationExamples/validation_test_03_corrected_config.yaml"
        cache_view = self.get_container(src_path)
        return cache_view

    @staticmethod
    def get_data_layout_element(cache_view, dataset, element_label):
        layout_section = cache_view.require(
            dataset.described_by, "DataLayoutSection"
        )
        return next(
            element
            for element in layout_section.elements
            if element.label == element_label
        )

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

    def test_build_validation_config(self):
        adapter = self.get_adapter()
        cache_view = self.get_container_validation_example_03()
        data_layout = cache_view.get(
            "peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA", "DataLayout"
        )
        assert isinstance(data_layout, DataLayout)
        dataset_series = DatasetSeries.from_peh_datalayout(
            data_layout=data_layout, cache_view=cache_view
        )
        dataset = dataset_series.get("SAMPLETIMEPOINT_BSS")
        assert dataset is not None
        validation_config = adapter.build_validation_config(
            dataset=dataset,
            dataset_series=dataset_series,
            cache_view=cache_view,
        )
        assert isinstance(validation_config, ValidationConfig)

    def test_build_validation_config_excludes_self_dataset_dependencies(self):
        adapter = self.get_adapter()
        cache_view = self.get_container_validation_example_03()
        data_layout = cache_view.get(
            "peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA", "DataLayout"
        )
        assert isinstance(data_layout, DataLayout)
        dataset_series = DatasetSeries.from_peh_datalayout(
            data_layout=data_layout, cache_view=cache_view
        )
        dataset = dataset_series.get("SAMPLETIMEPOINT_BSS")
        assert dataset is not None

        validation_config = adapter.build_validation_config(
            dataset=dataset,
            dataset_series=dataset_series,
            cache_view=cache_view,
        )
        assert dataset.label not in (
            validation_config.dependent_contextual_field_references or {}
        )

    def test_build_column_validation_with_custom_message(self):
        adapter = self.get_adapter()
        cache_view = self.get_container_validation_example_03()
        data_layout = cache_view.get(
            "peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA", "DataLayout"
        )
        assert isinstance(data_layout, DataLayout)
        dataset_series = DatasetSeries.from_peh_datalayout(
            data_layout=data_layout, cache_view=cache_view
        )
        type_annotations = dataset_series.get_type_annotations()
        dataset = dataset_series.get("SAMPLETIMEPOINT_BSS")
        assert dataset is not None
        dataset_schema_element = dataset.get_schema_element_by_label("chol")
        cv = adapter.build_column_validation(
            dataset_schema_element=dataset_schema_element,
            type_annotations=type_annotations,
            cache_view=cache_view,
            data_layout_element=self.get_data_layout_element(
                cache_view, dataset, "chol"
            ),
        )
        assert cv.validations is not None
        collect_messages = [
            vd.error_message for vd in cv.validations if vd.error_message
        ]
        pattern = r"IF matrix IS\s*\([^)]*\)"
        found = any(re.search(pattern, msg) for msg in collect_messages)
        assert found

    def test_data_layout_element_validation_designs_take_precedence(self):
        adapter = self.get_adapter()
        cache_view = self.get_container_validation_example_03()
        data_layout = cache_view.get(
            "peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA", "DataLayout"
        )
        dataset_series = DatasetSeries.from_peh_datalayout(
            data_layout=data_layout, cache_view=cache_view
        )
        dataset = dataset_series.get("SAMPLETIMEPOINT_BSS")
        assert dataset is not None
        schema_element = dataset.get_schema_element_by_label("chol")
        assert schema_element is not None
        observable_property = cache_view.get(
            schema_element.observable_property_id, "ObservableProperty"
        )
        observable_property.validation_designs = [
            peh.ValidationDesign(
                validation_name="legacy_property_rule",
                validation_expression=peh.ValidationExpression(
                    validation_command="is_null"
                ),
            )
        ]
        data_layout_element = self.get_data_layout_element(
            cache_view, dataset, "chol"
        )
        data_layout_element.validation_designs = [
            peh.ValidationDesign(
                validation_name="layout_element_rule",
                validation_expression=peh.ValidationExpression(
                    validation_command="is_not_null"
                ),
            )
        ]

        column_validation = adapter.build_column_validation(
            dataset_schema_element=schema_element,
            type_annotations=dataset_series.get_type_annotations(),
            cache_view=cache_view,
            data_layout_element=data_layout_element,
            dataset_label=dataset.label,
        )

        validation_names = {
            validation.name for validation in column_validation.validations
        }
        assert "layout_element_rule" in validation_names
        assert "legacy_property_rule" not in validation_names

    def test_legacy_observable_property_validation_designs_are_supported(self):
        """Remove with legacy ObservableProperty validation support."""
        adapter = self.get_adapter()
        cache_view = self.get_container_validation_example_03()
        data_layout = cache_view.get(
            "peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA", "DataLayout"
        )
        dataset_series = DatasetSeries.from_peh_datalayout(
            data_layout=data_layout, cache_view=cache_view
        )
        dataset = dataset_series.get("SAMPLETIMEPOINT_BSS")
        assert dataset is not None
        schema_element = dataset.get_schema_element_by_label("chol")
        assert schema_element is not None
        observable_property = cache_view.get(
            schema_element.observable_property_id, "ObservableProperty"
        )
        observable_property.validation_designs = [
            peh.ValidationDesign(
                validation_name="legacy_property_rule",
                validation_expression=peh.ValidationExpression(
                    validation_command="is_not_null"
                ),
            )
        ]

        column_validation = adapter.build_column_validation(
            dataset_schema_element=schema_element,
            type_annotations=dataset_series.get_type_annotations(),
            cache_view=cache_view,
            dataset_label=dataset.label,
        )

        assert any(
            validation.name == "legacy_property_rule"
            for validation in column_validation.validations
        )

    def test_build_column_validation_from_observable_property_bounds(self):
        adapter = self.get_adapter()
        cache_view = self.get_container_validation_example_03()
        data_layout = cache_view.get(
            "peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA", "DataLayout"
        )
        assert isinstance(data_layout, DataLayout)
        dataset_series = DatasetSeries.from_peh_datalayout(
            data_layout=data_layout, cache_view=cache_view
        )
        type_annotations = dataset_series.get_type_annotations()
        dataset = dataset_series.get("SAMPLETIMEPOINT_BSS")
        assert dataset is not None
        dataset_schema_element = dataset.get_schema_element_by_label(
            "chol_lod"
        )
        assert dataset_schema_element is not None
        observable_property = cache_view.get(
            dataset_schema_element.observable_property_id, "ObservableProperty"
        )
        assert isinstance(observable_property, ObservableProperty)
        observable_property.min = "0.2"
        observable_property.max = "999.9"

        cv = adapter.build_column_validation(
            dataset_schema_element=dataset_schema_element,
            type_annotations=type_annotations,
            cache_view=cache_view,
        )

        assert cv.validations is not None
        bounds_by_name = {vd.name: vd for vd in cv.validations}
        assert "min" in bounds_by_name
        assert "max" in bounds_by_name
        assert (
            bounds_by_name["min"].expression.command
            == "is_greater_than_or_equal_to"
        )
        assert (
            bounds_by_name["max"].expression.command
            == "is_less_than_or_equal_to"
        )
        assert bounds_by_name["min"].expression.arg_values == [0.2]
        assert bounds_by_name["max"].expression.arg_values == [999.9]

    def test_build_column_validation_with_significant_decimals(self):
        adapter = self.get_adapter()
        cache_view = self.get_container_validation_example_03()
        data_layout = cache_view.get(
            "peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA", "DataLayout"
        )
        assert isinstance(data_layout, DataLayout)
        dataset_series = DatasetSeries.from_peh_datalayout(
            data_layout=data_layout, cache_view=cache_view
        )
        type_annotations = dataset_series.get_type_annotations()
        dataset = dataset_series.get("SAMPLETIMEPOINT_BSS")
        assert dataset is not None
        dataset_schema_element = dataset.get_schema_element_by_label("chol")
        assert dataset_schema_element is not None
        observable_property = cache_view.get(
            dataset_schema_element.observable_property_id, "ObservableProperty"
        )
        assert isinstance(observable_property, ObservableProperty)
        observable_property.significantdecimals = 3

        cv = adapter.build_column_validation(
            dataset_schema_element=dataset_schema_element,
            type_annotations=type_annotations,
            cache_view=cache_view,
        )

        assert cv.validations is not None
        sig_dec_validations = [
            v for v in cv.validations if v.name == "check_significant_decimals"
        ]
        assert len(sig_dec_validations) == 1
        assert (
            sig_dec_validations[0].expression.command == "decimals_precision"
        )
        assert sig_dec_validations[0].expression.arg_values == [3]
        assert (
            sig_dec_validations[0].error_message
            == "Decimal precision exceeds 3 allowed decimal places."
        )


class TestDataImport(abc.ABC):
    """Abstract base class for testing dataops adapters."""

    __test__ = False

    @abc.abstractmethod
    def get_adapter(self) -> DataOpsProtocol:
        """Return the adapter implementation to test."""
        raise NotImplementedError

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


class TestDatasetSeriesMods(abc.ABC):
    __test__ = False

    def get_adapter(self):
        raise NotImplementedError

    @pytest.fixture(scope="function")
    def raw_data(self):
        raise NotImplementedError

    @pytest.fixture(scope="function")
    def observation_designs(self) -> dict[str, list[ObservationDesign]]:
        ret = {
            "urine_lab": [
                ObservationDesign(
                    id="peh:urine_lab_this_design",
                    observable_property_specifications=[
                        ObservablePropertySpecification(
                            observable_property="id_subject",
                            specification_category=ObservablePropertySpecificationCategory.identifying,
                        ),
                        ObservablePropertySpecification(
                            observable_property="matrix",
                            specification_category=ObservablePropertySpecificationCategory.required,
                        ),
                        ObservablePropertySpecification(
                            observable_property="crt",
                            specification_category=ObservablePropertySpecificationCategory.required,
                        ),
                    ],
                ),
                ObservationDesign(
                    id="peh:urine_lab_other_design",
                    observable_property_specifications=[
                        ObservablePropertySpecification(
                            observable_property="id_subject",
                            specification_category=ObservablePropertySpecificationCategory.identifying,
                        ),
                        ObservablePropertySpecification(
                            observable_property="crt_lod",
                            specification_category=ObservablePropertySpecificationCategory.required,
                        ),
                        ObservablePropertySpecification(
                            observable_property="crt_loq",
                            specification_category=ObservablePropertySpecificationCategory.required,
                        ),
                        ObservablePropertySpecification(
                            observable_property="sg",
                            specification_category=ObservablePropertySpecificationCategory.required,
                        ),
                    ],
                ),
            ],
            "analyticalinfo": [
                ObservationDesign(
                    id="peh:analytical_info_obs_design",
                    observable_property_specifications=[
                        ObservablePropertySpecification(
                            observable_property="id_subject",
                            specification_category=ObservablePropertySpecificationCategory.identifying,
                        ),
                        ObservablePropertySpecification(
                            observable_property="biomarkercode",
                            specification_category=ObservablePropertySpecificationCategory.required,
                        ),
                        ObservablePropertySpecification(
                            observable_property="matrix",
                            specification_category=ObservablePropertySpecificationCategory.required,
                        ),
                        ObservablePropertySpecification(
                            observable_property="labinstitution",
                            specification_category=ObservablePropertySpecificationCategory.required,
                        ),
                    ],
                ),
            ],
        }
        return ret

    @pytest.fixture(scope="function")
    def observations(self, raw_data) -> dict[str, list[Observation]]:
        ret = {
            "urine_lab": [
                Observation(
                    id="peh:urine_lab_this",
                    ui_label="urine_lab_this",
                    observation_design="peh:urine_lab_this_design",
                ),
                Observation(
                    id="peh:urine_lab_other",
                    ui_label="urine_lab_this",
                    observation_design="peh:urine_lab_other_design",
                ),
            ],
            "analyticalinfo": [
                Observation(
                    id="peh:analytical_info_obs",
                    ui_label="analytical_info_obs",
                    observation_design="peh:analytical_info_obs_design",
                )
            ],
        }

        return ret

    @pytest.fixture(scope="function")
    def dataset_series(self, raw_data) -> DatasetSeries:
        # Schema for urine_lab
        urine_lab_schema = DatasetSchema(
            elements={
                "id_subject": DatasetSchemaElement(
                    label="id_subject",
                    observable_property_id="id_subject",
                    data_type=ObservablePropertyValueType.STRING,
                ),
                "matrix": DatasetSchemaElement(
                    label="matrix",
                    observable_property_id="matrix",
                    data_type=ObservablePropertyValueType.STRING,
                ),
                "crt": DatasetSchemaElement(
                    label="crt",
                    observable_property_id="crt",
                    data_type=ObservablePropertyValueType.FLOAT,
                ),
                "crt_lod": DatasetSchemaElement(
                    label="crt_lod",
                    observable_property_id="crt_lod",
                    data_type=ObservablePropertyValueType.FLOAT,
                ),
                "crt_loq": DatasetSchemaElement(
                    label="crt_loq",
                    observable_property_id="crt_loq",
                    data_type=ObservablePropertyValueType.FLOAT,
                ),
                "sg": DatasetSchemaElement(
                    label="sg",
                    observable_property_id="sg",
                    data_type=ObservablePropertyValueType.FLOAT,
                ),
            },
            primary_keys={"id_subject"},
            foreign_keys={},
        )

        # Schema for analyticalinfo
        analyticalinfo_schema = DatasetSchema(
            elements={
                "id_subject": DatasetSchemaElement(
                    label="id_subject",
                    observable_property_id="id_subject",
                    data_type=ObservablePropertyValueType.STRING,
                ),
                "biomarkercode": DatasetSchemaElement(
                    label="biomarkercode",
                    observable_property_id="biomarkercode",
                    data_type=ObservablePropertyValueType.STRING,
                ),
                "matrix": DatasetSchemaElement(
                    label="matrix",
                    observable_property_id="matrix",
                    data_type=ObservablePropertyValueType.STRING,
                ),
                "labinstitution": DatasetSchemaElement(
                    label="labinstitution",
                    observable_property_id="labinstitution",
                    data_type=ObservablePropertyValueType.STRING,
                ),
            },
            primary_keys={"id_subject", "biomarkercode"},
            foreign_keys={
                "fk_subject": ForeignKey(
                    element_label="id_subject",
                    reference=ElementReference(
                        dataset_label="urine_lab",
                        element_label="id_subject",
                    ),
                )
            },
        )

        # --- DATASET INSTANCES ------------------------------------------------------

        urine_lab_dataset = Dataset(
            label="urine_lab",
            schema=urine_lab_schema,
            data=raw_data["urine_lab"],
            observation_ids=set(["peh:urine_lab_this", "peh:urine_lab_other"]),
        )

        analyticalinfo_dataset = Dataset(
            label="analyticalinfo",
            schema=analyticalinfo_schema,
            data=raw_data["analyticalinfo"],
            observation_ids=set(["peh:analyticalinfo_obs"]),
        )

        # --- DATASET SERIES ---------------------------------------------------------

        series = DatasetSeries(
            label="urine_study_series",
            parts={
                "urine_lab": urine_lab_dataset,
                "analyticalinfo": analyticalinfo_dataset,
            },
        )
        # Make the reverse link (Dataset.part_of)
        urine_lab_dataset.part_of = series
        analyticalinfo_dataset.part_of = series

        return series

    def test_split_by_observation_check_indices(self, dataset_series):
        adapter = self.get_adapter()
        dataset_series._register_observable_property(
            "id_subject", "peh:urine_lab_this", "urine_lab", "id_subject"
        )
        dataset_series._register_observable_property(
            "matrix", "peh:urine_lab_this", "urine_lab", "matrix"
        )
        dataset_series._register_observable_property(
            "crt", "peh:urine_lab_this", "urine_lab", "crt"
        )
        dataset_series._register_observable_property(
            "id_subject", "peh:urine_lab_other", "urine_lab", "id_subject"
        )
        dataset_series._register_observable_property(
            "crt_lod", "peh:urine_lab_other", "urine_lab", "crt_lod"
        )
        dataset_series._register_observable_property(
            "crt_loq", "peh:urine_lab_other", "urine_lab", "crt_loq"
        )
        dataset_series._register_observable_property(
            "sg", "peh:urine_lab_other", "urine_lab", "sg"
        )
        dataset_series._register_observable_property(
            "id_subject",
            "peh:analyticalinfo_obs",
            "analyticalinfo",
            "id_subject",
        )
        dataset_series._register_observable_property(
            "biomarkercode",
            "peh:analyticalinfo_obs",
            "analyticalinfo",
            "biomarkercode",
        )
        dataset_series._register_observable_property(
            "matrix",
            "peh:analyticalinfo_obs",
            "analyticalinfo",
            "matrix",
        )
        dataset_series._register_observable_property(
            "labinstitution",
            "peh:analyticalinfo_obs",
            "analyticalinfo",
            "labinstitution",
        )
        # NOTE: dataset_series does not contain an observation_index !
        split_series = adapter.split_by_observation(dataset_series)

        assert len(split_series.parts) == 3
        for dataset in split_series.parts.values():
            assert len(dataset.observation_ids) == 1

        assert split_series.context_lookup("peh:urine_lab_this", "crt")[0] == (
            "peh:urine_lab_this"
        )
        assert split_series.context_lookup("peh:urine_lab_other", "crt_lod")[
            0
        ] == ("peh:urine_lab_other")
        assert split_series.context_lookup(
            "peh:analyticalinfo_obs", "labinstitution"
        )[0] == ("peh:analyticalinfo_obs")

    @abc.abstractmethod
    def mixed_join_and_single_dataset_data(self):
        raise NotImplementedError

    @abc.abstractmethod
    def verify_join_and_single_dataset(
        self, split_series: DatasetSeries, adapter: DataOpsProtocol
    ):
        raise NotImplementedError

    def test_split_by_observation_mixed_join_and_single_dataset(self):
        # FIXME: currently limited to dataframe implementation

        adapter = self.get_adapter()
        dataset_series = DatasetSeries(label="mixed_split_case")

        left_dataset = dataset_series.add_empty_dataset("left")
        right_dataset = dataset_series.add_empty_dataset("right")

        left_dataset.add_observation_to_index("obs:1")
        left_dataset.add_observation_to_index("obs:2")
        right_dataset.add_observation_to_index("obs:1")

        # left schema
        left_dataset.add_observable_property(
            observable_property_id="shared_id_prop",
            data_type=ObservablePropertyValueType.STRING,
            element_label="id",
            is_primary_key=True,
        )
        left_dataset.add_observable_property(
            observable_property_id="obs1_left_prop",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="left_measure",
        )
        left_dataset.add_observable_property(
            observable_property_id="obs2_left_prop",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="left_other_measure",
        )

        # right schema
        right_dataset.add_observable_property(
            observable_property_id="right_fk_prop",
            data_type=ObservablePropertyValueType.STRING,
            element_label="left_id",
        )
        right_dataset.add_observable_property(
            observable_property_id="obs1_right_prop",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="right_measure",
        )
        right_dataset.schema.add_foreign_key_link(
            element_label="left_id",
            foreign_key_dataset_label="left",
            foreign_key_element_label="id",
        )

        # Context index links: obs:1 spans left+right, obs:2 is only on left.
        dataset_series._register_observable_property(
            "shared_id_prop", "obs:1", "left", "id"
        )
        dataset_series._register_observable_property(
            "obs1_left_prop", "obs:1", "left", "left_measure"
        )
        dataset_series._register_observable_property(
            "obs1_right_prop", "obs:1", "right", "right_measure"
        )
        dataset_series._register_observable_property(
            "shared_id_prop", "obs:2", "left", "id"
        )
        dataset_series._register_observable_property(
            "obs2_left_prop", "obs:2", "left", "left_other_measure"
        )

        left_dataset_data, right_dataset_data = (
            self.mixed_join_and_single_dataset_data()
        )
        left_dataset.data = left_dataset_data
        right_dataset.data = right_dataset_data

        split_series = adapter.split_by_observation(dataset_series)
        assert isinstance(split_series, DatasetSeries)
        assert set(split_series.parts.keys()) == {"obs:1", "obs:2"}
        assert len(split_series.parts["obs:1"].observation_ids) == 1
        assert len(split_series.parts["obs:2"].observation_ids) == 1
        assert split_series.parts["obs:1"].metadata[
            SOURCE_FIELDS_BY_OBSERVABLE_PROPERTY_METADATA_KEY
        ] == {
            "obs1_left_prop": {
                "dataset_label": "left",
                "element_label": "left_measure",
            },
            "obs1_right_prop": {
                "dataset_label": "right",
                "element_label": "right_measure",
            },
            "shared_id_prop": {
                "dataset_label": "left",
                "element_label": "id",
            },
        }
        self.verify_join_and_single_dataset(split_series, adapter)

    def test_split_by_observation_preserves_right_only_rows(self):
        import polars as pl

        adapter = self.get_adapter()
        dataset_series = DatasetSeries(label="outer_split_case")

        left_dataset = dataset_series.add_empty_dataset("left")
        right_dataset = dataset_series.add_empty_dataset("right")
        left_dataset.add_observation_to_index("obs:1")
        right_dataset.add_observation_to_index("obs:1")

        left_dataset.add_observable_property(
            observable_property_id="shared_id_prop",
            data_type=ObservablePropertyValueType.STRING,
            element_label="id",
            is_primary_key=True,
        )
        left_dataset.add_observable_property(
            observable_property_id="obs1_left_prop",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="left_measure",
        )
        right_dataset.add_observable_property(
            observable_property_id="right_fk_prop",
            data_type=ObservablePropertyValueType.STRING,
            element_label="left_id",
        )
        right_dataset.add_observable_property(
            observable_property_id="obs1_right_prop",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="right_measure",
        )
        right_dataset.schema.add_foreign_key_link(
            element_label="left_id",
            foreign_key_dataset_label="left",
            foreign_key_element_label="id",
        )
        dataset_series._register_observable_property(
            "shared_id_prop", "obs:1", "left", "id"
        )
        dataset_series._register_observable_property(
            "obs1_left_prop", "obs:1", "left", "left_measure"
        )
        dataset_series._register_observable_property(
            "obs1_right_prop", "obs:1", "right", "right_measure"
        )

        left_data, right_data = self.mixed_join_and_single_dataset_data()
        left_dataset.data = adapter.subset(
            left_data, element_group=["id", "left_measure"]
        )
        right_dataset.data = right_data.vstack(
            pl.DataFrame({"left_id": ["003"], "right_measure": [300.0]})
        )

        split_series = adapter.split_by_observation(dataset_series)

        obs1_data = split_series.parts["obs:1"].data
        assert obs1_data is not None
        id_label = split_series.context_lookup("obs:1", "shared_id_prop")[1]
        left_label = split_series.context_lookup("obs:1", "obs1_left_prop")[1]
        right_label = split_series.context_lookup("obs:1", "obs1_right_prop")[
            1
        ]
        sorted_obs1_data = obs1_data.sort(id_label)
        assert sorted_obs1_data.get_column(id_label).to_list() == [
            "001",
            "002",
            "003",
        ]
        assert sorted_obs1_data.get_column(left_label).to_list() == [
            10.0,
            20.0,
            None,
        ]
        assert sorted_obs1_data.get_column(right_label).to_list() == [
            100.0,
            200.0,
            300.0,
        ]

    def test_split_by_observation_prefixes_colliding_fields(self):
        adapter = self.get_adapter()
        dataset_series = DatasetSeries(label="prefix_split_case")

        left_dataset = dataset_series.add_empty_dataset("left")
        right_dataset = dataset_series.add_empty_dataset("right")
        left_dataset.add_observation_to_index("obs:1")
        right_dataset.add_observation_to_index("obs:1")

        left_dataset.add_observable_property(
            observable_property_id="id_prop",
            data_type=ObservablePropertyValueType.STRING,
            element_label="id",
            is_primary_key=True,
        )
        left_dataset.add_observable_property(
            observable_property_id="left_prop",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="measure",
        )
        right_dataset.add_observable_property(
            observable_property_id="right_id_prop",
            data_type=ObservablePropertyValueType.STRING,
            element_label="id",
        )
        right_dataset.add_observable_property(
            observable_property_id="right_prop",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="measure",
        )
        right_dataset.schema.add_foreign_key_link(
            element_label="id",
            foreign_key_dataset_label="left",
            foreign_key_element_label="id",
        )
        dataset_series._register_observable_property(
            "id_prop", "obs:1", "left", "id"
        )
        dataset_series._register_observable_property(
            "left_prop", "obs:1", "left", "measure"
        )
        dataset_series._register_observable_property(
            "right_prop", "obs:1", "right", "measure"
        )

        left_data, right_data = self.mixed_join_and_single_dataset_data()
        left_dataset.data = adapter.relabel(
            adapter.subset(left_data, element_group=["id", "left_measure"]),
            {"left_measure": "measure"},
        )
        right_dataset.data = adapter.relabel(
            adapter.subset(
                right_data, element_group=["left_id", "right_measure"]
            ),
            {"left_id": "id", "right_measure": "measure"},
        )

        split_series = adapter.split_by_observation(
            dataset_series,
            label_collision_strategy="prefix_source_dataset",
        )

        assert split_series.context_lookup("obs:1", "left_prop") == (
            "obs:1",
            "measure",
        )
        assert split_series.context_lookup("obs:1", "right_prop") == (
            "obs:1",
            "right__measure",
        )

    def test_split_by_observation_does_not_prefix_join_keys(self):
        adapter = self.get_adapter()
        dataset_series = DatasetSeries(label="join_key_collision_case")

        left_dataset = dataset_series.add_empty_dataset("left")
        right_dataset = dataset_series.add_empty_dataset("right")
        left_dataset.add_observation_to_index("obs:1")
        right_dataset.add_observation_to_index("obs:1")

        left_dataset.add_observable_property(
            observable_property_id="id_prop",
            data_type=ObservablePropertyValueType.STRING,
            element_label="id",
            is_primary_key=True,
        )
        left_dataset.add_observable_property(
            observable_property_id="left_prop",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="left_measure",
        )
        right_dataset.add_observable_property(
            observable_property_id="right_id_prop",
            data_type=ObservablePropertyValueType.STRING,
            element_label="id",
        )
        right_dataset.add_observable_property(
            observable_property_id="right_prop",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="right_measure",
        )
        right_dataset.schema.add_foreign_key_link(
            element_label="id",
            foreign_key_dataset_label="left",
            foreign_key_element_label="id",
        )
        dataset_series._register_observable_property(
            "id_prop", "obs:1", "left", "id"
        )
        dataset_series._register_observable_property(
            "right_id_prop", "obs:1", "right", "id"
        )
        dataset_series._register_observable_property(
            "left_prop", "obs:1", "left", "left_measure"
        )
        dataset_series._register_observable_property(
            "right_prop", "obs:1", "right", "right_measure"
        )

        left_data, right_data = self.mixed_join_and_single_dataset_data()
        left_dataset.data = adapter.subset(
            left_data, element_group=["id", "left_measure"]
        )
        right_dataset.data = adapter.relabel(
            adapter.subset(
                right_data, element_group=["left_id", "right_measure"]
            ),
            {"left_id": "id"},
        )

        split_series = adapter.split_by_observation(
            dataset_series,
            label_collision_strategy="error",
        )
        split_dataset = split_series["obs:1"]

        assert split_dataset is not None
        assert set(split_dataset.get_element_labels()) == {
            "id",
            "left_measure",
            "right_measure",
        }
        assert set(adapter.get_element_labels(split_dataset.data)) == {
            "id",
            "left_measure",
            "right_measure",
        }
        assert split_series.context_lookup("obs:1", "id_prop") == (
            "obs:1",
            "id",
        )
        assert split_series.context_lookup("obs:1", "right_id_prop") == (
            "obs:1",
            "id",
        )

    def test_split_by_observation_prefixes_observable_property_id(self):
        adapter = self.get_adapter()
        dataset_series = DatasetSeries(label="observable_prefix_split_case")

        left_dataset = dataset_series.add_empty_dataset("left")
        right_dataset = dataset_series.add_empty_dataset("right")
        left_dataset.add_observation_to_index("obs:1")
        right_dataset.add_observation_to_index("obs:1")

        left_dataset.add_observable_property(
            observable_property_id="id_prop",
            data_type=ObservablePropertyValueType.STRING,
            element_label="id",
            is_primary_key=True,
        )
        left_dataset.add_observable_property(
            observable_property_id="left_prop",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="measure",
        )
        right_dataset.add_observable_property(
            observable_property_id="right_id_prop",
            data_type=ObservablePropertyValueType.STRING,
            element_label="id",
        )
        right_dataset.add_observable_property(
            observable_property_id="right_prop",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="measure",
        )
        right_dataset.schema.add_foreign_key_link(
            element_label="id",
            foreign_key_dataset_label="left",
            foreign_key_element_label="id",
        )
        dataset_series._register_observable_property(
            "id_prop", "obs:1", "left", "id"
        )
        dataset_series._register_observable_property(
            "left_prop", "obs:1", "left", "measure"
        )
        dataset_series._register_observable_property(
            "right_prop", "obs:1", "right", "measure"
        )

        left_data, right_data = self.mixed_join_and_single_dataset_data()
        left_dataset.data = adapter.relabel(
            adapter.subset(left_data, element_group=["id", "left_measure"]),
            {"left_measure": "measure"},
        )
        right_dataset.data = adapter.relabel(
            adapter.subset(
                right_data, element_group=["left_id", "right_measure"]
            ),
            {"left_id": "id", "right_measure": "measure"},
        )

        split_series = adapter.split_by_observation(
            dataset_series,
            label_collision_strategy="prefix_observable_property_id",
        )

        assert split_series.context_lookup("obs:1", "left_prop") == (
            "obs:1",
            "measure",
        )
        assert split_series.context_lookup("obs:1", "right_prop") == (
            "obs:1",
            "right_prop__measure",
        )

    def test_split_by_observation_rejects_colliding_fields(self):
        adapter = self.get_adapter()
        dataset_series = DatasetSeries(label="error_split_case")

        left_dataset = dataset_series.add_empty_dataset("left")
        right_dataset = dataset_series.add_empty_dataset("right")
        left_dataset.add_observation_to_index("obs:1")
        right_dataset.add_observation_to_index("obs:1")

        left_dataset.add_observable_property(
            observable_property_id="id_prop",
            data_type=ObservablePropertyValueType.STRING,
            element_label="id",
            is_primary_key=True,
        )
        left_dataset.add_observable_property(
            observable_property_id="left_prop",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="measure",
        )
        right_dataset.add_observable_property(
            observable_property_id="right_id_prop",
            data_type=ObservablePropertyValueType.STRING,
            element_label="id",
        )
        right_dataset.add_observable_property(
            observable_property_id="right_prop",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="measure",
        )
        right_dataset.schema.add_foreign_key_link(
            element_label="id",
            foreign_key_dataset_label="left",
            foreign_key_element_label="id",
        )
        dataset_series._register_observable_property(
            "id_prop", "obs:1", "left", "id"
        )
        dataset_series._register_observable_property(
            "left_prop", "obs:1", "left", "measure"
        )
        dataset_series._register_observable_property(
            "right_prop", "obs:1", "right", "measure"
        )

        left_data, right_data = self.mixed_join_and_single_dataset_data()
        left_dataset.data = adapter.relabel(
            adapter.subset(left_data, element_group=["id", "left_measure"]),
            {"left_measure": "measure"},
        )
        right_dataset.data = adapter.relabel(
            adapter.subset(
                right_data, element_group=["left_id", "right_measure"]
            ),
            {"left_id": "id", "right_measure": "measure"},
        )

        with pytest.raises(ValueError, match="would collide"):
            adapter.split_by_observation(
                dataset_series,
                label_collision_strategy="error",
            )

    def test_split_by_observation_uses_observation_label_from_cache(self):
        adapter = self.get_adapter()
        dataset_series = DatasetSeries(label="labeled_split_case")
        dataset = dataset_series.add_empty_dataset("source")
        dataset.add_observation_to_index("obs:ui")
        dataset.add_observation_to_index("obs:short")
        dataset.add_observable_property(
            observable_property_id="id_prop",
            data_type=ObservablePropertyValueType.STRING,
            element_label="id",
            is_primary_key=True,
        )
        dataset.add_observable_property(
            observable_property_id="measure_prop",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="left_measure",
        )
        dataset_series._register_observable_property(
            "id_prop", "obs:ui", "source", "id"
        )
        dataset_series._register_observable_property(
            "measure_prop", "obs:ui", "source", "left_measure"
        )
        dataset_series._register_observable_property(
            "id_prop", "obs:short", "source", "id"
        )
        dataset_series._register_observable_property(
            "measure_prop", "obs:short", "source", "left_measure"
        )

        left_data, _ = self.mixed_join_and_single_dataset_data()
        dataset.data = adapter.subset(
            left_data, element_group=["id", "left_measure"]
        )

        container = CacheContainerFactory.new()
        container.add(
            Observation(
                id="obs:ui",
                ui_label="friendly_observation",
                short_name="short_observation",
            )
        )
        container.add(Observation(id="obs:short", short_name="short_only"))
        cache_view = CacheContainerView(container)

        split_series = adapter.split_by_observation(
            dataset_series, cache_view=cache_view
        )

        assert set(split_series.parts) == {
            "friendly_observation",
            "short_only",
        }
        assert split_series.context_lookup("obs:ui", "measure_prop")[0] == (
            "friendly_observation"
        )
        assert split_series.context_lookup("obs:short", "measure_prop")[0] == (
            "short_only"
        )

    def test_split_by_observation_rejects_duplicate_cache_labels(self):
        adapter = self.get_adapter()
        dataset_series = DatasetSeries(label="duplicate_label_split_case")
        dataset = dataset_series.add_empty_dataset("source")
        dataset.add_observation_to_index("obs:one")
        dataset.add_observation_to_index("obs:two")
        dataset.add_observable_property(
            observable_property_id="id_prop",
            data_type=ObservablePropertyValueType.STRING,
            element_label="id",
            is_primary_key=True,
        )
        dataset_series._register_observable_property(
            "id_prop", "obs:one", "source", "id"
        )
        dataset_series._register_observable_property(
            "id_prop", "obs:two", "source", "id"
        )
        left_data, _ = self.mixed_join_and_single_dataset_data()
        dataset.data = adapter.subset(left_data, element_group=["id"])

        container = CacheContainerFactory.new()
        container.add(Observation(id="obs:one", ui_label="duplicate"))
        container.add(Observation(id="obs:two", ui_label="duplicate"))
        cache_view = CacheContainerView(container)

        with pytest.raises(ValueError, match="must be unique"):
            adapter.split_by_observation(dataset_series, cache_view=cache_view)

    def test_extract_labeled_specs_rejects_duplicate_element_labels(self):
        adapter = self.get_adapter()
        container = CacheContainerFactory.new()
        container.add(
            Observation(
                id="obs:derived",
                observation_design="design:derived",
            )
        )
        container.add(
            ObservationDesign(
                id="design:derived",
                observable_property_specifications=[
                    ObservablePropertySpecification(
                        observable_property="prop:first",
                        specification_category=(
                            ObservablePropertySpecificationCategory.derived
                        ),
                    ),
                    ObservablePropertySpecification(
                        observable_property="prop:second",
                        specification_category=(
                            ObservablePropertySpecificationCategory.derived
                        ),
                    ),
                ],
            )
        )
        container.add(
            ObservableProperty(
                id="prop:first",
                short_name="duplicate_label",
                ui_label="duplicate_label",
                value_type="string",
            )
        )
        container.add(
            ObservableProperty(
                id="prop:second",
                short_name="duplicate_label",
                ui_label="duplicate_label",
                value_type="string",
            )
        )
        cache_view = CacheContainerView(container)
        observation = cache_view.require("obs:derived", "Observation")

        with pytest.raises(
            ValueError,
            match=(
                "resolves multiple observable properties to element label "
                "'duplicate_label'"
            ),
        ):
            adapter.extract_labeled_observable_property_specifications(
                observation, cache_view
            )

    def test_extract_labeled_specs_prefixes_observable_property_id(self):
        adapter = self.get_adapter()
        container = CacheContainerFactory.new()
        container.add(
            Observation(
                id="obs:derived",
                observation_design="design:derived",
            )
        )
        container.add(
            ObservationDesign(
                id="design:derived",
                observable_property_specifications=[
                    ObservablePropertySpecification(
                        observable_property="prop:first",
                        specification_category=(
                            ObservablePropertySpecificationCategory.derived
                        ),
                    ),
                    ObservablePropertySpecification(
                        observable_property="prop:second",
                        specification_category=(
                            ObservablePropertySpecificationCategory.derived
                        ),
                    ),
                ],
            )
        )
        container.add(
            ObservableProperty(
                id="prop:first",
                short_name="duplicate_label",
                value_type="string",
            )
        )
        container.add(
            ObservableProperty(
                id="prop:second",
                short_name="duplicate_label",
                value_type="string",
            )
        )
        cache_view = CacheContainerView(container)
        observation = cache_view.require("obs:derived", "Observation")

        specs = adapter.extract_labeled_observable_property_specifications(
            observation,
            cache_view,
            label_collision_strategy="prefix_observable_property_id",
        )

        assert set(specs) == {
            "first__duplicate_label",
            "second__duplicate_label",
        }

    def test_extract_labeled_specs_prefixes_source_dataset(self):
        adapter = self.get_adapter()
        source = DatasetSeries(label="source")
        source.add_empty_dataset("source_one")
        source.add_empty_dataset("source_two")
        source._register_observable_property(
            "src:first", "obs:source", "source_one", "first_value"
        )
        source._register_observable_property(
            "src:second", "obs:source", "source_two", "second_value"
        )
        first_calculation_design = CalculationDesign(
            calculation_implementation=CalculationImplementation(
                function_name="fn",
                function_kwargs=[
                    CalculationKeywordArgument(
                        mapping_name="measurement",
                        contextual_field_reference=ContextualFieldReference(
                            dataset_label="obs:source",
                            field_label="src:first",
                        ),
                    )
                ],
            )
        )
        second_calculation_design = CalculationDesign(
            calculation_implementation=CalculationImplementation(
                function_name="fn",
                function_kwargs=[
                    CalculationKeywordArgument(
                        mapping_name="measurement",
                        contextual_field_reference=ContextualFieldReference(
                            dataset_label="obs:source",
                            field_label="src:second",
                        ),
                    )
                ],
            )
        )

        container = CacheContainerFactory.new()
        container.add(
            Observation(
                id="obs:derived",
                observation_design="design:derived",
            )
        )
        container.add(
            ObservationDesign(
                id="design:derived",
                observable_property_specifications=[
                    ObservablePropertySpecification(
                        observable_property="prop:first",
                        specification_category=(
                            ObservablePropertySpecificationCategory.derived
                        ),
                        calculation_design=first_calculation_design,
                    ),
                    ObservablePropertySpecification(
                        observable_property="prop:second",
                        specification_category=(
                            ObservablePropertySpecificationCategory.derived
                        ),
                        calculation_design=second_calculation_design,
                    ),
                ],
            )
        )
        container.add(
            ObservableProperty(
                id="prop:first",
                short_name="duplicate_label",
                value_type="string",
            )
        )
        container.add(
            ObservableProperty(
                id="prop:second",
                short_name="duplicate_label",
                value_type="string",
            )
        )
        cache_view = CacheContainerView(container)
        observation = cache_view.require("obs:derived", "Observation")

        specs = adapter.extract_labeled_observable_property_specifications(
            observation,
            cache_view,
            label_collision_strategy="prefix_source_dataset",
            source_dataset_series=source,
        )

        assert set(specs) == {
            "source_one__duplicate_label",
            "source_two__duplicate_label",
        }

    def test_extract_labeled_specs_prefixes_split_source_dataset(self):
        adapter = self.get_adapter()
        source = DatasetSeries(label="source")
        source_dataset = source.add_empty_dataset(
            "source_observation",
            metadata={
                SOURCE_FIELDS_BY_OBSERVABLE_PROPERTY_METADATA_KEY: {
                    "src:first": {
                        "dataset_label": "source_one",
                        "element_label": "first_value",
                    },
                    "src:second": {
                        "dataset_label": "source_two",
                        "element_label": "second_value",
                    },
                }
            },
        )
        source_dataset.add_observation_to_index("obs:source")
        source_dataset.add_observable_property(
            observable_property_id="src:first",
            data_type=ObservablePropertyValueType.STRING,
            element_label="first_value",
        )
        source_dataset.add_observable_property(
            observable_property_id="src:second",
            data_type=ObservablePropertyValueType.STRING,
            element_label="second_value",
        )
        source._register_observable_property(
            "src:first", "obs:source", "source_observation", "first_value"
        )
        source._register_observable_property(
            "src:second", "obs:source", "source_observation", "second_value"
        )
        first_calculation_design = CalculationDesign(
            calculation_implementation=CalculationImplementation(
                function_name="fn",
                function_kwargs=[
                    CalculationKeywordArgument(
                        mapping_name="measurement",
                        contextual_field_reference=ContextualFieldReference(
                            dataset_label="obs:source",
                            field_label="src:first",
                        ),
                    )
                ],
            )
        )
        second_calculation_design = CalculationDesign(
            calculation_implementation=CalculationImplementation(
                function_name="fn",
                function_kwargs=[
                    CalculationKeywordArgument(
                        mapping_name="measurement",
                        contextual_field_reference=ContextualFieldReference(
                            dataset_label="obs:source",
                            field_label="src:second",
                        ),
                    )
                ],
            )
        )

        container = CacheContainerFactory.new()
        container.add(
            Observation(
                id="obs:derived",
                observation_design="design:derived",
            )
        )
        container.add(
            ObservationDesign(
                id="design:derived",
                observable_property_specifications=[
                    ObservablePropertySpecification(
                        observable_property="prop:first",
                        specification_category=(
                            ObservablePropertySpecificationCategory.derived
                        ),
                        calculation_design=first_calculation_design,
                    ),
                    ObservablePropertySpecification(
                        observable_property="prop:second",
                        specification_category=(
                            ObservablePropertySpecificationCategory.derived
                        ),
                        calculation_design=second_calculation_design,
                    ),
                ],
            )
        )
        container.add(
            ObservableProperty(
                id="prop:first",
                short_name="duplicate_label",
                value_type="string",
            )
        )
        container.add(
            ObservableProperty(
                id="prop:second",
                short_name="duplicate_label",
                value_type="string",
            )
        )
        cache_view = CacheContainerView(container)
        observation = cache_view.require("obs:derived", "Observation")

        specs = adapter.extract_labeled_observable_property_specifications(
            observation,
            cache_view,
            label_collision_strategy="prefix_source_dataset",
            source_dataset_series=source,
        )

        assert set(specs) == {
            "source_one__duplicate_label",
            "source_two__duplicate_label",
        }

    def test_enrich_after_split_uses_renamed_schema_labels(self):
        import polars as pl
        from pypeh.adapters.enrichment.dataframe_adapter import (
            DataFrameEnrichmentAdapter,
        )

        adapter = DataFrameEnrichmentAdapter()
        source = DatasetSeries(label="source")
        source_one = source.add_empty_dataset("source_one")
        source_two = source.add_empty_dataset("source_two")
        source_one.add_observation_to_index("obs:source")
        source_two.add_observation_to_index("obs:source")

        source_one.add_observable_property(
            observable_property_id="id_prop",
            data_type=ObservablePropertyValueType.STRING,
            element_label="id",
            is_primary_key=True,
        )
        source_one.add_observable_property(
            observable_property_id="src:one",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="value",
        )
        source_two.add_observable_property(
            observable_property_id="source_two_id",
            data_type=ObservablePropertyValueType.STRING,
            element_label="id",
        )
        source_two.add_observable_property(
            observable_property_id="src:two",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="value",
        )
        source_two.schema.add_foreign_key_link(
            element_label="id",
            foreign_key_dataset_label="source_one",
            foreign_key_element_label="id",
        )
        source._register_observable_property(
            "id_prop", "obs:source", "source_one", "id"
        )
        source._register_observable_property(
            "src:one", "obs:source", "source_one", "value"
        )
        source._register_observable_property(
            "src:two", "obs:source", "source_two", "value"
        )
        source_one.data = pl.DataFrame({"id": ["a", "b"], "value": [1.0, 2.0]})
        source_two.data = pl.DataFrame(
            {"id": ["a", "b"], "value": [10.0, 20.0]}
        )

        split = adapter.split_by_observation(source)
        assert split.context_lookup("obs:source", "src:two") == (
            "obs:source",
            "source_two__value",
        )

        container = CacheContainerFactory.new()
        source_observation = Observation(
            id="obs:source",
            observation_design="design:source",
        )
        target_observation = Observation(
            id="obs:derived",
            observation_design="design:derived",
        )
        container.add(source_observation)
        container.add(target_observation)
        calculation_design = CalculationDesign(
            calculation_implementation=CalculationImplementation(
                function_name=(
                    "tests.core.interfaces.dataops.test_dataops.add_one"
                ),
                function_kwargs=[
                    CalculationKeywordArgument(
                        mapping_name="measurement",
                        contextual_field_reference=ContextualFieldReference(
                            dataset_label="obs:source",
                            field_label="src:two",
                        ),
                    )
                ],
            )
        )
        container.add(
            ObservationDesign(
                id="design:source",
                observable_property_specifications=[
                    ObservablePropertySpecification(
                        observable_property="id_prop",
                        specification_category=(
                            ObservablePropertySpecificationCategory.identifying
                        ),
                    ),
                    ObservablePropertySpecification(
                        observable_property="src:one",
                        specification_category=(
                            ObservablePropertySpecificationCategory.optional
                        ),
                    ),
                    ObservablePropertySpecification(
                        observable_property="src:two",
                        specification_category=(
                            ObservablePropertySpecificationCategory.optional
                        ),
                    ),
                ],
            )
        )
        container.add(
            ObservationDesign(
                id="design:derived",
                observable_property_specifications=[
                    ObservablePropertySpecification(
                        observable_property="id_prop",
                        specification_category=(
                            ObservablePropertySpecificationCategory.identifying
                        ),
                    ),
                    ObservablePropertySpecification(
                        observable_property="derived:result",
                        specification_category=(
                            ObservablePropertySpecificationCategory.derived
                        ),
                        calculation_design=calculation_design,
                    ),
                ],
            )
        )
        container.add(
            ObservableProperty(
                id="id_prop",
                short_name="id",
                value_type="string",
            )
        )
        container.add(
            ObservableProperty(
                id="src:one",
                short_name="value",
                value_type="float",
            )
        )
        container.add(
            ObservableProperty(
                id="src:two",
                short_name="value",
                value_type="float",
            )
        )
        container.add(
            ObservableProperty(
                id="derived:result",
                short_name="result",
                value_type="float",
            )
        )

        adapter.enrich(
            source_dataset_series=split,
            target_observations=[target_observation],
            target_derived_from=[source_observation],
            cache_view=CacheContainerView(container),
        )

        enriched = split.parts["obs:source"].data
        assert enriched is not None
        assert enriched["result"].to_list() == [11.0, 21.0]

    def test_extract_from_source_single_source_relabels(self):
        adapter = self.get_adapter()

        source = DatasetSeries(label="extract_single_source")
        source_dataset = source.add_empty_dataset("source")
        source_dataset.add_observation_to_index("obs:src")
        source_dataset.add_observable_property(
            observable_property_id="prop_id",
            data_type=ObservablePropertyValueType.STRING,
            element_label="id",
            is_primary_key=True,
        )
        source_dataset.add_observable_property(
            observable_property_id="prop_value",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="measure",
        )
        source._register_observable_property(
            "prop_id", "obs:src", "source", "id"
        )
        source._register_observable_property(
            "prop_value", "obs:src", "source", "measure"
        )

        left_data, _ = self.mixed_join_and_single_dataset_data()
        source_dataset.data = adapter.subset(
            left_data, element_group=["id", "left_measure"]
        )
        source_dataset.data = adapter.relabel(
            source_dataset.data, {"left_measure": "measure"}
        )

        target = DatasetSeries(label="extract_single_target")
        target_dataset = target.add_empty_dataset("export")
        target_dataset.add_observation_to_index("obs:src")
        target_dataset.add_observable_property(
            observable_property_id="prop_id",
            data_type=ObservablePropertyValueType.STRING,
            element_label="subject_id",
            is_primary_key=True,
        )
        target_dataset.add_observable_property(
            observable_property_id="prop_value",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="measurement",
        )
        target._register_observable_property(
            "prop_id", "obs:src", "export", "subject_id"
        )
        target._register_observable_property(
            "prop_value", "obs:src", "export", "measurement"
        )

        result = adapter.extract_from_source(source=source, target=target)

        assert result is target
        export_dataset = result.parts["export"]
        assert export_dataset.data is not None
        assert sorted(adapter.get_element_labels(export_dataset.data)) == [
            "measurement",
            "subject_id",
        ]
        subject_ids = export_dataset.data.get_column("subject_id").to_list()
        measurements = export_dataset.data.get_column("measurement").to_list()
        assert subject_ids == ["001", "002"]
        assert measurements == [10.0, 20.0]

    def test_extract_from_source_joins_via_source_foreign_key(self):
        adapter = self.get_adapter()

        source = DatasetSeries(label="extract_join_source")
        left_dataset = source.add_empty_dataset("left")
        right_dataset = source.add_empty_dataset("right")
        left_dataset.add_observation_to_index("obs:joined")
        right_dataset.add_observation_to_index("obs:joined")

        left_dataset.add_observable_property(
            observable_property_id="prop_id",
            data_type=ObservablePropertyValueType.STRING,
            element_label="id",
            is_primary_key=True,
        )
        left_dataset.add_observable_property(
            observable_property_id="prop_left_value",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="left_measure",
        )
        right_dataset.add_observable_property(
            observable_property_id="prop_fk_id",
            data_type=ObservablePropertyValueType.STRING,
            element_label="left_id",
        )
        right_dataset.add_observable_property(
            observable_property_id="prop_right_value",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="right_measure",
        )
        right_dataset.schema.add_foreign_key_link(
            element_label="left_id",
            foreign_key_dataset_label="left",
            foreign_key_element_label="id",
        )
        source._register_observable_property(
            "prop_id", "obs:joined", "left", "id"
        )
        source._register_observable_property(
            "prop_left_value", "obs:joined", "left", "left_measure"
        )
        source._register_observable_property(
            "prop_fk_id", "obs:joined", "right", "left_id"
        )
        source._register_observable_property(
            "prop_right_value", "obs:joined", "right", "right_measure"
        )

        left_data, right_data = self.mixed_join_and_single_dataset_data()
        left_dataset.data = adapter.subset(
            left_data, element_group=["id", "left_measure"]
        )
        right_dataset.data = right_data

        target = DatasetSeries(label="extract_join_target")
        target_dataset = target.add_empty_dataset("export")
        target_dataset.add_observation_to_index("obs:joined")
        target_dataset.add_observable_property(
            observable_property_id="prop_left_value",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="left_value",
        )
        target_dataset.add_observable_property(
            observable_property_id="prop_right_value",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="right_value",
        )
        target._register_observable_property(
            "prop_left_value", "obs:joined", "export", "left_value"
        )
        target._register_observable_property(
            "prop_right_value", "obs:joined", "export", "right_value"
        )

        result = adapter.extract_from_source(source=source, target=target)

        export_dataset = result.parts["export"]
        assert export_dataset.data is not None
        assert sorted(adapter.get_element_labels(export_dataset.data)) == [
            "left_value",
            "right_value",
        ]
        left_values = export_dataset.data.get_column("left_value").to_list()
        right_values = export_dataset.data.get_column("right_value").to_list()
        assert left_values == [10.0, 20.0]
        assert right_values == [100.0, 200.0]

    def test_extract_from_source_preserves_right_only_rows(self):
        import polars as pl

        adapter = self.get_adapter()

        source = DatasetSeries(label="extract_outer_join_source")
        left_dataset = source.add_empty_dataset("left")
        right_dataset = source.add_empty_dataset("right")
        left_dataset.add_observation_to_index("obs:joined")
        right_dataset.add_observation_to_index("obs:joined")

        left_dataset.add_observable_property(
            observable_property_id="prop_id",
            data_type=ObservablePropertyValueType.STRING,
            element_label="id",
            is_primary_key=True,
        )
        left_dataset.add_observable_property(
            observable_property_id="prop_left_value",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="left_measure",
        )
        right_dataset.add_observable_property(
            observable_property_id="prop_fk_id",
            data_type=ObservablePropertyValueType.STRING,
            element_label="left_id",
        )
        right_dataset.add_observable_property(
            observable_property_id="prop_right_value",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="right_measure",
        )
        right_dataset.schema.add_foreign_key_link(
            element_label="left_id",
            foreign_key_dataset_label="left",
            foreign_key_element_label="id",
        )
        source._register_observable_property(
            "prop_left_value", "obs:joined", "left", "left_measure"
        )
        source._register_observable_property(
            "prop_right_value", "obs:joined", "right", "right_measure"
        )

        left_data, right_data = self.mixed_join_and_single_dataset_data()
        left_dataset.data = adapter.subset(
            left_data, element_group=["id", "left_measure"]
        )
        right_dataset.data = right_data.vstack(
            pl.DataFrame({"left_id": ["003"], "right_measure": [300.0]})
        )

        target = DatasetSeries(label="extract_outer_join_target")
        target_dataset = target.add_empty_dataset("export")
        target_dataset.add_observation_to_index("obs:joined")
        target_dataset.add_observable_property(
            observable_property_id="prop_left_value",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="left_value",
        )
        target_dataset.add_observable_property(
            observable_property_id="prop_right_value",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="right_value",
        )
        target._register_observable_property(
            "prop_left_value", "obs:joined", "export", "left_value"
        )
        target._register_observable_property(
            "prop_right_value", "obs:joined", "export", "right_value"
        )

        result = adapter.extract_from_source(source=source, target=target)

        export_dataset = result.parts["export"]
        assert export_dataset.data is not None
        sorted_export_data = export_dataset.data.sort("right_value")
        assert sorted_export_data.get_column("left_value").to_list() == [
            10.0,
            20.0,
            None,
        ]
        assert sorted_export_data.get_column("right_value").to_list() == [
            100.0,
            200.0,
            300.0,
        ]

    def test_extract_from_source_collision_raises(self):
        adapter = self.get_adapter()

        source = DatasetSeries(label="extract_collision_source")
        source_dataset = source.add_empty_dataset("source")
        source_dataset.add_observation_to_index("obs:a")
        source_dataset.add_observation_to_index("obs:b")
        source_dataset.add_observable_property(
            observable_property_id="prop_x",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="value",
        )
        # Register two distinct (observation, observable_property) context
        # entries that both resolve to the same source (dataset, element).
        # `_register_observable_property` updates `_context_index` directly
        # without touching the schema, so prop_y need not be a separate
        # schema element on the source side.
        source._register_observable_property(
            "prop_x", "obs:a", "source", "value"
        )
        source._register_observable_property(
            "prop_y", "obs:b", "source", "value"
        )
        left_data, _ = self.mixed_join_and_single_dataset_data()
        source_dataset.data = adapter.subset(
            left_data, element_group=["left_measure"]
        )
        source_dataset.data = adapter.relabel(
            source_dataset.data, {"left_measure": "value"}
        )

        target = DatasetSeries(label="extract_collision_target")
        target_dataset = target.add_empty_dataset("export")
        target_dataset.add_observation_to_index("obs:a")
        target_dataset.add_observation_to_index("obs:b")
        target_dataset.add_observable_property(
            observable_property_id="prop_x",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="value_a",
        )
        target_dataset.add_observable_property(
            observable_property_id="prop_y",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="value_b",
        )
        target._register_observable_property(
            "prop_x", "obs:a", "export", "value_a"
        )
        target._register_observable_property(
            "prop_y", "obs:b", "export", "value_b"
        )

        with pytest.raises(
            ValueError, match="resolve to the same source field"
        ) as exc_info:
            adapter.extract_from_source(source=source, target=target)

        message = str(exc_info.value)
        assert "value_a" in message
        assert "value_b" in message


class TestEnrichment(abc.ABC):
    """Abstract base class for enrichment adapters."""

    __test__ = False

    @abc.abstractmethod
    def get_adapter(self) -> DataOpsProtocol:
        """Return the adapter implementation to test."""
        raise NotImplementedError

    def container(self, path: str) -> CacheContainerView:
        source = get_absolute_path(path)
        container = CacheContainerFactory.new()
        host = DirectoryIO()
        roots = host.load(source, format="yaml", maxdepth=3)
        for root in roots:
            for entity in load_entities_from_tree(root):
                container.add(entity)

        return CacheContainerView(container)

    def raw_data(self):
        raise NotImplementedError

    def raw_dataset_series(
        self, data_import_config_id: str, cache_view: CacheContainerView
    ) -> DatasetSeries:
        data_import_config = cache_view.get(
            data_import_config_id, "DataImportConfig"
        )
        assert isinstance(data_import_config, DataImportConfig)
        return DatasetSeries.from_peh_data_config(
            data_config=data_import_config,
            cache_view=cache_view,
        )

    def test_build_simple_graph(self):
        data_import_config_id = "peh:ENRICHMENT_TEST_IMPORT_CONFIG"
        src_path = "./input/ProcessingExamples/Enrichment_03_MULTI_STEP"
        cache_view = self.container(src_path)
        dataset_series = self.raw_dataset_series(
            data_import_config_id=data_import_config_id, cache_view=cache_view
        )
        adapter = self.get_adapter()

        observations_dict = dataset_series.observations
        observations = []
        for observation_set in observations_dict.values():
            temp = [
                cache_view.get(obs_id, "Observation")
                for obs_id in observation_set
            ]
            observations.extend(temp)
        join_spec_mapping = dataset_series.resolve_all_joins()
        dependency_graph = adapter.build_dependency_graph(
            observations=observations,
            context_index=dataset_series,
            join_spec_mapping=join_spec_mapping,
            cache_view=cache_view,
        )
        assert isinstance(dependency_graph, Graph)
        ret = adapter.compile_dependency_graph(
            dependency_graph=dependency_graph
        )
        assert isinstance(ret, ExecutionPlan)

    def test_dependency_graph_compilation(self):
        data_import_config_id = "peh:ENRICHMENT_TEST_IMPORT_CONFIG"
        src_path = "./input/ProcessingExamples/Enrichment_03_MULTI_STEP"
        cache_view = self.container(src_path)
        dataset_series = self.raw_dataset_series(
            data_import_config_id=data_import_config_id, cache_view=cache_view
        )
        adapter = self.get_adapter()
        assert isinstance(adapter, DataOpsInterface)
        datasets = self.raw_data()
        for dataset_label, dataset in datasets.items():
            data_labels = adapter.get_element_labels(dataset)
            dataset_series.add_data(
                dataset_label=dataset_label,
                data=dataset,
                data_labels=data_labels,
            )
        _ = adapter.enrich(
            source_dataset_series=dataset_series,
            target_observations=[
                cache_view.get(
                    "peh:ENRICHMENT_TEST_OBSERVATION_SUBJECT_ENRICHED",
                    "Observation",
                )
            ],
            target_derived_from=[
                cache_view.get(
                    "peh:ENRICHMENT_TEST_OBSERVATION_SUBJECT_ENRICHED_BASE",
                    "Observation",
                )
            ],
            cache_view=cache_view,
        )

        enriched_data = {}
        for dataset_label in dataset_series:
            dataset = dataset_series[dataset_label]
            assert dataset is not None
            raw_data = dataset.data
            enriched_data[dataset_label] = raw_data
            dataset_element_labels = dataset.get_element_labels()
            for element_label in dataset_element_labels:
                values = adapter.get_element_values(
                    raw_data, element_label=element_label, as_list=True
                )
                assert len(values) > 0
        assert adapter.matches_schema(enriched_data, dataset_series)


@pytest.mark.dataframe
class TestDataFrameDataOps(
    TestValidation, TestDataImport, TestDatasetSeriesMods
):
    __test__ = True

    def get_adapter(self) -> DataOpsProtocol:
        dfops = importlib.import_module(
            "pypeh.adapters.validation.pandera_adapter.validation_adapter"
        )
        return dfops.DataFrameValidationAdapter()  # type: ignore

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
                {
                    "id_subject": "001",
                    "matrix": "urine",
                    "crt": 1.2,
                    "crt_lod": 0.1,
                    "crt_loq": 0.2,
                    "sg": 1.015,
                },
                {
                    "id_subject": "002",
                    "matrix": "urine",
                    "crt": 1.5,
                    "crt_lod": 0.1,
                    "crt_loq": 0.2,
                    "sg": 1.020,
                },
            ]
        )

        layout["analyticalinfo"] = pl.DataFrame(
            [
                {
                    "id_subject": "001",
                    "biomarkercode": "B001",
                    "matrix": "urine",
                    "labinstitution": "LabCorp",
                },
                {
                    "id_subject": "002",
                    "biomarkercode": "B002",
                    "matrix": "urine",
                    "labinstitution": "Quest Diagnostics",
                },
            ]
        )

        return layout

    def mixed_join_and_single_dataset_data(self):
        import polars as pl

        left_data = pl.DataFrame(
            {
                "id": ["001", "002"],
                "left_measure": [10.0, 20.0],
                "left_other_measure": [7.0, 8.0],
            }
        )
        right_data = pl.DataFrame(
            {"left_id": ["001", "002"], "right_measure": [100.0, 200.0]}
        )
        return (left_data, right_data)

    def verify_join_and_single_dataset(
        self, split_series: DatasetSeries, adapter: DataOpsProtocol
    ):
        obs1_dataset_label, obs1_right_label = split_series.context_lookup(
            "obs:1", "obs1_right_prop"
        )
        assert obs1_dataset_label == "obs:1"
        obs1_data = split_series.parts["obs:1"].data
        assert obs1_data is not None
        assert obs1_data.width == 3
        assert obs1_data.get_column(obs1_right_label).to_list() == [
            100.0,
            200.0,
        ]

        obs2_dataset_label, obs2_left_label = split_series.context_lookup(
            "obs:2", "obs2_left_prop"
        )
        assert obs2_dataset_label == "obs:2"
        obs2_data = split_series.parts["obs:2"].data
        assert obs2_data is not None
        assert obs2_data.width == 2
        assert obs2_data.get_column(obs2_left_label).to_list() == [7.0, 8.0]
        split_series_data = {}
        for dataset_label in split_series.parts:
            dataset = split_series[dataset_label]
            assert dataset is not None
            split_series_data[dataset_label] = dataset.data
        assert adapter.matches_schema(split_series_data, split_series)


@pytest.mark.dataframe
class TestDataFrameEnrichment(TestEnrichment):
    __test__ = True

    def get_adapter(self) -> DataOpsProtocol:
        dfops = importlib.import_module(
            "pypeh.adapters.enrichment.dataframe_adapter"
        )
        return dfops.DataFrameEnrichmentAdapter()  # type: ignore

    def raw_data(self) -> dict:
        import polars as pl

        df_ingested = pl.DataFrame(
            {
                "id_subject": [1, 2, 3, 4, 5],
                "current_year": [2025, 2025, 2025, 2025, 2025],
                "current_month": [12, 12, 12, 12, 12],
                "current_day": [11, 11, 11, 11, 11],
                "N1Birthdate": [
                    date(1990, 5, 21),
                    date(1985, 7, 14),
                    date(2000, 1, 3),
                    date(1995, 9, 30),
                    date(1988, 3, 12),
                ],
            }
        )

        df_enriched = pl.DataFrame(
            {
                "id_subject": [1, 2, 3, 4, 5],
                "N2Birthweight": [3.2, 2.8, 3.5, 4.0, 3.0],
            }
        )

        return {
            "SUBJECTUNIQUE": df_ingested,
            "ENRICH_BASE": df_enriched,
        }

    def test_type_mapper_distinguishes_date_and_datetime(self):
        import polars as pl

        adapter = self.get_adapter()

        assert adapter.type_mapper("date") is pl.Date
        assert adapter.type_mapper("datetime") is pl.Datetime


@pytest.mark.other
class TestUnknownDataOps(TestValidation):
    def get_adapter(self) -> DataOpsProtocol:
        raise NotImplementedError


class TestAggregation(abc.ABC):
    """Abstract base class for Aggregation adapters."""

    __test__ = False

    @abc.abstractmethod
    def get_adapter(self) -> DataOpsProtocol:
        """Return the adapter implementation to test."""
        raise NotImplementedError

    def container(self, path: str) -> CacheContainerView:
        source = get_absolute_path(path)
        container = CacheContainerFactory.new()
        host = DirectoryIO()
        roots = host.load(source, format="yaml", maxdepth=3)
        for root in roots:
            for entity in load_entities_from_tree(root):
                container.add(entity)

        return CacheContainerView(container)

    def raw_data(self):
        raise NotImplementedError

    def raw_dataset_series(
        self, data_import_config_id: str, cache_view: CacheContainerView
    ) -> DatasetSeries:
        data_import_config = cache_view.get(
            data_import_config_id, "DataImportConfig"
        )
        assert isinstance(data_import_config, DataImportConfig)
        return DatasetSeries.from_peh_data_config(
            data_config=data_import_config,
            cache_view=cache_view,
        )

    def test_summarize(self):
        data_import_config_id = "peh:ENRICHMENT_TEST_IMPORT_CONFIG"
        src_path = "./input/AggregationExamples/Aggregation"
        cache_view = self.container(src_path)
        dataset_series = self.raw_dataset_series(
            data_import_config_id=data_import_config_id, cache_view=cache_view
        )
        adapter = self.get_adapter()
        assert isinstance(adapter, DataOpsInterface)
        datasets = self.raw_data()
        for dataset_label, dataset in datasets.items():
            data_labels = adapter.get_element_labels(dataset)
            dataset_series.add_data(
                dataset_label=dataset_label,
                data=dataset,
                data_labels=data_labels,
            )
        target_observations = []
        target_derived_from = []
        for target_obs_id, derived_from_obs_id in [
            (
                "peh:TEST_SUMMARY",
                "peh:ENRICHMENT_TEST_OBSERVATION_SUBJECTUNIQUE_INGESTED",
            ),
            (
                "peh:TEST_SUMMARY2",
                "peh:ENRICHMENT_TEST_OBSERVATION_SUBJECT_ENRICHED_BASE",
            ),
        ]:
            target_observation = cache_view.get(target_obs_id, "Observation")
            assert target_observation is not None
            target_observations.append(target_observation)
            derived_from_observation = cache_view.get(
                derived_from_obs_id, "Observation"
            )
            assert derived_from_observation is not None
            target_derived_from.append(derived_from_observation)

        ret = adapter.summarize(
            source_dataset_series=dataset_series,
            target_observations=target_observations,
            target_derived_from=target_derived_from,
            cache_view=cache_view,
        )
        assert isinstance(ret, DatasetSeries)
        assert len(ret.parts) == 2

        expected_shape_dict = {"TEST_SUMMARY": (2, 5), "TEST_SUMMARY2": (2, 3)}
        expected_labels_dict = {
            "TEST_SUMMARY": {
                "current_year",
                "current_month",
                "mean_birthweight",
                "sem_birthweight",
                "mean_birthlength",
            },
            "TEST_SUMMARY2": {
                "current_year",
                "current_month",
                "mean_birthweight2",
            },
        }

        for result_label, expected_shape in expected_shape_dict.items():
            result_dataset = ret[result_label]
            assert result_dataset is not None
            assert result_dataset.data.shape == expected_shape
            # function function_kwarg.mapping_name is used as column name for the result of the stat builder, so we check that it is present in the resulting dataset, along with the stratification columns
            observed_labels = set(
                adapter.get_element_labels(result_dataset.data)
            )
            assert observed_labels == expected_labels_dict[result_label]

        summary = ret["TEST_SUMMARY"]
        assert summary is not None
        summary_data = summary.data.sort("current_year")

        assert summary_data["mean_birthweight"].to_list() == pytest.approx(
            [150.0, 400.0]
        )
        mean_birthlength = summary_data["mean_birthlength"].to_list()
        assert mean_birthlength[0] is None
        assert mean_birthlength[1] == pytest.approx((50 + 45 + 54) / 3)

    def test_summarize_prefixes_colliding_target_labels(self):
        import polars as pl

        adapter = self.get_adapter()
        source = DatasetSeries(label="source")
        source_dataset = source.add_empty_dataset("source_dataset")
        source_dataset.add_observation_to_index("obs:source")
        source_dataset.add_observable_property(
            observable_property_id="src:measure",
            data_type=ObservablePropertyValueType.FLOAT,
            element_label="measure",
        )
        source._register_observable_property(
            "src:measure", "obs:source", "source_dataset", "measure"
        )
        source_dataset.data = pl.DataFrame({"measure": [1.0, 2.0, 3.0]})

        container = CacheContainerFactory.new()
        source_observation = Observation(
            id="obs:source",
            observation_design="design:source",
        )
        target_observation = Observation(
            id="obs:summary",
            ui_label="summary",
            observation_design="design:summary",
        )
        container.add(source_observation)
        container.add(target_observation)
        calculation_design = CalculationDesign(
            calculation_implementation=CalculationImplementation(
                function_name=(
                    "pypeh.adapters.aggregation.polars_adapter.statistics."
                    "statistics_count_n"
                ),
                function_kwargs=[
                    CalculationKeywordArgument(
                        contextual_field_reference=ContextualFieldReference(
                            dataset_label="obs:source",
                            field_label="src:measure",
                        )
                    )
                ],
            )
        )
        container.add(
            ObservationDesign(
                id="design:source",
                observable_property_specifications=[
                    ObservablePropertySpecification(
                        observable_property="src:measure",
                        specification_category=(
                            ObservablePropertySpecificationCategory.optional
                        ),
                    ),
                ],
            )
        )
        container.add(
            ObservationDesign(
                id="design:summary",
                observable_property_specifications=[
                    ObservablePropertySpecification(
                        observable_property="target:count_one",
                        specification_category=(
                            ObservablePropertySpecificationCategory.derived
                        ),
                        calculation_design=calculation_design,
                    ),
                    ObservablePropertySpecification(
                        observable_property="target:count_two",
                        specification_category=(
                            ObservablePropertySpecificationCategory.derived
                        ),
                        calculation_design=calculation_design,
                    ),
                ],
            )
        )
        container.add(
            ObservableProperty(
                id="src:measure",
                short_name="measure",
                value_type="float",
            )
        )
        container.add(
            ObservableProperty(
                id="target:count_one",
                short_name="count",
                ui_label="count",
                value_type="integer",
            )
        )
        container.add(
            ObservableProperty(
                id="target:count_two",
                short_name="count",
                ui_label="count",
                value_type="integer",
            )
        )

        result = adapter.summarize(
            source_dataset_series=source,
            target_observations=[target_observation],
            target_derived_from=[source_observation],
            cache_view=CacheContainerView(container),
            target_label_collision_strategy="prefix_observable_property_id",
        )

        summary = result["summary"]
        assert summary is not None
        assert set(summary.get_element_labels()) == {
            "count_one__count",
            "count_two__count",
        }
        assert summary.data["count_one__count"].to_list() == [3]
        assert summary.data["count_two__count"].to_list() == [3]


@pytest.mark.dataframe
class TestDataFrameAggregation(TestAggregation):
    __test__ = True

    def get_adapter(self) -> DataOpsProtocol:
        dfops = importlib.import_module(
            "pypeh.adapters.aggregation.polars_adapter.dataframe_adapter"
        )
        return dfops.DataFrameAggregationAdapter()  # type: ignore

    def raw_data(self) -> dict:
        import polars as pl

        df_ingested = pl.DataFrame(
            {
                "id_subject": [1, 2, 3, 4, 5],
                "current_year": [2024, 2024, 2025, 2025, 2025],
                "current_month": [12, 12, 12, 12, 12],
                "N1BirthWeight": [
                    100,
                    200,
                    300,
                    400,
                    500,
                ],
                "N1BirthLength": [
                    40,
                    None,
                    50,
                    45,
                    54,
                ],
            }
        )

        df_enriched = pl.DataFrame(
            {
                "id_subject": [1, 2, 3, 4, 5],
                "current_year": [2024, 2024, 2025, 2025, 2025],
                "current_month": [12, 12, 12, 12, 12],
                "N2BirthWeight": [3.2, 2.8, 3.5, 4.0, 3.0],
            }
        )

        return {
            "SUBJECTUNIQUE": df_ingested,
            "ENRICH_BASE": df_enriched,
        }


class DataExtractProtocol(Protocol, Generic[T_DataType]):
    data_format: T_DataType

    def _filter(
        self, data: T_DataType, config: FilterConfig
    ) -> T_DataType: ...

    def build_filter_config(
        self, filter_expression, dataset_label, type_annotations
    ) -> FilterConfig: ...

    def apply_filter(
        self,
        reshaped_dataset_series,
        filter_expression,
        dataset_label,
        source_dataset_series=None,
    ) -> DatasetSeries[T_DataType]: ...

    def extract_from_source(
        self, source, target
    ) -> DatasetSeries[T_DataType]: ...

    def execute_join_plan(self, base_data, datasets, join_plan): ...


class TestDataExtract(abc.ABC):
    """Abstract base class for testing extract adapters."""

    __test__ = False

    @abc.abstractmethod
    def get_adapter(self) -> DataExtractProtocol:
        raise NotImplementedError

    def test_getting_default_adapter_from_interface(self):
        adapter_class = DataExtractInterface.get_default_adapter_class()
        adapter = adapter_class()
        assert isinstance(adapter, DataExtractInterface)
        assert isinstance(adapter, type(self.get_adapter()))

    def test_build_filter_config_from_observation_filter_expression(self):
        adapter = self.get_adapter()

        obs_filter = FilterExpression(
            filter_command="is_in",
            filter_subject_contextual_field_references=[
                ContextualFieldReference(
                    field_label="country", dataset_label="D1"
                )
            ],
            filter_arg_values=["BE", "BR"],
        )
        type_annotations = {
            "D1": {"country": ObservablePropertyValueType.STRING}
        }

        result = adapter.build_filter_config(
            filter_expression=obs_filter,
            dataset_label="D1",
            type_annotations=type_annotations,
        )

        assert isinstance(result, FilterConfig)
        assert result.filter_expression.command == "is_in"
        assert result.filter_expression.subject == ["country"]
        assert result.filter_expression.arg_values == ["BE", "BR"]

    def test_apply_filter_filters_base_dataset(self):
        import polars as pl

        adapter = self.get_adapter()

        obs_filter = FilterExpression(
            filter_command="is_in",
            filter_subject_contextual_field_references=[
                ContextualFieldReference(
                    field_label="country", dataset_label="D1"
                )
            ],
            filter_arg_values=["BE", "BR"],
        )

        reshaped = DatasetSeries(label="reshaped")
        base_dataset = reshaped.add_empty_dataset("D1")
        base_dataset.schema.add_observable_property(
            "peh:country",
            ObservablePropertyValueType.STRING,
            element_label="country",
        )
        base_dataset.data = pl.DataFrame({"country": ["BE", "BR", "NL"]})

        result = adapter.apply_filter(
            reshaped_dataset_series=reshaped,
            filter_expression=obs_filter,
            dataset_label="D1",
        )

        # the filtered frame is written back and the same series is returned
        assert result is reshaped
        assert reshaped.parts["D1"].data["country"].to_list() == ["BE", "BR"]

    def test_apply_filter_joins_dependencies(self):
        import polars as pl

        adapter = self.get_adapter()

        obs_filter = FilterExpression(
            filter_command="is_in",
            filter_subject_contextual_field_references=[
                ContextualFieldReference(
                    field_label="country", dataset_label="D2"
                )
            ],
            filter_arg_values=["BE", "BR"],
        )

        # Real DatasetSeries with a foreign key from D1 -> D2 so the
        # interface can resolve the cross-dataset filter join.
        reshaped = DatasetSeries(label="reshaped")
        base_dataset = reshaped.add_empty_dataset("D1")
        base_dataset.schema.add_observable_property(
            "peh:id_d1", ObservablePropertyValueType.STRING, element_label="id"
        )
        base_dataset.schema.add_foreign_key_link(
            element_label="id",
            foreign_key_dataset_label="D2",
            foreign_key_element_label="id",
        )
        base_dataset.data = pl.DataFrame({"id": [1, 2, 3]})
        dependent_dataset = reshaped.add_empty_dataset("D2")
        dependent_dataset.schema.add_observable_property(
            "peh:id_d2", ObservablePropertyValueType.STRING, element_label="id"
        )
        dependent_dataset.schema.add_observable_property(
            "peh:country",
            ObservablePropertyValueType.STRING,
            element_label="country",
        )
        dependent_dataset.data = pl.DataFrame(
            {"id": [1, 2, 3], "country": ["BE", "BR", "NL"]}
        )

        filter_config = adapter.build_filter_config(
            filter_expression=obs_filter,
            dataset_label="D1",
            type_annotations=reshaped.get_type_annotations(),
        )
        assert filter_config.dependent_contextual_field_references.get("D2")

        result = adapter.apply_filter(
            reshaped_dataset_series=reshaped,
            filter_expression=obs_filter,
            dataset_label="D1",
        )

        # D1 rows are kept only where the joined D2.country is in [BE, BR]
        assert result is reshaped
        assert reshaped.parts["D1"].data["id"].to_list() == [1, 2]

    def test_apply_filter_join_does_not_leak_dependency_columns(self):
        import polars as pl

        adapter = self.get_adapter()

        # Same cross-dataset setup as `test_apply_filter_joins_dependencies`,
        # but here we assert the *shape* of the result. The join pulls D2's
        # `country` column into the frame that is filtered; the reshaped base
        # dataset must only retain its own schema columns afterwards.
        obs_filter = FilterExpression(
            filter_command="is_in",
            filter_subject_contextual_field_references=[
                ContextualFieldReference(
                    field_label="country", dataset_label="D2"
                )
            ],
            filter_arg_values=["BE", "BR"],
        )

        reshaped = DatasetSeries(label="reshaped")
        base_dataset = reshaped.add_empty_dataset("D1")
        base_dataset.schema.add_observable_property(
            "peh:id_d1", ObservablePropertyValueType.STRING, element_label="id"
        )
        base_dataset.schema.add_foreign_key_link(
            element_label="id",
            foreign_key_dataset_label="D2",
            foreign_key_element_label="id",
        )
        base_dataset.data = pl.DataFrame({"id": [1, 2, 3]})
        dependent_dataset = reshaped.add_empty_dataset("D2")
        dependent_dataset.schema.add_observable_property(
            "peh:id_d2", ObservablePropertyValueType.STRING, element_label="id"
        )
        dependent_dataset.schema.add_observable_property(
            "peh:country",
            ObservablePropertyValueType.STRING,
            element_label="country",
        )
        dependent_dataset.data = pl.DataFrame(
            {"id": [1, 2, 3], "country": ["BE", "BR", "NL"]}
        )

        result = adapter.apply_filter(
            reshaped_dataset_series=reshaped,
            filter_expression=obs_filter,
            dataset_label="D1",
        )

        # The filtered base dataset keeps only its own schema columns; the
        # joined-in `country` column from D2 must not appear.
        assert result is reshaped
        assert reshaped.parts["D1"].data.columns == ["id"]
        assert set(reshaped.parts["D1"].data.columns) == set(
            reshaped.parts["D1"].get_element_labels()
        )
        assert reshaped.parts["D1"].data["id"].to_list() == [1, 2]

    def test_apply_filter_falls_back_to_source_series(self):
        import polars as pl

        adapter = self.get_adapter()

        # Export a single non-identifying column (measurement) but filter on a
        # condition column (status) that lives in a section which was NOT
        # extracted into the reshaped series. The condition column is only
        # reachable through the pre-extraction source series.
        obs_filter = FilterExpression(
            filter_command="is_in",
            filter_subject_contextual_field_references=[
                ContextualFieldReference(
                    field_label="status", dataset_label="D2"
                )
            ],
            filter_arg_values=["ok"],
        )

        # reshaped series only holds D1 with its foreign key and the single
        # non-identifying output column; D2 was projected away by extraction.
        reshaped = DatasetSeries(label="reshaped")
        base_dataset = reshaped.add_empty_dataset("D1")
        base_dataset.schema.add_observable_property(
            "peh:id_d1", ObservablePropertyValueType.STRING, element_label="id"
        )
        base_dataset.schema.add_foreign_key_link(
            element_label="id",
            foreign_key_dataset_label="D2",
            foreign_key_element_label="id",
        )
        base_dataset.schema.add_observable_property(
            "peh:measurement",
            ObservablePropertyValueType.INTEGER,
            element_label="measurement",
        )
        base_dataset.data = pl.DataFrame(
            {"id": [1, 2, 3], "measurement": [10, 20, 30]}
        )

        # source series still holds the condition column in D2.
        source = DatasetSeries(label="source")
        source_d2 = source.add_empty_dataset("D2")
        source_d2.schema.add_observable_property(
            "peh:id_d2", ObservablePropertyValueType.STRING, element_label="id"
        )
        source_d2.schema.add_observable_property(
            "peh:status",
            ObservablePropertyValueType.STRING,
            element_label="status",
        )
        source_d2.data = pl.DataFrame(
            {"id": [1, 2, 3], "status": ["ok", "bad", "ok"]}
        )

        result = adapter.apply_filter(
            reshaped_dataset_series=reshaped,
            filter_expression=obs_filter,
            dataset_label="D1",
            source_dataset_series=source,
        )

        # Rows survive only where the source D2.status is "ok" (ids 1 and 3).
        assert result is reshaped
        assert reshaped.parts["D1"].data["measurement"].to_list() == [10, 30]

    def test_apply_filter_missing_dependency_without_source_raises(self):
        import polars as pl

        adapter = self.get_adapter()

        obs_filter = FilterExpression(
            filter_command="is_in",
            filter_subject_contextual_field_references=[
                ContextualFieldReference(
                    field_label="status", dataset_label="D2"
                )
            ],
            filter_arg_values=["ok"],
        )

        reshaped = DatasetSeries(label="reshaped")
        base_dataset = reshaped.add_empty_dataset("D1")
        base_dataset.schema.add_observable_property(
            "peh:id_d1", ObservablePropertyValueType.STRING, element_label="id"
        )
        base_dataset.schema.add_foreign_key_link(
            element_label="id",
            foreign_key_dataset_label="D2",
            foreign_key_element_label="id",
        )
        base_dataset.data = pl.DataFrame({"id": [1, 2, 3]})

        # D2 exists as a part so its type annotation resolves, but it was never
        # populated with data and no source fallback is provided.
        dependent_dataset = reshaped.add_empty_dataset("D2")
        dependent_dataset.schema.add_observable_property(
            "peh:id_d2", ObservablePropertyValueType.STRING, element_label="id"
        )
        dependent_dataset.schema.add_observable_property(
            "peh:status",
            ObservablePropertyValueType.STRING,
            element_label="status",
        )

        with pytest.raises(ValueError, match="not available"):
            adapter.apply_filter(
                reshaped_dataset_series=reshaped,
                filter_expression=obs_filter,
                dataset_label="D1",
            )

    def test_apply_filter_rejects_filter_output_that_breaks_schema(self):
        import polars as pl

        # `apply_filter` writes the filter result back through `add_data`,
        # passing the *actual* columns of the filtered frame as `data_labels`.
        # `add_data` verifies those labels against the dataset schema, so an
        # adapter whose `_filter` returns a column that is not part of the
        # base schema is rejected.
        adapter = self.get_adapter()

        class LeakyFilterAdapter(type(adapter)):
            def _filter(self, data, config):
                # Ignore the schema-derived projection and leak an extra,
                # unschemaed column into the result.
                filtered = super()._filter(data, config)
                return filtered.with_columns(pl.lit("x").alias("unexpected"))

        leaky_adapter = LeakyFilterAdapter()

        obs_filter = FilterExpression(
            filter_command="is_in",
            filter_subject_contextual_field_references=[
                ContextualFieldReference(
                    field_label="country", dataset_label="D1"
                )
            ],
            filter_arg_values=["BE", "BR"],
        )

        reshaped = DatasetSeries(label="reshaped")
        base_dataset = reshaped.add_empty_dataset("D1")
        base_dataset.schema.add_observable_property(
            "peh:country",
            ObservablePropertyValueType.STRING,
            element_label="country",
        )
        base_dataset.data = pl.DataFrame({"country": ["BE", "BR", "NL"]})

        with pytest.raises(DatasetSchemaError):
            leaky_adapter.apply_filter(
                reshaped_dataset_series=reshaped,
                filter_expression=obs_filter,
                dataset_label="D1",
            )


@pytest.mark.dataframe
class TestDataFrameExtract(TestDataExtract):
    __test__ = True

    def get_adapter(self) -> DataExtractProtocol:
        dfops = importlib.import_module(
            "pypeh.adapters.extract.dataframe_adapter"
        )
        return dfops.DataFrameExtractAdapter()  # type: ignore
