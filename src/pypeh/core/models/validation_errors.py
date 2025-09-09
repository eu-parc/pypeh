import json

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_serializer

from pypeh.core.models.constants import ValidationErrorLevel


class ValidationErrorLocation(BaseModel):
    """Base class for specifying where an error occurred"""

    location_type: str


class DataFrameLocation(ValidationErrorLocation):
    """Location information for DataFrame-based validation errors"""

    location_type: Literal["dataframe"] = "dataframe"
    key_columns: List[str]  # List of column names that jointly identifies a dataframe entry.
    column_names: Optional[List[str]] = None
    row_ids: List[int] = []


class ValidationError(BaseModel):
    """Base validation error model"""

    message: str = Field(description="Human-readable error message")
    type: str = Field(description="Machine-readable error code")
    level: ValidationErrorLevel

    locations: Optional[List[ValidationErrorLocation]] = Field(
        default_factory=list, description="Where the error occurred"
    )
    context: Optional[list[str]] = None
    check_name: Optional[str] = None
    traceback: Optional[str] = None
    source: Optional[str] = None

    @field_serializer("level")
    def serialize_error_counts(self, level: ValidationErrorLevel):
        return level.name


class ValidationErrorGroup(BaseModel):
    """Group of related validation errors"""

    group_id: str
    group_type: str
    name: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    errors: List[ValidationError] = Field(default_factory=list)


class ValidationErrorReport(BaseModel):
    """Complete validation report"""

    timestamp: str
    total_errors: int
    error_counts: Dict[ValidationErrorLevel, int] = Field(default_factory=dict)
    groups: List[ValidationErrorGroup] = Field(default_factory=list)
    unexpected_errors: List[ValidationError] = Field(default_factory=list)

    @field_serializer("error_counts")
    def serialize_error_counts(self, error_counts: Dict[ValidationErrorLevel, int]):
        return {k.name: v for k, v in error_counts.items()}


class ValidationErrorReportCollection(dict[str, ValidationErrorReport]):
    """Collection of validation reports mapped by observable property set"""

    def model_dump_json(self, indent: int = 2) -> str:
        json_dict = {property_set: report.model_dump() for property_set, report in self.items()}

        return json.dumps(json_dict, indent=indent)
