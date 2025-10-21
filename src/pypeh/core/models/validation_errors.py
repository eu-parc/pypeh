import json

from datetime import datetime
from typing import Any, Dict, List, Tuple, Literal, Optional, Union
from pydantic import BaseModel, Field, field_serializer
from typing_extensions import Annotated

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


class EntityLocation(ValidationErrorLocation):
    """Location information for Entity-based validation errors"""

    location_type: Literal["entity"] = "entity"
    identifying_property_list: List[str]
    identifying_property_values: List[Tuple[Union[int, float, str, None], ...]]


# Example of another ValidationErrorLocation subclass
class FileLocation(ValidationErrorLocation):
    location_type: Literal["file"] = "file"
    filepath: str


# The discriminated union definition
LocationUnion = Annotated[
    Union[DataFrameLocation, FileLocation, EntityLocation],
    Field(discriminator="location_type"),
]


class RuntimeError(BaseModel):
    message: str = Field(description="Human-readable error message")
    type: str = Field(description="Machine-readable error code")


class ValidationError(BaseModel):
    """Base validation error model"""

    message: str = Field(description="Human-readable error message")
    type: str = Field(description="Machine-readable error code")
    level: ValidationErrorLevel

    locations: Optional[List[LocationUnion]] = Field(default_factory=list, description="Where the error occurred")
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
    unexpected_errors: List[ValidationError | RuntimeError] = Field(default_factory=list)

    @field_serializer("error_counts")
    def serialize_error_counts(self, error_counts: Dict[ValidationErrorLevel, int]):
        return {k.name: v for k, v in error_counts.items()}

    @classmethod
    def from_runtime_error(cls, exception: Exception):
        runtime_exception = RuntimeError(
            type=type(exception).__name__,
            message=str(exception),
        )
        counter = {level: 0 for level in ValidationErrorLevel}
        counter[ValidationErrorLevel.FATAL] = 1
        return cls(
            timestamp=datetime.now().isoformat(),
            total_errors=1,
            error_counts=counter,
            groups=[],
            unexpected_errors=[runtime_exception],
        )


class ValidationErrorReportCollection(dict[str, ValidationErrorReport]):
    """Collection of validation reports mapped by observation"""

    def model_dump_json(self, indent: int = 2) -> str:
        json_dict = {observation_id: report.model_dump() for observation_id, report in self.items()}

        return json.dumps(json_dict, indent=indent)
