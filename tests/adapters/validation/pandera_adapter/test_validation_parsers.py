import pytest

from copy import deepcopy

from pypeh.adapters.persistence.hosts import DirectoryIO
from pypeh.adapters.validation.pandera_adapter.parsers import (
    parse_validation_expression,
    parse_columns,
    parse_config,
)

from pypeh.core.models.validation_dto import (
    ValidationExpression,
    ValidationDesign,
    ColumnValidation,
    ValidationConfig,
)
from pypeh.core.interfaces.dataops import ValidationInterface
from pypeh.core.models.constants import ValidationErrorLevel
from pypeh.core.models.internal_data_layout import (
    Dataset,
    DatasetSchema,
    DatasetSchemaElement,
    ObservablePropertyValueType,
)
from pypeh.core.cache.containers import (
    CacheContainerFactory,
    CacheContainerView,
)
from pypeh.core.cache.utils import load_entities_from_tree

from tests.test_utils.dirutils import get_absolute_path


@pytest.mark.dataframe
class TestPydanticToDto:
    @pytest.mark.parametrize(
        "input_data, expected_output",
        [
            (
                ValidationExpression(
                    command="is_greater_than",
                    arg_columns=["col1"],
                ),
                {
                    "command": "is_greater_than",
                    "arg_values": None,
                    "subject": None,
                    "arg_columns": ["col1"],
                },
            ),
            (
                ValidationExpression(
                    command="conjunction",
                    arg_expressions=[
                        ValidationExpression(
                            command="is_greater_than",
                            arg_columns=["col1"],
                        ),
                        ValidationExpression(
                            command="is_less_than",
                            arg_columns=["col2"],
                        ),
                    ],
                ),
                {
                    "check_case": "conjunction",
                    "expressions": [
                        {
                            "command": "is_greater_than",
                            "arg_values": None,
                            "subject": None,
                            "arg_columns": ["col1"],
                        },
                        {
                            "command": "is_less_than",
                            "arg_values": None,
                            "subject": None,
                            "arg_columns": ["col2"],
                        },
                    ],
                },
            ),
            (
                ValidationExpression(
                    command="disjunction",
                    arg_expressions=[
                        ValidationExpression(
                            command="is_greater_than",
                            arg_columns=["col1"],
                        ),
                        ValidationExpression(
                            command="is_less_than",
                            subject=["col2"],
                            arg_values=[10],
                        ),
                    ],
                ),
                {
                    "check_case": "disjunction",
                    "expressions": [
                        {
                            "command": "is_greater_than",
                            "arg_values": None,
                            "subject": None,
                            "arg_columns": ["col1"],
                        },
                        {
                            "command": "is_less_than",
                            "arg_values": [10],
                            "subject": ["col2"],
                            "arg_columns": None,
                        },
                    ],
                },
            ),
            (
                ValidationExpression(
                    conditional_expression=ValidationExpression(
                        command="disjunction",
                        arg_expressions=[
                            ValidationExpression(
                                command="is_greater_than",
                                arg_columns=["col1"],
                            ),
                            ValidationExpression(
                                command="is_less_than",
                                subject=["col2"],
                                arg_values=[10],
                            ),
                        ],
                    ),
                    command="is_equal_to",
                    arg_values=[5],
                ),
                {
                    "check_case": "condition",
                    "expressions": [
                        {
                            "check_case": "disjunction",
                            "expressions": [
                                {
                                    "command": "is_greater_than",
                                    "arg_values": None,
                                    "subject": None,
                                    "arg_columns": ["col1"],
                                },
                                {
                                    "command": "is_less_than",
                                    "arg_values": [10],
                                    "subject": ["col2"],
                                    "arg_columns": None,
                                },
                            ],
                        },
                        {
                            "command": "is_equal_to",
                            "arg_values": [5],
                            "subject": None,
                            "arg_columns": None,
                        },
                    ],
                },
            ),
        ],
    )
    def test_parse_validation_expression(self, input_data, expected_output):
        result = parse_validation_expression(input_data)
        assert result == expected_output

    @pytest.mark.parametrize("command", ["conjunction", "disjunction"])
    @pytest.mark.parametrize("operand_count", [3, 4])
    def test_parse_multiple_validation_expressions(
        self, command, operand_count
    ):
        expressions = [
            ValidationExpression(
                command="is_equal_to",
                arg_values=[value],
            )
            for value in range(operand_count)
        ]

        result = parse_validation_expression(
            ValidationExpression(
                command=command,
                arg_expressions=expressions,
            )
        )

        assert result == {
            "check_case": command,
            "expressions": [
                {
                    "command": "is_equal_to",
                    "arg_values": [value],
                    "arg_columns": None,
                    "subject": None,
                }
                for value in range(operand_count)
            ],
        }

    def test_parse_nested_multiple_validation_expressions(self):
        nested_expression = ValidationExpression(
            command="disjunction",
            arg_expressions=[
                ValidationExpression(
                    command="is_equal_to",
                    arg_values=[value],
                )
                for value in range(3)
            ],
        )
        expression = ValidationExpression(
            command="conjunction",
            arg_expressions=[
                nested_expression,
                ValidationExpression(
                    command="is_greater_than",
                    arg_values=[10],
                ),
            ],
        )

        result = parse_validation_expression(expression)

        assert result == {
            "check_case": "conjunction",
            "expressions": [
                {
                    "check_case": "disjunction",
                    "expressions": [
                        {
                            "command": "is_equal_to",
                            "arg_values": [value],
                            "arg_columns": None,
                            "subject": None,
                        }
                        for value in range(3)
                    ],
                },
                {
                    "command": "is_greater_than",
                    "arg_values": [10],
                    "arg_columns": None,
                    "subject": None,
                },
            ],
        }

    def test_parse_conditional_multiple_disjunction_operands(self):
        expression = ValidationExpression(
            conditional_expression=ValidationExpression(
                command="is_not_null",
                arg_columns=["chol"],
            ),
            command="disjunction",
            arg_expressions=[
                ValidationExpression(
                    command="is_less_than",
                    arg_values=[2.5],
                ),
                ValidationExpression(
                    command="is_equal_to",
                    arg_values=[-1],
                ),
                ValidationExpression(
                    command="is_equal_to",
                    arg_values=[-2],
                ),
                ValidationExpression(
                    command="is_equal_to",
                    arg_values=[-10],
                ),
            ],
        )

        result = parse_validation_expression(expression)

        assert result == {
            "check_case": "condition",
            "expressions": [
                {
                    "command": "is_not_null",
                    "arg_values": None,
                    "subject": None,
                    "arg_columns": ["chol"],
                },
                {
                    "check_case": "disjunction",
                    "expressions": [
                        {
                            "command": "is_less_than",
                            "arg_values": [2.5],
                            "arg_columns": None,
                            "subject": None,
                        },
                        {
                            "command": "is_equal_to",
                            "arg_values": [-1],
                            "arg_columns": None,
                            "subject": None,
                        },
                        {
                            "command": "is_equal_to",
                            "arg_values": [-2],
                            "arg_columns": None,
                            "subject": None,
                        },
                        {
                            "command": "is_equal_to",
                            "arg_values": [-10],
                            "arg_columns": None,
                            "subject": None,
                        },
                    ],
                },
            ],
        }

    def test_parse_conditional_single_arg_conjunction_wrapper(self):
        expression = ValidationExpression(
            conditional_expression=ValidationExpression(
                command="is_not_null",
                arg_columns=["chol"],
            ),
            command="conjunction",
            arg_expressions=[
                ValidationExpression(
                    command="is_in",
                    arg_values=[1, 2, 3],
                )
            ],
        )

        result = parse_validation_expression(expression)

        assert result == {
            "check_case": "condition",
            "expressions": [
                {
                    "command": "is_not_null",
                    "arg_values": None,
                    "subject": None,
                    "arg_columns": ["chol"],
                },
                {
                    "command": "is_in",
                    "arg_values": [1, 2, 3],
                    "arg_columns": None,
                    "subject": None,
                },
            ],
        }

    @pytest.mark.parametrize("command", ["conjunction", "disjunction"])
    @pytest.mark.parametrize(
        "arg_expressions",
        [
            None,
            [],
            [ValidationExpression(command="is_equal_to")],
        ],
        ids=["missing-operands", "zero-operands", "one-operand"],
    )
    def test_parse_conjunction_or_disjunction_requires_two_operands(
        self, command, arg_expressions
    ):
        expression = ValidationExpression(
            command=command,
            arg_expressions=arg_expressions,
        )

        with pytest.raises(ValueError, match="two or more arg expressions"):
            parse_validation_expression(expression)

    @pytest.mark.parametrize(
        "columns, expected_output",
        [
            (
                [
                    ColumnValidation(
                        unique_name="col1",
                        data_type="string",
                        required=True,
                        nullable=False,
                        validations=[],
                    )
                ],
                [
                    {
                        "id": "col1",
                        "data_type": "string",
                        "required": True,
                        "nullable": False,
                        "unique": False,
                        "checks": [],
                    }
                ],
            ),
            (
                [
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
                                    command="is_greater_than",
                                    arg_columns=["col1"],
                                ),
                            ),
                        ],
                    )
                ],
                [
                    {
                        "id": "col1",
                        "data_type": "string",
                        "required": True,
                        "nullable": False,
                        "unique": False,
                        "checks": [
                            {
                                "name": "name",
                                "error_level": "error",
                                "command": "is_greater_than",
                                "arg_values": None,
                                "subject": None,
                                "arg_columns": ["col1"],
                            }
                        ],
                    }
                ],
            ),
        ],
    )
    def test_parse_columns(self, columns, expected_output):
        result = parse_columns(columns)

        assert result == expected_output

    @pytest.mark.parametrize(
        "config, expected_output",
        [
            (
                ValidationConfig(
                    name="test_config",
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
                                        command="is_greater_than",
                                        arg_columns=["col1"],
                                    ),
                                )
                            ],
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
                    "name": "test_config",
                    "columns": [
                        {
                            "id": "col1",
                            "data_type": "string",
                            "required": True,
                            "nullable": False,
                            "unique": False,
                            "checks": [
                                {
                                    "name": "name",
                                    "error_level": "error",
                                    "command": "is_greater_than",
                                    "arg_values": None,
                                    "subject": None,
                                    "arg_columns": ["col1"],
                                }
                            ],
                        }
                    ],
                    "ids": ["col1"],
                    "checks": [
                        {
                            "name": "name",
                            "error_level": "error",
                            "command": "is_greater_than",
                            "arg_values": None,
                            "arg_columns": ["col2"],
                            "subject": ["col1"],
                        }
                    ],
                },
            ),
        ],
    )
    def test_parse_config(self, config, expected_output):
        result = parse_config(config)
        assert result == expected_output

    def test_exception_handling(self, monkeypatch):
        adapter = ValidationInterface.get_default_adapter_class()
        monkeypatch.setattr("polars.DataFrame.cast", ArithmeticError)

        config = ValidationConfig(
            name="exception_handling_test",
            columns=[],
            identifying_column_names=[],
            validations=[],
        )
        data = {"col1": [1, 2, 3], "col2": [2, 1, 4]}

        result = adapter()._validate(data, config)
        assert result is not None
        assert result.total_errors == 1
        assert len(result.unexpected_errors) == 1
        assert result.error_counts[ValidationErrorLevel.FATAL] == 1
        assert result.unexpected_errors[0].type == "AttributeError"


