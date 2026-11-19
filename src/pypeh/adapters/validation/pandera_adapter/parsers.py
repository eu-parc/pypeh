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
            importlib.import_module(
                "pypeh.adapters.validation.pandera_adapter.check_functions"
            ),
            command,
        )
    except AttributeError:
        try:
            from pypeh.adapters.validation.pandera_adapter.check_functions import (
                AVAILABLE_CHECKS,
            )
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
    logical_commands = ("conjunction", "disjunction")
    is_logical = expression.command in logical_commands

    if conditional_expr := expression.conditional_expression:
        arg_expressions = expression.arg_expressions

        if not arg_expressions or (is_logical and len(arg_expressions) > 1):
            consequence = expression.model_copy(
                update={"conditional_expression": None}
            )
        else:
            if len(arg_expressions) != 1:
                raise NotImplementedError(
                    "Conditional expressions with a validation condition "
                    "currently support exactly one arg expression. "
                    f"received={len(arg_expressions)}."
                )
            consequence = arg_expressions[0]

        return {
            "check_case": "condition",
            "expressions": [
                parse_validation_expression(conditional_expr),
                parse_validation_expression(consequence),
            ],
        }
    if is_logical:
        arg_expressions = expression.arg_expressions or []

        if len(arg_expressions) < 2:
            raise ValueError(
                "Conjunction/disjunction expressions need "
                f"two or more arg expressions. received={len(arg_expressions)}."
            )

        return {
            "check_case": expression.command,
            "expressions": [
                parse_validation_expression(exp) for exp in arg_expressions
            ],
        }
    return parse_single_expression(expression)


def parse_validation_design(validation_design: ValidationDesign) -> Mapping:
    ret = {
        "name": validation_design.name,
        "error_level": validation_design.error_level.name.lower(),
    }
    if validation_design.error_message is not None:
        ret["error_msg"] = validation_design.error_message
    ret |= dict(parse_validation_expression(validation_design.expression))

    return ret


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
                "checks": [
                    parse_validation_design(check)
                    for check in column.validations
                ]
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
        "checks": [
            parse_validation_design(check) for check in config.validations
        ]
        if config.validations
        else [],
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
        message=exception.message,
        type=exception.type,
        level=map_error_level(exception.level),
        traceback=exception.traceback,
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

    if getattr(error_schema, "column_names", None):
        column_names = (
            [col_name for col_name in error_schema.column_names]
            if isinstance(error_schema.column_names, list)
            else [error_schema.column_names]
        )
        locations = [
            DataFrameLocation(
                location_type="dataframe",
                key_columns=error_schema.idx_columns,
                column_names=column_names,
                row_ids=error_schema.row_ids,
            )
        ]
    else:
        locations = None
    return ValidationError(
        message=error_schema.message,
        type=error_schema.title,
        level=level,
        locations=locations,
        check_name=error_schema.title,
    )


def parse_error_report(
    error_collector_schema: ErrorCollectorSchema,
) -> ValidationErrorReport:
    error_reports = error_collector_schema.error_reports
    exceptions = error_collector_schema.exceptions

    groups = (
        [parse_validation_error_group(group) for group in error_reports]
        if error_reports
        else []
    )
    unexpected_errors = (
        [parse_collected_exception(exception) for exception in exceptions]
        if exceptions
        else []
    )

    counter = {level: 0 for level in ValidationErrorLevel}

    total_errors = 0
    for group in groups:
        for error in group.errors:
            total_errors += 1
            counter[error.level] += 1
    for error in unexpected_errors:
        total_errors += 1
        counter[error.level] += 1

    return ValidationErrorReport(
        timestamp=datetime.now().isoformat(),
        total_errors=total_errors,
        error_counts=counter,
        groups=groups,
        unexpected_errors=unexpected_errors,
    )
