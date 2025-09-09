import pytest
import abc

from typing import Protocol, Any, Generic
from peh_model.peh import DataLayout

from pypeh.core.interfaces.outbound.dataops import T_DataType, ValidationInterface
from pypeh.core.models.validation_errors import ValidationErrorReport
from pypeh.core.models.constants import ValidationErrorLevel
from pypeh.core.models.validation_dto import (
    ValidationExpression,
    ValidationDesign,
    ColumnValidation,
    ValidationConfig,
)
from pypeh.core.models.settings import LocalFileSettings
from tests.test_utils.dirutils import get_absolute_path


class DataOpsProtocol(Protocol, Generic[T_DataType]):
    data_format: T_DataType

    def validate(self, data, config) -> ValidationErrorReport: ...

    def import_data(self, source, config) -> Any: ...

    def import_data_layout(self, source, config) -> Any: ...


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
                        ValidationErrorLevel.ERROR: 0,
                        ValidationErrorLevel.FATAL: 1,
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
                            data_type="decimal",
                            required=True,
                            nullable=False,
                            # decimals_precision
                            validations=[
                                ValidationDesign(
                                    name="fn",
                                    error_level=ValidationErrorLevel.ERROR,
                                    expression=ValidationExpression(
                                        command="decimals_precision",
                                        arg_values=["3"],
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

        adapter.cleanup()

    @pytest.mark.parametrize(
        "config, data, expected_output",
        [
            # data type error
            (
                ValidationConfig(
                    name="data type error",
                    columns=[
                        ColumnValidation(
                            unique_name="col1",
                            data_type="not a type",
                            required=True,
                            nullable=False,
                            validations=[],
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
                    "len_unexpected": 2,
                },
            ),
            # ValidationDesign Error
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
                            name="conditional",
                            error_level=ValidationErrorLevel.ERROR,
                            expression=ValidationExpression(
                                conditional_expression=ValidationExpression(
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
                                command="is_in",
                                arg_values=["a", "b", "c"],
                            ),
                        )
                    ],
                ),
                {
                    "col1": [3, 1],
                    "col2": [1, 2],
                },
                {
                    "len_unexpected": 2,
                },
            ),
        ],
    )
    def test_validate_unexpected_errors(self, config, data, expected_output):
        adapter = self.get_adapter()
        result = adapter._validate(data, config)

        assert result is not None
        assert len(result.unexpected_errors) == expected_output.get("len_unexpected")

        adapter.cleanup()


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


@pytest.mark.dataframe
class TestDataFrameDataOps(TestValidation, TestDataImport):
    def get_adapter(self) -> DataOpsProtocol:
        try:
            from pypeh.adapters.outbound.validation.pandera_adapter import dataops as dfops

            return dfops.DataFrameAdapter()
        except ImportError:
            pytest.skip("Necessary modules not installed")


@pytest.mark.other
class TestUnknownDataOps(TestValidation):
    def get_adapter(self) -> DataOpsProtocol:
        raise NotImplementedError
