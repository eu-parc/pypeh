import pytest

from pypeh.adapters.outbound.validation.pandera_adapter.parsers import (
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
from pypeh.core.models.constants import ValidationErrorLevel


@pytest.mark.dataframe
@pytest.mark.parametrize(
    "input_data, expected_output",
    [
        (
            ValidationExpression(
                command="is_greater_than",
                arg_columns=["col1"],
            ),
            {"command": "is_greater_than", "arg_values": None, "subject": None, "arg_columns": ["col1"]},
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
                    {"command": "is_greater_than", "arg_values": None, "subject": None, "arg_columns": ["col1"]},
                    {"command": "is_less_than", "arg_values": None, "subject": None, "arg_columns": ["col2"]},
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
                    {"command": "is_greater_than", "arg_values": None, "subject": None, "arg_columns": ["col1"]},
                    {"command": "is_less_than", "arg_values": [10], "subject": ["col2"], "arg_columns": None},
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
                "check_case": "conditional",
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
                            {"command": "is_less_than", "arg_values": [10], "subject": ["col2"], "arg_columns": None},
                        ],
                    },
                    {"command": "is_equal_to", "arg_values": [5], "subject": None, "arg_columns": None},
                ],
            },
        ),
    ],
)
def test_parse_validation_expression(input_data, expected_output):
    result = parse_validation_expression(input_data)
    assert result == expected_output


@pytest.mark.dataframe
@pytest.mark.parametrize(
    "columns, expected_output",
    [
        (
            [ColumnValidation(unique_name="col1", data_type="string", required=True, nullable=False, validations=[])],
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
def test_parse_columns(columns, expected_output):
    result = parse_columns(columns)

    assert result == expected_output


@pytest.mark.dataframe
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
def test_parse_config(config, expected_output):
    result = parse_config(config)

    assert result == expected_output
