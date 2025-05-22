from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ValidationExpression(BaseModel):
    conditional_expression: ValidationExpression | None = None
    arg_expressions: list[ValidationExpression] | None = None
    command: str
    arg_values: list[Any] | None = None
    arg_columns: list[str] | None = None
    subject: list[str] | None = None


class ValidationDesign(ValidationExpression):
    name: str
    error_level: str


class ColumnValidation(BaseModel):
    unique_name: str
    data_type: str
    required: bool
    nullable: bool
    unique: bool = False
    validations: list[ValidationDesign] | None = None


class DataFrameValidationConfig(BaseModel):
    name: str
    columns: list[ColumnValidation]
    identifying_column_names: list[str] | None = None
    validations: list[ValidationDesign] | None = None
