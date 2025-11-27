from __future__ import annotations

import logging
import uuid

from datetime import datetime
from decimal import Decimal, getcontext
from pydantic import BaseModel, field_validator
from typing import Generic, Any, Dict, Sequence, TYPE_CHECKING

from pypeh.core.cache.containers import CacheContainerView
from pypeh.core.models.typing import CategoricalString, T_DataType
from pypeh.core.models.constants import ValidationErrorLevel
from peh_model import pydanticmodel_v2 as pehs
from peh_model import peh


if TYPE_CHECKING:
    from pypeh.core.models.internal_data_layout import Dataset

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


def infer_type(value: str) -> str:
    val = value.strip()
    # Boolean check
    if val.lower() in ["true", "false"]:
        return "boolean"
    # Integer / Float check
    try:
        num = float(val)
        # If it has no decimal part, it's an integer
        if num.is_integer():
            return "integer"
        return "float"
    except ValueError:
        pass
    # Date / Datetime check
    date_formats = [
        ("%Y-%m-%d", "date"),
        ("%Y-%m-%d %H:%M:%S", "datetime"),
        ("%Y-%m-%dT%H:%M:%S", "datetime"),  # ISO-like
        ("%Y-%m-%d %H:%M:%S%z", "datetime"),
        ("%Y-%m-%dT%H:%M:%S%z", "datetime"),
    ]
    for fmt, t in date_formats:
        try:
            datetime.strptime(val, fmt)
            return t
        except ValueError:
            continue

    # Fallback
    return "string"


