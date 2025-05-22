from typing import Mapping, Sequence
import importlib

from pypeh.core.models.validation_interface_objects import (
    ValidationDesign, ValidationExpression, ColumnValidation, DataFrameValidationConfig
)
from pypeh.core.models.validation_errors import ValidationReport


def parse_single_expression(expression: ValidationExpression) -> Mapping:
    command = expression.command
    try:
        command = getattr(importlib.import_module("pypeh.dataframe_adapter.validation.check_functions"), command)
    except AttributeError:
        pass
    return {
        "command": command,
        "arg_values": expression.arg_values,
        "arg_columns": expression.arg_columns,
        "subject": expression.subject,
    }


def parse_validation_expression(expression: ValidationExpression) -> Mapping:
    if conditional_expr := expression.conditional_expression:
        case = "conditional"
        exp_1 = parse_validation_expression(conditional_expr)
        expression.conditional_expression = None
        exp_2 = parse_validation_expression(expression)
        return {
            "check_case": case,
            "expressions": [exp_1, exp_2],
        }
    if expression.command in ("conjunction", "disjunction"):
        if len(expression.arg_expressions) != 2:
            raise NotImplementedError
        case = expression.command
        exp_1 = parse_validation_expression(expression.arg_expressions[0])
        exp_2 = parse_validation_expression(expression.arg_expressions[1])
        return {
            "check_case": case,
            "expressions": [exp_1, exp_2],
        }
    return parse_single_expression(expression)


def parse_validation_design(validation_design: ValidationDesign) -> Mapping:
    return {
        "name": validation_design.name,
        "error_level": validation_design.error_level,
    } | parse_validation_expression(validation_design.expression)


def parse_columns(columns: Sequence[ColumnValidation]) -> Mapping:
    parsed_columns = []
    for column in columns:
        parsed_columns.append(
            {
                "id": column.unique_name,
                "data_type": column.data_type,
                "required": column.required,
                "nullable": column.nullable,
                "unique": False,
                "checks": [parse_validation_design(check) for check in column.validations]
                if column.validations
                else None,
            }
        )
    return parsed_columns


def parse_config(config: DataFrameValidationConfig) -> Mapping:
    return {
        "name": config.name,
        "columns": parse_columns(config.columns),
        "ids": config.identifying_column_names,
        "checks": [parse_validation_design(check) for check in config.validations]
        if config.validations
        else None,
    }


def parse_error_report(error_report: Mapping) -> ValidationReport:
    # TODO: Implement the parsing logic for the error report
    return error_report
