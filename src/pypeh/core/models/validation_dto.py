from __future__ import annotations

import logging
import uuid

from collections import defaultdict
from enum import Enum
from pydantic import BaseModel, field_validator
from typing import Generic, Any, Sequence, TYPE_CHECKING

from pypeh.core.models.typing import T_DataType
from pypeh.core.models.constants import ObservablePropertyValueType, ValidationErrorLevel
from peh_model import pydanticmodel_v2 as pehs
from peh_model import peh


if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def convert_peh_validation_error_level_to_validation_dto_error_level(peh_validation_error_level: str | None):
    if peh_validation_error_level is None:
        return ValidationErrorLevel.ERROR
    else:
        match peh_validation_error_level:
            case "info":
                return ValidationErrorLevel.INFO
            case "warning":
                return ValidationErrorLevel.WARNING
            case "error":
                return ValidationErrorLevel.ERROR
            case "fatal":
                return ValidationErrorLevel.FATAL
            case _:
                raise ValueError(f"Invalid Error level encountered: {peh_validation_error_level}")


def cast_to_peh_value_type(value: str, peh_value_type: ObservablePropertyValueType | str | None) -> Any:
    # valid input values: "string", "boolean", "date", "datetime", "decimal", "float", "integer"
    if isinstance(peh_value_type, Enum):
        peh_value_type = peh_value_type.value
    if not isinstance(value, str):
        return value

    match peh_value_type:
        case "string":
            return str(value)
        case "boolean":
            return bool(value)
        case "date":
            return str(value)  # FIXME
        case "datetime":
            return str(value)  # FIXME
        case "decimal":
            logger.info("Casting decimal as float")
            return float(value)
        case "integer":
            return int(value)
        case "float":
            return float(value)
        case _:
            return str(value)


