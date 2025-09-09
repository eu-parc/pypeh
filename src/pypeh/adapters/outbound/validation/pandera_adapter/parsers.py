from __future__ import annotations

import importlib

from datetime import datetime
from enum import Enum
from typing import Mapping, Sequence, TYPE_CHECKING, List

from pypeh.core.models.constants import ValidationErrorLevel
from pypeh.core.models.validation_dto import (
    ValidationDesign,
    ValidationExpression,
    ColumnValidation,
    ValidationConfig,
)
from pypeh.core.models.validation_errors import (
    ValidationErrorReport,
    ValidationErrorGroup,
    ValidationError,
    DataFrameLocation,
)


if TYPE_CHECKING:
    from dataguard.error_report.error_schemas import (
        ErrorCollectorSchema,
        ErrorSchema,
        ExceptionSchema,
    )
    from dataguard.core.utils.enums import ErrorLevel


def parse_single_expression(expression: ValidationExpression) -> Mapping:
    command = expression.command
    try:
        command = getattr(
            importlib.import_module("pypeh.adapters.outbound.validation.pandera_adapter.check_functions"), command
        )
    except AttributeError:
        try:
            from pypeh.adapters.outbound.validation.pandera_adapter.check_functions import AVAILABLE_CHECKS
        except Exception as _:
            ImportError("Please install dataframe module.")
        assert command in AVAILABLE_CHECKS

    return {
        "command": command,
        "arg_values": expression.arg_values,
        "arg_columns": expression.arg_columns,
        "subject": expression.subject,
    }


def parse_validation_expression(expression: ValidationExpression) -> Mapping:
    if conditional_expr := expression.conditional_expression:
        case = "condition"
        exp_1 = parse_validation_expression(conditional_expr)
        arg_expressions = expression.arg_expressions
        if arg_expressions is None or (isinstance(arg_expressions, list) and len(arg_expressions) == 0):
            expression.conditional_expression = None
            exp_2 = parse_validation_expression(expression)
        else:
            if len(arg_expressions) != 1:
                raise NotImplementedError(
                    f"Conditional expression {expression.conditional_expression} can only take a single validation_arg_expression"
                )
            exp_2 = parse_validation_expression(arg_expressions[0])

        return {
            "check_case": case,
            "expressions": [exp_1, exp_2],
        }
    if expression.command in ("conjunction", "disjunction"):
        if expression.arg_expressions is not None:
            if len(expression.arg_expressions) != 2:
                raise NotImplementedError
            case = expression.command
            exp_1 = parse_validation_expression(expression.arg_expressions[0])
            exp_2 = parse_validation_expression(expression.arg_expressions[1])
            return {
                "check_case": case,
                "expressions": [exp_1, exp_2],
            }
        else:
            raise ValueError
    return parse_single_expression(expression)


def parse_validation_design(validation_design: ValidationDesign) -> Mapping:
    return {
        "name": validation_design.name,
        "error_level": validation_design.error_level.name.lower(),
    } | dict(parse_validation_expression(validation_design.expression))


def parse_columns(columns: Sequence[ColumnValidation]) -> List:
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
                else [],
            }
        )
    return parsed_columns


def parse_config(config: ValidationConfig) -> Mapping:
    return {
        "name": config.name,
        "columns": parse_columns(config.columns),
        "ids": config.identifying_column_names,
        "checks": [parse_validation_design(check) for check in config.validations] if config.validations else [],
    }


def map_error_level(level: ErrorLevel | str) -> ValidationErrorLevel:
    if isinstance(level, Enum):
        error_level = level.name.lower()
    else:
        error_level = level.lower()
    match error_level.lower():
        case "warning":
            return ValidationErrorLevel.WARNING
        case "error":
            return ValidationErrorLevel.ERROR
        case "critical":
            return ValidationErrorLevel.FATAL
        case _:
            raise ValueError(f"Unknown error level: {error_level}")


def parse_collected_exception(exception: ExceptionSchema) -> ValidationError:
    return ValidationError(
        message=exception.error_message,
        type=exception.error_type,
        level=map_error_level(exception.error_level),
        traceback=exception.error_traceback,
        context=exception.error_context,
        source=exception.error_source,
    )


def parse_validation_error_group(group) -> ValidationErrorGroup:
    return ValidationErrorGroup(
        group_id=str(group.id),
        group_type="pandera",
        name=group.name,
        metadata={},
        errors=[parse_error_schema(error) for error in group.errors],
    )


def parse_error_schema(error_schema: ErrorSchema) -> ValidationError:
    level = map_error_level(error_schema.level)
    column_names = (
        [col_name for col_name in error_schema.column_names]
        if isinstance(error_schema.column_names, list)
        else [error_schema.column_names]
    )

    return ValidationError(
        message=error_schema.message,
        type=error_schema.title,
        level=level,
        locations=[
            DataFrameLocation(
                location_type="dataframe",
                key_columns=error_schema.idx_columns,
                column_names=column_names,
                row_ids=error_schema.row_ids,
            )
        ],
        check_name=error_schema.title,
    )


def parse_error_report(error_collector_schema: ErrorCollectorSchema) -> ValidationErrorReport:
    error_reports = error_collector_schema.error_reports
    exceptions = error_collector_schema.exceptions

    groups = [parse_validation_error_group(group) for group in error_reports] if error_reports else []
    unexpected_errors = [parse_collected_exception(exception) for exception in exceptions] if exceptions else []

    counter = {level: 0 for level in ValidationErrorLevel}

    total_errors = 0
    for group in groups:
        for error in group.errors:
            total_errors += 1
            counter[error.level] += 1

    return ValidationErrorReport(
        timestamp=datetime.now().isoformat(),
        total_errors=total_errors,
        error_counts=counter,
        groups=groups,
        unexpected_errors=unexpected_errors,
    )
