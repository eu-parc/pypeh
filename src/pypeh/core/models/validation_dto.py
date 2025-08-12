from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from pydantic import BaseModel
from typing import Any, Dict, Generator

from pypeh.core.models.constants import ValidationErrorLevel
from peh_model import peh


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


def convert_peh_value_type_to_validation_dto_datatype(peh_value_type: str):
    # TODO: fix for "categorical" ?
    # TODO: review & extend potential input values
    # valid input values: "string", "boolean", "date", "datetime", "decimal"
    # valid return values: 'date', 'datetime', 'boolean', 'decimal', 'integer', 'varchar' or 'categorical'
    if peh_value_type is None:
        return None
    else:
        match peh_value_type:
            case "string":
                return "varchar"
            case "boolean" | "date" | "datetime" | "decimal":
                return peh_value_type
            case _:
                raise ValueError(f"Invalid data type encountered: {peh_value_type}")


class ValidationExpression(BaseModel):
    conditional_expression: ValidationExpression | None = None
    arg_expressions: list[ValidationExpression] | None = None
    command: str
    arg_values: list[Any] | None = None
    arg_columns: list[str] | None = None
    subject: list[str] | None = None

    @classmethod
    def from_peh(cls, expression: peh.ValidationExpression) -> "ValidationExpression":
        conditional_expression = getattr(expression, "validation_condition_expression")
        conditional_expression_instance = None
        if conditional_expression is not None:
            conditional_expression_instance = ValidationExpression.from_peh(conditional_expression)
        arg_expressions = getattr(expression, "validation_arg_expressions")
        arg_expression_instances = None
        if arg_expressions is not None:
            arg_expression_instances = [ValidationExpression.from_peh(nested_expr) for nested_expr in arg_expressions]
        validation_command = getattr(expression, "validation_command", None)
        if validation_command is None:
            raise AttributeError
        return cls(
            conditional_expression=conditional_expression_instance,
            arg_expressions=arg_expression_instances,
            command=str(validation_command),
            arg_values=getattr(expression, "validation_arg_values"),
            arg_columns=getattr(expression, "validation_arg_source_paths"),
            subject=getattr(expression, "validation_subject_source_paths"),
        )


class ValidationDesign(BaseModel):
    name: str
    error_level: ValidationErrorLevel
    expression: ValidationExpression

    @classmethod
    def from_peh(cls, validation_design: peh.ValidationDesign) -> "ValidationDesign":
        error_level = getattr(validation_design, "error_level", None)
        error_level = convert_peh_validation_error_level_to_validation_dto_error_level(error_level)
        expression = getattr(validation_design, "validation_expression", None)
        if expression is None:
            raise AttributeError
        expression = ValidationExpression.from_peh(expression)
        name = getattr(validation_design, "validation_name", None)
        if name is None:
            name = str(uuid.uuid4())
        return cls(
            name=name,
            error_level=error_level,
            expression=expression,
        )

    @classmethod
    def list_from_metadata(cls, metadata: list[Any]) -> "ValidationDesign":
        expression_list = []
        for metadatum in metadata:
            match metadatum.field.lower():
                case "min":
                    expression_list.append(
                        ValidationExpression.from_peh(
                            peh.ValidationExpression(
                                validation_command=peh.ValidationCommand.is_greater_than_or_equal_to,
                                validation_arg_values=[Decimal(metadatum.value)],
                            )
                        )
                    )
                case "max":
                    expression_list.append(
                        ValidationExpression.from_peh(
                            peh.ValidationExpression(
                                validation_command=peh.ValidationCommand.is_less_than_or_equal_to,
                                validation_arg_values=[Decimal(metadatum.value)],
                            )
                        )
                    )
        return [
            cls(name=metadatum.field.lower(), error_level=ValidationErrorLevel.ERROR, expression=expression)
            for expression in expression_list
        ]


class ColumnValidation(BaseModel):
    unique_name: str
    data_type: str
    required: bool
    nullable: bool
    validations: list[ValidationDesign] | None = None

    @classmethod
    def from_peh(cls, column_name: str, observable_property: peh.ObservableProperty) -> "ColumnValidation":
        required = observable_property.default_required
        nullable = not required
        validations = []
        if validation_designs := getattr(observable_property, "validation_designs", None):
            validations.extend([ValidationDesign.from_peh(vd) for vd in validation_designs])
        if value_metadata := getattr(observable_property, "value_metadata", None):
            validations.extend(ValidationDesign.list_from_metadata(value_metadata))
        if getattr(observable_property, "categorical", None):
            validations.append(
                ValidationDesign.from_peh(
                    peh.ValidationDesign(
                        validation_name="check_categorical",
                        validation_expression=peh.ValidationExpression(
                            validation_command=peh.ValidationCommand.is_in,
                            validation_arg_values=[
                                vo.key for vo in getattr(observable_property, "value_options", None)
                            ],
                        ),
                        validation_error_level=peh.ValidationErrorLevel.error,
                    )
                )
            )

        assert isinstance(observable_property.value_type, str)
        data_type = convert_peh_value_type_to_validation_dto_datatype(observable_property.value_type)
        assert isinstance(required, bool)
        return cls(
            unique_name=column_name,
            data_type=data_type,
            required=required,
            nullable=nullable,
            validations=validations,
        )


class ValidationConfig(BaseModel):
    name: str
    columns: list[ColumnValidation]
    identifying_column_names: list[str] | None = None
    validations: list[ValidationDesign] | None = None

    @classmethod
    def from_peh(
        cls,
        oep_set: peh.ObservableEntityPropertySet,
        oep_set_name: str,
        observable_property_dict: Dict[str, peh.ObservableProperty],
    ) -> "ValidationConfig":
        if isinstance(oep_set.required_observable_property_id_list, list) and isinstance(
            oep_set.optional_observable_property_id_list, list
        ):
            all_op_ids = (
                oep_set.identifying_observable_property_id_list
                + oep_set.required_observable_property_id_list
                + oep_set.optional_observable_property_id_list
            )
        else:
            raise TypeError

        columns = [
            ColumnValidation.from_peh(op_id, observable_property_dict[op_id])
            for op_id in all_op_ids
            if op_id in observable_property_dict
        ]

        # Optional: log or raise error if some op_ids are missing
        missing = set(all_op_ids) - observable_property_dict.keys()
        if missing:
            raise ValueError(f"Missing observable properties for IDs: {missing}")

        assert isinstance(oep_set.identifying_observable_property_id_list, list)
        return cls(
            name=oep_set_name,
            columns=columns,
            identifying_column_names=oep_set.identifying_observable_property_id_list,
            validations=[],  # TODO: handle dataset-level validations if any
        )

    @classmethod
    def from_observation(
        cls,
        observation: peh.Observation,
        observable_property_dict: dict[str, peh.ObservableProperty],
    ) -> Generator[tuple[str, ValidationConfig], None, None]:
        observation_design = observation.observation_design
        observable_entity_property_sets = getattr(observation_design, "observable_entity_property_sets", None)
        if observable_entity_property_sets is None:
            logger.error(
                "Cannot generate a ValidationConfig from an ObservationDesign that does not contain observable_entity_property_sets"
            )
            raise AttributeError
        for cnt, oep_set in enumerate(observable_entity_property_sets):
            oep_set_name = f"{oep_set}_{cnt:0>2}"
            yield (
                oep_set_name,
                ValidationConfig.from_peh(
                    oep_set,
                    oep_set_name,
                    observable_property_dict,
                ),
            )


class ValidationDTO(BaseModel):
    config: ValidationConfig
    data: dict[str, Any]