def merge_dependencies(
    a: dict[str, set[str]] | None,
    b: dict[str, set[str]] | None,
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    if a:
        for ds, fields in a.items():
            result[ds].update(fields)
    if b:
        for ds, fields in b.items():
            result[ds].update(fields)
    return result


class ValidationExpression(BaseModel):
    conditional_expression: ValidationExpression | None = None
    arg_expressions: list[ValidationExpression] | None = None
    command: str
    arg_values: list[Any] | None = None
    arg_columns: list[str] | None = None
    subject: list[str] | None = None
    dependent_contextual_field_references: dict[str, set[str]] | None = None

    @field_validator("command", mode="before")
    @classmethod
    def command_to_str(cls, v):
        if v is None:
            return "conjunction"
        elif isinstance(v, peh.PermissibleValue):
            return v.text
        elif isinstance(v, str):
            return v
        elif isinstance(v, peh.ValidationCommand):
            return str(v)
        else:
            logger.error(f"No conversion defined for {v} of type {v.__class__}")
            raise NotImplementedError

    @classmethod
    def from_peh(
        cls,
        expression: peh.ValidationExpression | pehs.ValidationExpression,
        type_annotations: dict[str, dict[str, ObservablePropertyValueType]] | None = None,
        dataset_label: str | None = None,
    ) -> "ValidationExpression":
        dependent_contextual_field_references = defaultdict(set)
        conditional_expression = getattr(expression, "validation_condition_expression")
        conditional_expression_instance = None
        if conditional_expression is not None:
            conditional_expression_instance = ValidationExpression.from_peh(
                conditional_expression,
                type_annotations,
                dataset_label=dataset_label,
            )
            dependent_contextual_field_references = merge_dependencies(
                dependent_contextual_field_references,
                conditional_expression_instance.dependent_contextual_field_references,
            )

        arg_expressions = getattr(expression, "validation_arg_expressions")
        arg_expression_instances = None
        if arg_expressions is not None:
            arg_expression_instances = []
            for nested_expr in arg_expressions:
                new_arg_expression = ValidationExpression.from_peh(
                    nested_expr, type_annotations, dataset_label=dataset_label
                )
                arg_expression_instances.append(new_arg_expression)
                dependent_contextual_field_references = merge_dependencies(
                    dependent_contextual_field_references, new_arg_expression.dependent_contextual_field_references
                )
        validation_command = getattr(expression, "validation_command", "conjunction")

        subject_contextual_field_references = getattr(
            expression, "validation_subject_contextual_field_references", None
        )
        subject_columns = None
        data_type = None
        if subject_contextual_field_references is not None:
            subject_columns = []
            data_types = set()
            assert type_annotations is not None
            for field_reference in subject_contextual_field_references:
                ref_dataset_label = getattr(field_reference, "dataset_label", None)
                assert ref_dataset_label is not None
                if ref_dataset_label != dataset_label:
                    dependent_contextual_field_references[ref_dataset_label].add(field_reference.field_label)
                subject_columns.append(field_reference.field_label)
                data_type = type_annotations.get(ref_dataset_label, {}).get(field_reference.field_label, None)
                assert (
                    data_type is not None
                ), f"Did not find type_annotation for dataset with label {ref_dataset_label} and field_label {field_reference.field_label}"
                data_types.add(data_type)
            assert (
                len(data_types) <= 1
            ), f'Found the following datatypes for the subject_contextual_field_references: {", ".join(dt for dt in data_types)}'
            data_type = next(iter(data_types), None)
        if data_type is None:
            data_type = ObservablePropertyValueType.STRING

        arg_values = getattr(expression, "validation_arg_values", None)
        if arg_values is not None:
            assert isinstance(arg_values, Sequence)
            try:
                arg_values = [cast_to_peh_value_type(arg_value, data_type) for arg_value in arg_values]
            except Exception as e:
                logger.error(f"Could not cast values in {arg_values} to {data_type}: {e}")
                raise

        arg_contextual_field_references = getattr(expression, "validation_arg_contextual_field_references", None)
        arg_columns = None
        if arg_contextual_field_references is not None:
            arg_columns = []
            for field_reference in arg_contextual_field_references:
                ref_dataset_label = getattr(field_reference, "dataset_label", None)
                assert ref_dataset_label is not None
                if ref_dataset_label != dataset_label:
                    dependent_contextual_field_references[ref_dataset_label].add(field_reference.field_label)
                arg_columns.append(field_reference.field_label)

        return cls(
            conditional_expression=conditional_expression_instance,
            arg_expressions=arg_expression_instances,
            command=validation_command,
            arg_values=arg_values,
            arg_columns=arg_columns,
            subject=subject_columns,
            dependent_contextual_field_references=dependent_contextual_field_references,
        )


class ValidationDesign(BaseModel):
    name: str
    error_level: ValidationErrorLevel
    expression: ValidationExpression
    dependent_contextual_field_references: dict[str, set[str]] | None = None

    @classmethod
    def from_peh(
        cls,
        validation_design: peh.ValidationDesign | pehs.ValidationDesign,
        type_annotations: dict[str, dict[str, ObservablePropertyValueType]],
        dataset_label: str | None = None,
    ) -> "ValidationDesign":
        dependent_contextual_field_references = defaultdict(set)
        error_level = getattr(validation_design, "error_level", None)
        error_level = convert_peh_validation_error_level_to_validation_dto_error_level(error_level)
        expression = getattr(validation_design, "validation_expression", None)
        if expression is None:
            raise AttributeError
        expression = ValidationExpression.from_peh(expression, type_annotations, dataset_label=dataset_label)
        name = getattr(validation_design, "validation_name", None)
        if name is None:
            name = str(uuid.uuid4())

        dependent_contextual_field_references = merge_dependencies(
            dependent_contextual_field_references, expression.dependent_contextual_field_references
        )
        return cls(
            name=name,
            error_level=error_level,
            expression=expression,
            dependent_contextual_field_references=dependent_contextual_field_references,
        )

    @classmethod
    def list_from_metadata(
        cls,
        metadata: list[Any],
        type_annotations: dict[str, dict[str, ObservablePropertyValueType]],
        dataset_label: str | None = None,
    ) -> list["ValidationDesign"]:
        name_expression_list = []
        numeric_commands = set(
            [
                "min",
                "max",
                "is_equal_to",
                "is_greater_than_or_equal_to",
                "is_greater_than",
                "is_equal_to_or_both_missing",
                "is_less_than_or_equal_to",
                "is_less_than",
                "is_not_equal_to",
                "is_not_equal_to_and_not_both_missing",
            ]
        )
        for metadatum in metadata:
            arg_type = "string"
            if metadatum.field.lower() in numeric_commands:
                if metadatum.value is not None:
                    try:
                        # NOTE: type conversion here is useless unless using Baseclass.model_construct() to avoid validation
                        arg_type = "float"
                        typed_metadata_value = cast_to_peh_value_type(metadatum.value, arg_type)
                    except Exception as e:
                        logger.error(
                            f"could not cast ValidationExpression argument {metadatum.value} to {arg_type}: {e}"
                        )
                        raise

            generate = False
            match metadatum.field.lower():
                case "min":
                    validation_command = peh.ValidationCommand.is_greater_than_or_equal_to
                    generate = True
                case "max":
                    validation_command = peh.ValidationCommand.is_less_than_or_equal_to
                    generate = True
                case "is_equal_to":
                    validation_command = peh.ValidationCommand.is_equal_to
                    generate = True
                case "is_equal_to_or_both_missing":
                    validation_command = peh.ValidationCommand.is_equal_to_or_both_missing
                    generate = True
                case "is_greater_than_or_equal_to":
                    validation_command = peh.ValidationCommand.is_greater_than_or_equal_to
                    generate = True
                case "is_greater_than":
                    validation_command = peh.ValidationCommand.is_greater_than
                    generate = True
                case "is_less_than_or_equal_to":
                    validation_command = peh.ValidationCommand.is_less_than_or_equal_to
                    generate = True
                case "is_less_than":
                    validation_command = peh.ValidationCommand.is_less_than
                    generate = True
                case "is_not_equal_to":
                    validation_command = peh.ValidationCommand.is_not_equal_to
                    generate = True
                case "is_not_equal_to_and_not_both_missing":
                    validation_command = peh.ValidationCommand.is_not_equal_to_and_not_both_missing
                    generate = True

            if generate:
                name_expression_list.append(
                    (
                        metadatum.field.lower(),
                        ValidationExpression.from_peh(
                            pehs.ValidationExpression.model_construct(
                                **{
                                    "validation_command": validation_command,
                                    "validation_arg_values": [typed_metadata_value],
                                }
                            ),
                            type_annotations=type_annotations,
                            dataset_label=dataset_label,
                        ),
                    )
                )

        return [
            cls(name=name, error_level=ValidationErrorLevel.ERROR, expression=expression)
            for name, expression in name_expression_list
        ]


class ColumnValidation(BaseModel):
    unique_name: str
    data_type: str
    required: bool
    nullable: bool
    validations: list[ValidationDesign] | None = None


class ValidationConfig(BaseModel, Generic[T_DataType]):
    name: str
    columns: list[ColumnValidation]
    identifying_column_names: list[str] | None = None
    validations: list[ValidationDesign] | None = None
    dependent_contextual_field_references: dict[str, set[str]] = defaultdict(set)


class ValidationDTO(BaseModel):
    config: ValidationConfig
    data: dict[str, Any]
