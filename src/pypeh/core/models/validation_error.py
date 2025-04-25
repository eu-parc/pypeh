from typing import Any

from pydantic import BaseModel

from pypeh.core.models.constants import ValidationErrorLevel


class GenericValidationError(BaseModel):
    """Generic validation error model.

    Validation errors that are not from validation checks.
    """

    type: str
    message: str
    level: ValidationErrorLevel
    traceback: str
    context: str | None = None
    source: str | None = None


class ValidationError(BaseModel):
    """Validation error model.

    Validation errors that are from validation checks.
    """

    check_name: str
    level: ValidationErrorLevel
    message: str
    column_id: str
    dataframe_ids: list[str]
    row_ids: list[str]
    cases: dict[str, Any]


class DataFrameErrors(BaseModel):
    """DataFrame validation error model.

    Group validation errors by dataframe.
    """

    name: str
    metadata: dict[str, Any]
    errors: list[ValidationError]


class ValidationErrorReport(BaseModel):
    """Validation error report model."""

    dataframe_errors: list[DataFrameErrors]
    generic_errors: list[GenericValidationError]