@pytest.mark.dataframe
class TestPehToDto:
    @pytest.fixture(scope="function")
    def get_check_command_cache(self):
        source = get_absolute_path("input_check_command")
        container = CacheContainerFactory.new()
        host = DirectoryIO()
        roots = host.load(source, format="yaml")
        for root in roots:
            for entity in load_entities_from_tree(root):
                container.add(entity)
        return CacheContainerView(container)

    @pytest.fixture(scope="function")
    def get_arg_expression_cache(self):
        source = get_absolute_path("input_arg_expression")
        container = CacheContainerFactory.new()
        host = DirectoryIO()
        roots = host.load(source, format="yaml")
        for root in roots:
            for entity in load_entities_from_tree(root):
                container.add(entity)
        return CacheContainerView(container)

    def test_condition(
        self, get_check_command_cache, get_arg_expression_cache
    ):
        """
        Checks whether using a single validation_command leads to the same
        validation configuration as using one validation_arg_expression.
        """
        adapter = ValidationInterface.get_default_adapter_class()
        adapter = adapter()
        matrix_chol_schema = DatasetSchema(
            elements={
                "id_sample": DatasetSchemaElement(
                    label="id_sample",
                    observable_property_id="id_sample",
                    data_type=ObservablePropertyValueType.STRING,
                ),
                "matrix": DatasetSchemaElement(
                    label="matrix",
                    observable_property_id="matrix",
                    data_type=ObservablePropertyValueType.STRING,
                ),
                "chol": DatasetSchemaElement(
                    label="chol",
                    observable_property_id="chol",
                    data_type=ObservablePropertyValueType.FLOAT,
                ),
            },
            primary_keys=set("id_sample"),
            foreign_keys={},
        )

        dataset = Dataset(
            label="matrix_chol",
            schema=matrix_chol_schema,
        )

        check_command_cache_view = get_check_command_cache
        vc_check = adapter.build_validation_config(
            dataset=dataset, cache_view=check_command_cache_view
        )
        arg_expression_cache_view = get_arg_expression_cache
        vc_arg = adapter.build_validation_config(
            dataset=dataset, cache_view=arg_expression_cache_view
        )

        assert len(vc_check.columns) == len(vc_arg.columns)

        for check_col, arg_col in zip(vc_check.columns, vc_arg.columns):
            assert check_col.validations is not None
            assert arg_col.validations is not None
            assert len(check_col.validations) == len(arg_col.validations)

        parsed_vc_check = parse_config(vc_check)

        parsed_vc_arg = parse_config(vc_arg)

        def strip_names(obj):
            """Recursively remove 'name' keys from dicts and lists."""
            if isinstance(obj, dict):
                return {
                    k: strip_names(v) for k, v in obj.items() if k != "name"
                }
            elif isinstance(obj, list):
                return [strip_names(item) for item in obj]
            else:
                return obj

        def are_dicts_equal_except_names(dict1, dict2):
            stripped1 = strip_names(deepcopy(dict1))
            stripped2 = strip_names(deepcopy(dict2))
            return stripped1 == stripped2

        assert are_dicts_equal_except_names(parsed_vc_check, parsed_vc_arg)
