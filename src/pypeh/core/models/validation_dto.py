from __future__ import annotations

import logging
import uuid

from decimal import Decimal, getcontext
from pydantic import BaseModel, field_validator
from typing import Generic, Any, Dict, Generator, Sequence

from pypeh.core.models.typing import T_DataType
from pypeh.core.models.constants import ValidationErrorLevel
from peh_model import pydanticmodel_v2 as pehs
from peh_model import peh

logger = logging.getLogger(__name__)


def get_max_decimal_value():
    ctx = getcontext()
    precision = ctx.prec
    emax = ctx.Emax

    max_digits = "9" * precision
    max_value = Decimal(f"{max_digits}E{emax}")
    return max_value


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
    # valid input values: "string", "boolean", "date", "datetime", "decimal", "integer", "float"
    # valid return values: 'date', 'datetime', 'boolean', 'decimal', 'integer', 'varchar', 'float', or 'categorical'
    if peh_value_type is None:
        return None
    else:
        match peh_value_type:
            case "decimal":
                logger.info("Casting decimal to float")
                return "float"
            case "boolean" | "date" | "datetime" | "float" | "string" | "integer":
                return peh_value_type
            case _:
                raise ValueError(f"Invalid data type encountered: {peh_value_type}")


def cast_to_peh_value_type(value: Any, peh_value_type: str | None) -> Any:
    # valid input values: "string", "boolean", "date", "datetime", "decimal", "float"
    if peh_value_type is None:
        return value
    else:
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


class ValidationExpression(BaseModel):
    conditional_expression: ValidationExpression | None = None
    arg_expressions: list[ValidationExpression] | None = None
    command: str
    arg_values: list[Any] | None = None
    arg_columns: list[str] | None = None
    subject: list[str] | None = None

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
        observable_property_short_name_dict: dict | None = None,
    ) -> "ValidationExpression":
        conditional_expression = getattr(expression, "validation_condition_expression")
        conditional_expression_instance = None
        if conditional_expression is not None:
            conditional_expression_instance = ValidationExpression.from_peh(
                conditional_expression, observable_property_short_name_dict=observable_property_short_name_dict
            )
        arg_expressions = getattr(expression, "validation_arg_expressions")
        arg_expression_instances = None
        if arg_expressions is not None:
            arg_expression_instances = [
                ValidationExpression.from_peh(
                    nested_expr, observable_property_short_name_dict=observable_property_short_name_dict
                )
                for nested_expr in arg_expressions
            ]
        validation_command = getattr(expression, "validation_command", "conjunction")
        arg_values = getattr(expression, "validation_arg_values", None)
        source_paths = getattr(expression, "validation_subject_source_paths", None)
        arg_type = None
        if source_paths:
            arg_types = set()
            if observable_property_short_name_dict is not None:
                for source_path in source_paths:
                    obs_prop = observable_property_short_name_dict.get(source_path, None)
                    if source_path is None:
                        me = f"Could not find validation_subject_source_path with short_name {source_path}"
                        logger.error(me)
                        raise ValueError(me)
                    new_arg_type = getattr(obs_prop, "value_type", str)
                    assert new_arg_type is not None
                    arg_types.add(new_arg_type)
            if len(arg_types) != 1:
                logger.error(
                    f"More than one type corresponds to the ObservableProperties in validation_source_paths: {arg_types}"
                )
                raise ValueError
            arg_type = arg_types.pop()
        if arg_values is not None:
            assert isinstance(arg_values, Sequence)
            try:
                arg_values = [cast_to_peh_value_type(arg_value, arg_type) for arg_value in arg_values]
            except Exception as e:
                logger.error(f"Could not cast values in {arg_values} to {arg_type}: {e}")
                raise
        return cls(
            conditional_expression=conditional_expression_instance,
            arg_expressions=arg_expression_instances,
            command=validation_command,
            arg_values=arg_values,
            arg_columns=getattr(expression, "validation_arg_source_paths"),
            subject=getattr(expression, "validation_subject_source_paths"),
        )


