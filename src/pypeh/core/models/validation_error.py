from typing import Any, NewType
from pydantic import BaseModel

from pypeh.core.models.constants import ValidationErrorLevel


T_DataFrameID = NewType("T_DataFrameID", str)


class ValidationInterfaceError(BaseModel):
    message: str
    type: str  # type or checkname
    level: ValidationErrorLevel


class GenericValidationError(ValidationInterfaceError):
    """Generic validation error model.

    Errors happening during validation that are not a direct consequence
    of failing one or more validation checks.
    """

    message: str
    type: str
    level: ValidationErrorLevel

    traceback: str
    context: str | None = None
    source: str | None = None


class ValidationError(ValidationInterfaceError):
    """Validation error model.

    Validation errors that are from validation checks.
    """

    message: str
    check_name: str  # change to type here, no need to name this differently I think.
    level: ValidationErrorLevel

    cases: dict[str, Any]  # Can you specify what cases are
    data_ids: Any  # identifier/location of the data that is causing the validation error ## TODO: typing should be improved upon.


class DataFrameDataId(BaseModel):
    dataframe_ids: list[str]
    column_id: str
    row_ids: list[str]


class DataFrameValidationError(ValidationError):
    data_ids: DataFrameDataId


class GroupedErrors(BaseModel):
    """Grouped validation errors model.

    Group list of errors given a group_id."""

    name: str
    metadata: dict[str, Any]
    errors: list[ValidationError]
    group_id: str


class DataFrameErrors(GroupedErrors):
    """Grouped validation errors model for DataFrame group_id."""

    group_id: T_DataFrameID


class ValidationErrorReport(BaseModel):
    """Validation error report model."""

    errors: list[GroupedErrors | GenericValidationError]
