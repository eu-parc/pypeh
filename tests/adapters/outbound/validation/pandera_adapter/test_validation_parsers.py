import peh_model.peh as peh
import pytest
import yaml

from copy import deepcopy

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
                        {"command": "is_equal_to", "arg_values": [5], "subject": None, "arg_columns": None},
                    ],
                },
            ),
        ],
    )
    def test_parse_validation_expression(self, input_data, expected_output):
        result = parse_validation_expression(input_data)
        assert result == expected_output

    @pytest.mark.parametrize(
        "columns, expected_output",
        [
            (
                [
                    ColumnValidation(
                        unique_name="col1", data_type="string", required=True, nullable=False, validations=[]
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


@pytest.mark.dataframe
class TestPehToDto:
    def test_condition(self):
        """
        Checks whether using a single validation_command leads to the same
        validation configuration as using one validation_arg_expression.
        """
        check_command_path = get_absolute_path("./input/check_command.yaml")
        with open(check_command_path) as f:
            check_command_yaml = yaml.safe_load(f)
        check_command_obs_props = [
            peh.ObservableProperty(**obs_prop) for obs_prop in check_command_yaml["observable_properties"]
        ]
        obs_prop_dict_check = {obs_prop.id: obs_prop for obs_prop in check_command_obs_props}
        observation_design_check = peh.ObservationDesign(**check_command_yaml["observations"][0]["observation_design"])

        vc_check = ValidationConfig.from_peh(
            "check",
            observation_design_check,
            obs_prop_dict_check,
        )

        arg_expression_path = get_absolute_path("./input/arg_expression.yaml")
        with open(arg_expression_path) as f:
            arg_expression_yaml = yaml.safe_load(f)
        arg_expression_obs_props = [
            peh.ObservableProperty(**obs_prop) for obs_prop in arg_expression_yaml["observable_properties"]
        ]

        obs_prop_dict_arg = {obs_prop.id: obs_prop for obs_prop in arg_expression_obs_props}
        observation_design_arg = peh.ObservationDesign(**arg_expression_yaml["observations"][0]["observation_design"])

        vc_arg = ValidationConfig.from_peh(
            "arg",
            observation_design_arg,
            obs_prop_dict_arg,
        )

        assert len(vc_check.columns) == len(vc_arg.columns)
        for check_col, arg_col in zip(vc_check.columns, vc_arg.columns):
            assert len(check_col.validations) == len(arg_col.validations)

        parsed_vc_check = parse_config(vc_check)

        parsed_vc_arg = parse_config(vc_arg)

        def strip_names(obj):
            """Recursively remove 'name' keys from dicts and lists."""
            if isinstance(obj, dict):
                return {k: strip_names(v) for k, v in obj.items() if k != "name"}
            elif isinstance(obj, list):
                return [strip_names(item) for item in obj]
            else:
                return obj

        def are_dicts_equal_except_names(dict1, dict2):
            stripped1 = strip_names(deepcopy(dict1))
            stripped2 = strip_names(deepcopy(dict2))
            return stripped1 == stripped2

        assert are_dicts_equal_except_names(parsed_vc_check, parsed_vc_arg)
