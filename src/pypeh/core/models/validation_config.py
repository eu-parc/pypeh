from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from pypeh.core.models.constants import ValidationErrorLevel
from pypeh.core.models.dto import MetaData


class ValidationExpression(BaseModel):
    conditional_expression: ValidationExpression | None = None
    arg_expressions: list[ValidationExpression] | None = None
    command: str
    arg_values: list[Any] | None = None
    arg_columns: list[str] | None = None
    subject: list[str] | None = None


class ValidationDesign(BaseModel):
    name: str
    error_level: ValidationErrorLevel
    expression: ValidationExpression


class ColumnValidation(BaseModel):
    unique_name: str
    data_type: str
    required: bool
    nullable: bool
    unique: bool = False
    validations: list[ValidationDesign] | None = None


class DataFrameValidationConfig(MetaData):
    name: str
    columns: list[ColumnValidation]
    identifying_column_names: list[str] | None = None
    validations: list[ValidationDesign] | None = None