class ValidationDesign(BaseModel):
    name: str
    error_level: ValidationErrorLevel
    expression: ValidationExpression

    @classmethod
    def from_peh(
        cls,
        validation_design: peh.ValidationDesign | pehs.ValidationDesign,
        observable_property_short_name_dict: dict | None = None,
        layout_section: peh.DataLayoutSection | None = None,
    ) -> "ValidationDesign":
        error_level = getattr(validation_design, "error_level", None)
        error_level = convert_peh_validation_error_level_to_validation_dto_error_level(error_level)
        expression = getattr(validation_design, "validation_expression", None)
        if expression is None:
            raise AttributeError
        expression = ValidationExpression.from_peh(
            expression, observable_property_short_name_dict=observable_property_short_name_dict
        )
        name = getattr(validation_design, "validation_name", None)
        if name is None:
            name = str(uuid.uuid4())
        return cls(
            name=name,
            error_level=error_level,
            expression=expression,
        )

    @classmethod
    def list_from_metadata(cls, metadata: list[Any]) -> list["ValidationDesign"]:
        expression_list = []
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
                expression_list.append(
                    ValidationExpression.from_peh(
                        pehs.ValidationExpression.model_construct(
                            **{
                                "validation_command": validation_command,
                                "validation_arg_values": [typed_metadata_value],
                            }
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
    def from_peh(
        cls,
        column_name: str,
        observable_property: peh.ObservableProperty | pehs.ObservableProperty,
        short_name_dict: dict,
    ) -> "ColumnValidation":
        required = observable_property.default_required
        nullable = not required
        validations = []
        assert isinstance(observable_property.value_type, str)
        data_type = convert_peh_value_type_to_validation_dto_datatype(observable_property.value_type)
        if validation_designs := getattr(observable_property, "validation_designs", None):
            validations.extend(
                [
                    ValidationDesign.from_peh(vd, observable_property_short_name_dict=short_name_dict)
                    for vd in validation_designs
                ]
            )
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
                    ),
                    observable_property_short_name_dict=short_name_dict,
                )
            )

        assert isinstance(required, bool)
        return cls(
            unique_name=column_name,
            data_type=data_type,
            required=required,
            nullable=nullable,
            validations=validations,
        )