def cast_to_peh_value_type(value: str, peh_value_type: str | None) -> Any:
    # valid input values: "string", "boolean", "date", "datetime", "decimal", "float", "integer"
    if not isinstance(value, str):
        return value
    if isinstance(value, CategoricalString):
        return str(value)

    if peh_value_type is None:
        peh_value_type = infer_type(value)

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
    # TODO: Evaluate the need for a two-level field_reference implementation in ValidationExpression.arg_columns
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

        subject_contextual_field_references = getattr(
            expression, "validation_subject_contextual_field_references", None
        )
        # TODO: extract type from dataset schema
        arg_type = None
        observable_property_id_based_subject_contextual_field_references = []
        if subject_contextual_field_references:
            arg_types = set()
            if observable_property_short_name_dict is not None:
                for contextual_field_reference in [
                    ssp for ssp in subject_contextual_field_references if ssp is not None
                ]:
                    obs_prop = observable_property_short_name_dict.get(contextual_field_reference.field_label, None)
                    if obs_prop is None:
                        me = f"Could not find contextual_field_reference.field_label {contextual_field_reference.field_label} in observable_property_short_name_dict"
                        logger.error(me)
                        raise ValueError(me)
                    observable_property_id_based_subject_contextual_field_references.append(obs_prop.id)
                    new_arg_type = getattr(obs_prop, "value_type", None)
                    arg_types.add(new_arg_type)
            if len(arg_types) != 1:
                logger.error(
                    f"More than one type corresponds to the ObservableProperties in validation_subject_contextual_field_references: {arg_types}"
                )
                raise ValueError
            arg_type = arg_types.pop()

        arg_values = getattr(expression, "validation_arg_values", None)
        if arg_values is not None:
            assert isinstance(arg_values, Sequence)
            try:
                arg_values = [cast_to_peh_value_type(arg_value, arg_type) for arg_value in arg_values]
            except Exception as e:
                logger.error(f"Could not cast values in {arg_values} to {arg_type}: {e}")
                raise

        # TODO: add support for cross-dataset column references
        arg_columns = [fr.field_label for fr in getattr(expression, "validation_arg_contextual_field_references", None)]
        validation_arg_contextual_field_references = []
        if arg_columns is not None:
            assert isinstance(arg_values, Sequence)
            validation_arg_contextual_field_references = [
                observable_property_short_name_dict(c).id for c in arg_columns
            ]

        return cls(
            conditional_expression=conditional_expression_instance,
            arg_expressions=arg_expression_instances,
            command=validation_command,
            arg_values=arg_values,
            arg_columns=validation_arg_contextual_field_references,
            subject=observable_property_id_based_subject_contextual_field_references,
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
            expression,
            observable_property_short_name_dict=observable_property_short_name_dict,
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
    def from_observable_property(
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
            value_options = getattr(observable_property, "value_options", None)
            assert (
                value_options is not None
            ), f"ObservableProperty {observable_property} lacks `value_options` for categorical type"
            validation_arg_values: list[str] = [CategoricalString(vo.key) for vo in value_options]
            validations.append(
                ValidationDesign.from_peh(
                    peh.ValidationDesign(
                        validation_name="check_categorical",
                        validation_expression=peh.ValidationExpression(
                            validation_command=peh.ValidationCommand.is_in,
                            validation_arg_values=validation_arg_values,
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
    dependent_observable_property_ids: set[str] | None = None

    @classmethod
    def get_sample_matrix_validations_dict_from_section_labels(
        cls,
        data_import_config: peh.DataImportConfig,
        data_dict: Dict[str, Dict[str, Sequence] | T_DataType],
        cache_view: CacheContainerView,
    ) -> Dict[str, Sequence[ValidationDesign]] | None:
        # TODO: Make configurable
        SAMPLETIMEPOINT_LABEL_PREFIX = "SAMPLETIMEPOINT_"
        MATRIX_SHORT_NAME = "matrix"

        observable_property_list = cache_view.get_all("ObservableProperty")
        observable_property_short_name_dict = {op.short_name: op for op in observable_property_list}
        matrix_column_name = observable_property_short_name_dict[MATRIX_SHORT_NAME].id

        def get_matrix_values(data_import_config: peh.DataImportConfig, cache_view: CacheContainerView):
            matrix_values = []
            layout = cache_view.get(data_import_config.layout, "DataLayout")
            for section in layout.sections:
                if section.ui_label.find(SAMPLETIMEPOINT_LABEL_PREFIX) >= 0:
                    matrix_values.append(
                        section.ui_label[
                            section.ui_label.find(SAMPLETIMEPOINT_LABEL_PREFIX) + len(SAMPLETIMEPOINT_LABEL_PREFIX) :
                        ]
                    )
            return matrix_values if len(matrix_values) else None

        matrix_values = get_matrix_values(data_import_config, cache_view)

        dataset_validations_dict = {}
        for observation_id, observation_result in data_dict.items():
            if matrix_column_name in observation_result.observed_data.columns:
                dataset_validations = [
                    peh.ValidationDesign(
                        validation_name="check_sample_matrix",
                        validation_expression=peh.ValidationExpression(
                            validation_subject_contextual_field_references=[MATRIX_SHORT_NAME],
                            validation_command=peh.ValidationCommand.is_in,
                            validation_arg_values=matrix_values,
                        ),
                        validation_error_level=peh.ValidationErrorLevel.error,
                    ),
                ]
                dataset_validations_dict[observation_id] = dataset_validations
        return dataset_validations_dict

    @classmethod
    def from_peh(
        cls,
        observation_id: str,
        observable_property_id_selection: Sequence[str],
        observation_design: peh.ObservationDesign | pehs.ObservationDesign,
        observable_property_dict: Dict[str, peh.ObservableProperty | peh.ObservableProperty],
        dataset_validations: Sequence[peh.ValidationDesign] | None = None,
    ) -> "ValidationConfig":
        if isinstance(observation_design.required_observable_property_id_list, list) and isinstance(
            observation_design.optional_observable_property_id_list, list
        ):
            assert isinstance(observation_design.identifying_observable_property_id_list, list)
            assert isinstance(observation_design.required_observable_property_id_list, list)
            assert isinstance(observation_design.optional_observable_property_id_list, list)
            all_op_ids = (
                observation_design.identifying_observable_property_id_list
                + observation_design.required_observable_property_id_list
                + observation_design.optional_observable_property_id_list
            )
        else:
            raise TypeError
        observable_property_short_name_dict = {op.short_name: op for op in observable_property_dict.values()}
        columns = [
            ColumnValidation.from_observable_property(
                op_id, observable_property_dict[op_id], observable_property_short_name_dict
            )
            for op_id in all_op_ids
            if op_id in observable_property_dict and op_id in observable_property_id_selection
        ]

        # figure out dependent_observable_property_ids
        observable_property_id_set = set(all_op_ids)
        dependent_observable_property_ids = set()
        expression_stack = []
        for column_validation in columns:
            validation_designs = getattr(column_validation, "validations", None)
            if validation_designs is None:
                continue
            for validation_design in validation_designs:
                expression = getattr(validation_design, "expression", None)
                assert expression is not None
                expression_stack.append(expression)

        while expression_stack:
            expression = expression_stack.pop()
            conditional_expression = expression.conditional_expression
            if conditional_expression is not None:
                expression_stack.append(conditional_expression)
            arg_expressions = expression.arg_expressions
            if arg_expressions is not None:
                for arg_expression in arg_expressions:
                    expression_stack.append(arg_expression)
            arg_columns = expression.arg_columns
            if arg_columns is not None:
                for arg_column in arg_columns:
                    if arg_column not in observable_property_id_set:
                        dependent_observable_property_ids.add(arg_column)
            subject = expression.subject
            if subject is not None:
                for s in subject:
                    if s not in observable_property_id_set:
                        dependent_observable_property_ids.add(s)

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
            dependent_observable_property_ids=dependent_observable_property_ids,
        )

    @classmethod
    def from_observation(
        cls,
        observation: peh.Observation | pehs.Observation,
        observable_property_id_selection: Sequence[str],
        observable_property_dict: Dict[str, peh.ObservableProperty | peh.ObservableProperty],
        dataset_validations: Sequence[peh.ValidationDesign] | None = None,
    ) -> ValidationConfig:
        observation_design = getattr(observation, "observation_design", None)
        if observation_design is None:
            logger.error(
                "Cannot generate a ValidationConfig from an Observation that does not contain an ObservationDesign"
            )
            raise AttributeError

        validation_config = cls.from_peh(
            observation.id,
            observable_property_id_selection,
            observation_design,
            observable_property_dict,
            dataset_validations,
        )
        return validation_config

    @classmethod
    def extract_dependent_columns(cls, column_validations: list[ColumnValidation]) -> set:
        # TODO: Evaluate the need for a two-level field_reference implementation in ValidationExpression.arg_columns
        ret = set()
        expression_stack = []

        for column_validation in column_validations:
            validation_designs = getattr(column_validation, "validations", None)
            if validation_designs is None:
                continue
            for validation_design in validation_designs:
                expression = getattr(validation_design, "expression", None)
                assert expression is not None
                expression_stack.append(expression)

        while expression_stack:
            expression = expression_stack.pop()
            assert isinstance(expression, ValidationExpression)
            conditional_expression = expression.conditional_expression
            if conditional_expression is not None:
                expression_stack.append(conditional_expression)
            arg_expressions = expression.arg_expressions
            if arg_expressions is not None:
                for arg_expression in arg_expressions:
                    expression_stack.append(arg_expression)
            arg_columns = expression.arg_columns
            if arg_columns is not None:
                for arg_column in arg_columns:
                    ret.add(arg_column)
            subject = expression.subject
            if subject is not None:
                for s in subject:
                    ret.add(s)

        return ret

    @classmethod
    def from_dataset(
        cls,
        dataset: Dataset[T_DataType],
        cache_view: CacheContainerView,
        dataset_validations: Sequence[ValidationDesign] | None = None,
    ) -> ValidationConfig:
        # TODO: remove observable_property_short_name_dict: replace with proper contextual_field_references
        # source path is dataset depedent
        observable_property_short_name_dict = {op.short_name: op for op in cache_view.get_all("ObservableProperty")}
        dataset_series = getattr(dataset, "part_of")
        assert dataset_series is not None
        # use typing information: dict uses {dataset_series_label: {dataset_label: type}}
        # can then be accessed with contextual_field_references
        # TODO: dataset_series_type_info = dataset_series.get_type_annotations()

        column_validations = []
        non_empty_columns = dataset.non_empty
        assert non_empty_columns is not None
        for non_empty_column in non_empty_columns:
            dataset_element = dataset.get_schema_element(non_empty_column)
            assert dataset_element is not None
            observable_property_id = dataset_element.observable_property_id
            observable_property = cache_view.get(observable_property_id, "ObservableProperty")
            assert isinstance(observable_property, peh.ObservableProperty)
            # TODO: should be ColumnValidation.from_dataset_element
            column_validation = ColumnValidation.from_observable_property(
                column_name=non_empty_column,
                observable_property=observable_property,
                short_name_dict=observable_property_short_name_dict,
            )
            column_validations.append(column_validation)

        dependent_observable_property_ids = cls.extract_dependent_columns(column_validations)
        obs_prop_in_dataset = set(dataset.get_observable_property_ids())
        cross_dataset_dependent_observable_property_ids = dependent_observable_property_ids - obs_prop_in_dataset

        peh_dataset_validations = None
        if dataset_validations is not None:
            peh_dataset_validations = list(dataset_validations)

        return cls(
            name=dataset.label,
            columns=column_validations,
            identifying_column_names=dataset.schema.primary_keys,
            validations=peh_dataset_validations,
            dependent_observable_property_ids=cross_dataset_dependent_observable_property_ids,
        )


class ValidationDTO(BaseModel):
    config: ValidationConfig
    data: dict[str, Any]
