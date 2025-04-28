from typing import Any, NewType

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


class GroupedErrors(BaseModel):
    """Grouped validation errors model.

    Group list of errors given a group_id."""

    name: str
    metadata: dict[str, Any]
    errors: list[ValidationError]
    group_id: str


T_DataFrameID = NewType("T_DataFrameID", str)


class DataFrameErrors(GroupedErrors):
    """Grouped validation errors model for DataFrame group_id."""

    group_id: T_DataFrameID


class ValidationErrorReport(BaseModel):
    """Validation error report model."""

    errors: list[GroupedErrors | GenericValidationError]
