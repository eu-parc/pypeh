import pytest

from copy import deepcopy

from pypeh.adapters.outbound.persistence.hosts import DirectoryIO
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
from pypeh.core.interfaces.outbound.dataops import ValidationInterface
from pypeh.core.models.constants import ValidationErrorLevel
from pypeh.core.cache.containers import CacheContainerFactory, CacheContainerView
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
        assert result.total_errors == 0
        assert len(result.unexpected_errors) == 1
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

    def test_condition(self, get_check_command_cache, get_arg_expression_cache):
        """
        Checks whether using a single validation_command leads to the same
        validation configuration as using one validation_arg_expression.
        """
        check_command_cache_view = get_check_command_cache
        check_command_obs_props = list(check_command_cache_view.get_all("ObservableProperty"))
        check_command_observations = list(check_command_cache_view.get_all("Observation"))
        observation_design_check = check_command_observations[0].observation_design

        vc_check = ValidationConfig.from_peh(
            "check",
            check_command_obs_props,
            observation_design_check,
            cache_view=check_command_cache_view,
        )

        arg_expression_cache_view = get_arg_expression_cache
        arg_expression_obs_props = list(arg_expression_cache_view.get_all("ObservableProperty"))
        arg_expression_observations = list(arg_expression_cache_view.get_all("Observation"))
        observation_design_arg = arg_expression_observations[0].observation_design

        vc_arg = ValidationConfig.from_peh(
            "arg",
            arg_expression_obs_props,
            observation_design_arg,
            cache_view=arg_expression_cache_view,
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