class ValidationConfig(BaseModel, Generic[T_DataType]):
    name: str
    columns: list[ColumnValidation]
    identifying_column_names: list[str] | None = None
    validations: list[ValidationDesign] | None = None

    @classmethod
    def from_peh(
        cls,
        observation_id: str,
        observation_design: peh.ObservationDesign | pehs.ObservationDesign,
        observable_property_dict: Dict[str, peh.ObservableProperty | pehs.ObservableProperty],
        dataset_validations: Sequence[peh.ValidationDesign] | None = None,
    ) -> "ValidationConfig":
        if isinstance(observation_design.required_observable_property_id_list, list) and isinstance(
            observation_design.optional_observable_property_id_list, list
        ):
            all_op_ids = (
                observation_design.identifying_observable_property_id_list
                + observation_design.required_observable_property_id_list
                + observation_design.optional_observable_property_id_list
            )
        else:
            raise TypeError
        observable_property_short_name_dict = {op.short_name: op for op in observable_property_dict.values()}
        columns = [
            ColumnValidation.from_peh(op_id, observable_property_dict[op_id], observable_property_short_name_dict)
            for op_id in all_op_ids
            if op_id in observable_property_dict
        ]

        validations = (
            None
            if dataset_validations is None
            else [ValidationDesign.from_peh(v, observable_property_short_name_dict) for v in dataset_validations]
        )

        # Optional: log or raise error if some op_ids are missing
        missing = set(all_op_ids) - observable_property_dict.keys()
        if missing:
            raise ValueError(f"Missing observable properties for IDs: {missing}")

        assert isinstance(observation_design.identifying_observable_property_id_list, list)
        return cls(
            name=observation_id,
            columns=columns,
            identifying_column_names=observation_design.identifying_observable_property_id_list,
            validations=validations,
        )

    @classmethod
    def get_dataset_validations(
        cls,
        observation_list: Sequence[peh.Observation],
        layout: peh.DataLayout,
        dataset_mapping: Dict[str, Dict[str, str | int]],
    ) -> Sequence[ValidationDesign] | None:
        return None

    @classmethod
    def get_dataset_identifier_consistency_validations_dict(
        cls,
        observation_list: Sequence[peh.Observation],
        layout: peh.DataLayout,
        dataset_mapping: Dict[str, Dict[str, str | int | Dict[str, Sequence[str]]]],
        data_dict: Dict[str, Dict[str, Sequence] | T_DataType],
    ) -> Dict[str, Sequence[ValidationDesign]] | None:
        """Returns validation designs that verify consistency of the entity identifiers in the data."""

        observation_dict = {o.id: o for o in observation_list}
        observation_id_to_dataset_label_dict = {}
        identifying_observation_list = []
        for dataset_label, mapping in dataset_mapping.items():
            if "observation_id" in mapping and mapping["observation_id"] is not None:
                observation_id = mapping["observation_id"]
                observation_id_to_dataset_label_dict[observation_id] = dataset_label
                if str(observation_dict[observation_id].observation_type) == "metadata":
                    identifying_observation_list.append(observation_dict[observation_id])

        entity_type_identifiers_dict = {}
        for observation in identifying_observation_list:
            observable_entity_type = str(observation.observation_design.observable_entity_type)
            if observable_entity_type in entity_type_identifiers_dict.keys():
                raise AttributeError(
                    f"Found multiple competing metadata observations for the {observable_entity_type} EntityType"
                )
            else:
                entity_type_identifiers_dict[observable_entity_type] = {}
                for prop in observation.observation_design.identifying_observable_property_id_list:
                    entity_type_identifiers_dict[observable_entity_type][prop] = list(
                        data_dict[observation_id_to_dataset_label_dict[observation.id]][prop]
                    )

        validation_designs_dict = {}
        for key, mapping in dataset_mapping.items():
            observation_id = mapping["observation_id"]
            observable_entity_type = str(observation_dict[observation_id].observation_design.observable_entity_type)
            validation_designs = []
            # If not a metadata set (which the primary keys were read from), add primary key validation
            if str(observation_dict[observation_id].observation_type) != "metadata":
                for prop, id_list in entity_type_identifiers_dict[observable_entity_type].items():
                    validation_designs.append(
                        peh.ValidationDesign(
                            validation_name=f"check_primarykey_{observation_id.replace(':', '_')}_{prop}",
                            validation_expression=peh.ValidationExpression(
                                validation_subject_source_paths=[prop],
                                validation_command=peh.ValidationCommand.is_in,
                                validation_arg_values=id_list,
                            ),
                            validation_error_level=peh.ValidationErrorLevel.error,
                        )
                    )
            # add foreign key validation
            if "foreign_keys" in mapping:
                for prop, foreign_tuple in mapping["foreign_keys"].items():
                    foreign_entity_type = str(
                        observation_dict[foreign_tuple[0]].observation_design.observable_entity_type
                    )
                    foreign_prop = foreign_tuple[1]
                    validation_designs.append(
                        peh.ValidationDesign(
                            validation_name=f"check_foreignkey_{observation_id.replace(':', '_')}_{prop}",
                            validation_expression=peh.ValidationExpression(
                                validation_subject_source_paths=[prop],
                                validation_command=peh.ValidationCommand.is_in,
                                validation_arg_values=entity_type_identifiers_dict[foreign_entity_type][foreign_prop],
                            ),
                            validation_error_level=peh.ValidationErrorLevel.error,
                        )
                    )
            if len(validation_designs):
                validation_designs_dict[key] = validation_designs

        return validation_designs_dict if len(validation_designs_dict) else None

    @classmethod
    def get_dataset_validations_dict(
        cls,
        observation_list: Sequence[peh.Observation],
        layout: peh.DataLayout,
        dataset_mapping: Dict[str, Dict[str, str | int | Dict[str, Sequence[str]]]],
        data_dict: Dict[str, Dict[str, Sequence] | T_DataType],
    ) -> Dict[str, Sequence[ValidationDesign]] | None:
        observation_design_dict = {
            set_key: [o for o in observation_list if o.id == mapping["observation_id"]][0].observation_design
            for set_key, mapping in dataset_mapping.items()
        }
        layout_section_dict = {
            set_key: [ls for ls in layout.sections if ls.id == mapping["layout_section_id"]][0]
            for set_key, mapping in dataset_mapping.items()
        }

        # Add Sheet labels into the mapping
        # Add Record Identifiers into the mapping
        for set_key, mapping in dataset_mapping.items():
            mapping["sheet_label"] = layout_section_dict[set_key].ui_label
            mapping["identifier_dict"] = {
                iop_id: list(data_dict[mapping["sheet_label"]][iop_id])
                for iop_id in observation_design_dict[set_key].identifying_observable_property_id_list
            }

        sheet_label_mapping = {m["sheet_label"]: m for m in dataset_mapping.values()}
        valid_matrix_list = [
            sl.split("_")[-1] for sl in sheet_label_mapping.keys() if sl.startswith("SAMPLETIMEPOINT_")
        ]
        data_sample_id_list = []
        for matrix in valid_matrix_list:
            data_sample_id_list.extend(sheet_label_mapping[f"SAMPLETIMEPOINT_{matrix}"]["identifier_dict"]["id_sample"])

        # Setup dataset-level validations
        dataset_validations_dict = {}
        for set_key, mapping in dataset_mapping.items():
            dataset_validations = []
            layout_section = layout_section_dict[set_key]
            if layout_section.ui_label == "SAMPLE":
                # SAMPLE > matrix is_in list of SAMPLETIMEPOINT_ suffixes
                dataset_validations.append(
                    peh.ValidationDesign(
                        validation_name="check_sample_matrix",
                        validation_expression=peh.ValidationExpression(
                            validation_subject_source_paths=["matrix"],
                            validation_command=peh.ValidationCommand.is_in,
                            validation_arg_values=valid_matrix_list,
                        ),
                        validation_error_level=peh.ValidationErrorLevel.error,
                    ),
                )
                # SAMPLE > id_sample matrix in SAMPLETIMEPOINT_ matches sheet name suffix
                dataset_validations.append(
                    peh.ValidationDesign(
                        validation_name="check_sample_idsample_from_data",
                        validation_expression=peh.ValidationExpression(
                            validation_subject_source_paths=["id_sample"],
                            validation_command=peh.ValidationCommand.is_in,
                            validation_arg_values=data_sample_id_list,
                        ),
                        validation_error_level=peh.ValidationErrorLevel.error,
                    ),
                )
            dataset_validations_dict[set_key] = dataset_validations
        return dataset_validations_dict

    @classmethod
    def from_observation_list(
        cls,
        observation_list: Sequence[peh.Observation] | Sequence[pehs.Observation],
        observable_property_dict: dict[str, peh.ObservableProperty | peh.ObservableProperty],
        dataset_validations: Sequence[peh.ValidationDesign] | None = None,
    ) -> Generator[tuple[str, ValidationConfig], None, None]:
        for observation in observation_list:
            if getattr(observation, "observation_design", None) is None:
                logger.error(
                    "Cannot generate a ValidationConfig from an Observation that does not contain an ObservationDesign"
                )
                raise AttributeError
            yield (
                observation.id,
                ValidationConfig.from_peh(
                    observation.id,
                    observation.observation_design,
                    observable_property_dict,
                    dataset_validations,
                ),
            )


class ValidationDTO(BaseModel):
    config: ValidationConfig
    data: dict[str, Any]
