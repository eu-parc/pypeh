"""
Each of these Interface subclasses provides a protocol on how
the corresponding Adapter subclass should be implemented.

Usage: TODO: add usage info

"""

from __future__ import annotations
import importlib

import logging

from abc import abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from peh_model import peh
from typing import TYPE_CHECKING, Callable, Generic, Literal, Sequence, cast

from pypeh.core.cache.containers import (
    CacheContainerView,
)
from pypeh.core.models.constants import ObservablePropertyValueType
from pypeh.core.models.dataset_series_mapping import (
    DatasetSeriesConcatenationPlan,
)
from pypeh.core.models.internal_data_layout import (
    Dataset,
    DatasetSchemaElement,
    DatasetSeries,
    ContextIndexProtocol,
    JoinSpec,
)
from pypeh.core.models.typing import T_DataType
from pypeh.core.models import extract_dto, graph, validation_dto
from pypeh.core.utils.function_utils import _extract_callable

if TYPE_CHECKING:
    from typing import Any
    from pypeh.core.models.validation_errors import ValidationErrorReport

logger = logging.getLogger(__name__)


SOURCE_FIELDS_BY_OBSERVABLE_PROPERTY_METADATA_KEY = (
    "source_fields_by_observable_property"
)

JoinHow = Literal[
    "inner",
    "left",
    "right",
    "full",
    "semi",
    "anti",
    "cross",
]
OBSERVATION_ASSEMBLY_JOIN_HOW: JoinHow = "full"

LabelCollisionStrategy = Literal[
    "error",
    "prefix_observable_property_id",
    "prefix_source_dataset",
]


@dataclass(frozen=True)
class SourceFieldRef:
    dataset_label: str
    element_label: str

    @classmethod
    def from_tuple(cls, ref: tuple[str, str]) -> "SourceFieldRef":
        dataset_label, element_label = ref
        return cls(dataset_label=dataset_label, element_label=element_label)


@dataclass(frozen=True)
class JoinEdge:
    left_dataset: str
    left_elements: tuple[str, ...]
    right_dataset: str
    right_elements: tuple[str, ...]

    @classmethod
    def from_join_spec(cls, join_spec: JoinSpec) -> "JoinEdge":
        return cls(
            left_dataset=join_spec.left_dataset,
            left_elements=join_spec.left_elements,
            right_dataset=join_spec.right_dataset,
            right_elements=join_spec.right_elements,
        )

    def orient_to_base(self, base_dataset_label: str) -> "JoinEdge":
        if self.left_dataset == base_dataset_label:
            return self
        if self.right_dataset == base_dataset_label:
            return JoinEdge(
                left_dataset=self.right_dataset,
                left_elements=self.right_elements,
                right_dataset=self.left_dataset,
                right_elements=self.left_elements,
            )
        raise ValueError(
            f"JoinEdge {self} does not reference base dataset "
            f"'{base_dataset_label}'."
        )


@dataclass
class JoinPlan:
    base_dataset_label: str
    edges: list[JoinEdge]
    required_fields_by_dataset: dict[str, set[str]] = field(
        default_factory=dict
    )
    how: JoinHow = "left"

    @classmethod
    def from_join_specs(
        cls,
        *,
        base_dataset_label: str,
        join_specs: list[JoinSpec],
        required_fields_by_dataset: dict[str, set[str]] | None = None,
        how: JoinHow = "left",
    ) -> "JoinPlan":
        edges = [
            JoinEdge.from_join_spec(js).orient_to_base(base_dataset_label)
            for js in join_specs
        ]
        return cls(
            base_dataset_label=base_dataset_label,
            edges=edges,
            required_fields_by_dataset=required_fields_by_dataset or {},
            how=how,
        )


class DataOpsInterface(Generic[T_DataType]):
    """
    Example of DataOps methods
    def validate(self, data: Mapping, config: Mapping):
        pass

    def summarize(self, dat: Mapping, config: Mapping):
        pass
    """

    @classmethod
    def get_default_adapter_class(cls):
        try:
            adapter_module = importlib.import_module(
                "pypeh.adapters.dataops.dataframe_adapter"
            )
            adapter_class = getattr(adapter_module, "DataFrameAdapter")
        except Exception as e:
            logger.error(
                "Exception encountered while attempting to import dataops DataFrameAdapter"
            )
            raise e
        return adapter_class

    def execute_join_plan(
        self,
        base_data: T_DataType,
        datasets: dict[str, T_DataType],
        join_plan: JoinPlan,
    ) -> T_DataType:
        raise NotImplementedError(
            "Method DataOpsInterface.execute_join_plan requires adapter-specific implementation."
        )

    @abstractmethod
    def select_field(self, dataset, field_label: str):
        raise NotImplementedError(
            "Abstract method on class DataOpsInterface was called without supporting implementation."
        )

    @abstractmethod
    def get_element_labels(self, data: T_DataType) -> list[str]:
        raise NotImplementedError(
            "Abstract method on class DataOpsInterface was called without supporting implementation."
        )

    @abstractmethod
    def get_element_values(
        self, data: T_DataType, element_label: str, as_list=True
    ) -> set[str] | list[str]:
        raise NotImplementedError(
            "Abstract method on class DataOpsInterface was called without supporting implementation."
        )

    @abstractmethod
    def check_element_has_empty_values(
        self, data: T_DataType, element_label: str
    ) -> bool:
        raise NotImplementedError(
            "Abstract method on class DataOpsInterface was called without supporting implementation."
        )

    @abstractmethod
    def check_element_has_only_empty_values(
        self, data: T_DataType, element_label: str
    ) -> bool:
        raise NotImplementedError(
            "Abstract method on class DataOpsInterface was called without supporting implementation."
        )

    @abstractmethod
    def subset(
        self,
        data: T_DataType,
        element_group: list[str],
        id_group: list[tuple[Any]] | None = None,
        identifying_elements: list[str] | None = None,
    ) -> T_DataType: ...

    def relabel(
        self, data: T_DataType, element_mapping: dict[str, str]
    ) -> T_DataType: ...

    @abstractmethod
    def collect(self, datasets: dict):
        raise NotImplementedError(
            "Abstract method on class DataOpsInterface was called without supporting implementation."
        )

    @abstractmethod
    def concatenate_data(self, datasets: list[T_DataType]) -> T_DataType:
        raise NotImplementedError(
            "Abstract method on class DataOpsInterface was called without supporting implementation."
        )

    @abstractmethod
    def type_mapper(self, peh_value_type: str | ObservablePropertyValueType):
        raise NotImplementedError(
            "Abstract method on class DataOpsInterface was called without supporting implementation."
        )

    @staticmethod
    def _scalar_type_names(mapped_type, peh_value_type) -> set[str]:
        type_names = {
            str(mapped_type).lower(),
            str(peh_value_type).lower(),
        }
        mapped_type_name = getattr(mapped_type, "__name__", None)
        if mapped_type_name is not None:
            type_names.add(mapped_type_name.lower())
        value_type_value = getattr(peh_value_type, "value", None)
        if value_type_value is not None:
            type_names.add(str(value_type_value).lower())
        return type_names

    def _resolve_scalar_value(self, value, value_type):
        if value_type is None:
            raise ValueError(
                "Scalar CalculationKeywordArguments require value_type."
            )

        mapped_type = self.type_mapper(value_type)
        type_names = self._scalar_type_names(mapped_type, value_type)

        if "string" in type_names or "categorical" in type_names:
            return str(value)
        if "boolean" in type_names or "bool" in type_names:
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                lower_value = value.strip().lower()
                if lower_value in {"true", "1", "yes"}:
                    return True
                if lower_value in {"false", "0", "no"}:
                    return False
            return bool(value)
        if "integer" in type_names or "int64" in type_names:
            return int(value)
        if (
            "float" in type_names
            or "decimal" in type_names
            or "float64" in type_names
        ):
            return float(value)

        return value

    def matches_schema(
        self,
        raw_data_dict: dict[str, T_DataType],
        dataset_series: DatasetSeries,
    ) -> bool:
        ret = True
        for dataset_label in dataset_series.parts:
            if dataset_label not in raw_data_dict:
                return False
            dataset = dataset_series[dataset_label]
            assert dataset is not None
            raw_data = raw_data_dict[dataset_label]
            raw_data_labels = set(self.get_element_labels(raw_data))
            ret = set(dataset.get_element_labels()) == raw_data_labels

        return ret

    @staticmethod
    def _observable_property_element_label(
        observable_property: peh.ObservableProperty,
    ) -> str:
        element_label = observable_property.short_name
        if element_label is None:
            element_label = observable_property.ui_label
        if element_label is None:
            element_label = observable_property.id
        assert isinstance(element_label, str)
        return element_label

    @staticmethod
    def _identifier_tail(identifier: str) -> str:
        return identifier.rsplit("/", 1)[-1].rsplit(":", 1)[-1]

    def _infer_source_dataset_label_for_calculation(
        self,
        observable_property: peh.ObservableProperty,
        observable_property_spec: peh.ObservablePropertySpecification,
        source_dataset_series: DatasetSeries | None,
    ) -> str:
        if source_dataset_series is None:
            raise ValueError(
                "Cannot use target label collision strategy "
                "'prefix_source_dataset' without a source DatasetSeries."
            )
        calculation_design = observable_property_spec.calculation_design
        if calculation_design is None:
            raise ValueError(
                "Cannot use target label collision strategy "
                "'prefix_source_dataset' for observable property "
                f"{observable_property.id!r} because it has no calculation "
                "design."
            )
        assert isinstance(calculation_design, peh.CalculationDesign)
        calculation_implementation = (
            calculation_design.calculation_implementation
        )
        assert isinstance(
            calculation_implementation,
            peh.CalculationImplementation,
        )
        function_kwargs = calculation_implementation.function_kwargs or []

        source_dataset_labels: set[str] = set()
        for function_kwarg in function_kwargs:
            assert isinstance(function_kwarg, peh.CalculationKeywordArgument)
            source_field_ref = getattr(
                function_kwarg, "contextual_field_reference", None
            )
            if source_field_ref is None:
                continue
            assert isinstance(source_field_ref, peh.ContextualFieldReference)
            source_observation_id = source_field_ref.dataset_label
            source_observable_property_id = source_field_ref.field_label
            assert source_observation_id is not None
            assert source_observable_property_id is not None
            source_dataset_label, _ = source_dataset_series.context_lookup(
                source_observation_id,
                source_observable_property_id,
            )
            source_dataset = source_dataset_series[source_dataset_label]
            if source_dataset is not None:
                source_fields = source_dataset.metadata.get(
                    SOURCE_FIELDS_BY_OBSERVABLE_PROPERTY_METADATA_KEY,
                    {},
                )
                source_field = source_fields.get(source_observable_property_id)
                if source_field is not None:
                    source_dataset_label = source_field["dataset_label"]
            source_dataset_labels.add(source_dataset_label)

        if len(source_dataset_labels) != 1:
            raise ValueError(
                "Cannot resolve target label collision for observable "
                f"property {observable_property.id!r} using source dataset "
                f"prefix; expected one source dataset, found "
                f"{sorted(source_dataset_labels)!r}."
            )
        return next(iter(source_dataset_labels))

    def _resolve_target_element_label_collision(
        self,
        element_label: str,
        observable_property: peh.ObservableProperty,
        observable_property_spec: peh.ObservablePropertySpecification,
        *,
        label_collision_strategy: LabelCollisionStrategy,
        source_dataset_series: DatasetSeries | None,
    ) -> str:
        if label_collision_strategy == "prefix_observable_property_id":
            prefix = self._identifier_tail(observable_property.id)
        elif label_collision_strategy == "prefix_source_dataset":
            prefix = self._infer_source_dataset_label_for_calculation(
                observable_property,
                observable_property_spec,
                source_dataset_series,
            )
        else:
            raise NotImplementedError(
                "Unsupported target label collision strategy "
                f"{label_collision_strategy!r}."
            )
        return f"{prefix}__{element_label}"

    @staticmethod
    def _raise_target_element_label_collision(
        observation: peh.Observation,
        element_label: str,
        observable_properties: Sequence[peh.ObservableProperty],
    ) -> None:
        observable_property_ids = [
            observable_property.id
            for observable_property in observable_properties
        ]
        raise ValueError(
            f"Observation {observation.id!r} resolves multiple observable "
            f"properties to element label {element_label!r}: "
            f"{observable_property_ids!r}."
        )

    @staticmethod
    def _raise_resolved_target_element_label_collision(
        observation: peh.Observation,
        element_label: str,
    ) -> None:
        raise ValueError(
            f"Observation {observation.id!r} resolves target element label "
            f"{element_label!r} more than once after collision resolution."
        )

    def extract_labeled_observable_property_specifications(
        self,
        observation: peh.Observation,
        cache_view: CacheContainerView,
        *,
        label_collision_strategy: LabelCollisionStrategy = "error",
        source_dataset_series: DatasetSeries | None = None,
    ) -> dict[str, peh.ObservablePropertySpecification]:
        ret: dict[str, peh.ObservablePropertySpecification] = {}
        observation_design_id = observation.observation_design
        assert isinstance(observation_design_id, str)
        observation_design = cache_view.require(
            observation_design_id, "ObservationDesign"
        )
        assert isinstance(observation_design, peh.ObservationDesign)
        observable_property_specs = (
            observation_design.observable_property_specifications
        )
        assert observable_property_specs is not None
        specs_by_element_label: dict[
            str,
            list[
                tuple[
                    peh.ObservableProperty, peh.ObservablePropertySpecification
                ]
            ],
        ] = defaultdict(list)
        for observable_property_spec in observable_property_specs:
            assert isinstance(
                observable_property_spec, peh.ObservablePropertySpecification
            )
            assert isinstance(
                observable_property_spec.observable_property, str
            )
            observable_property = cache_view.require(
                observable_property_spec.observable_property,
                "ObservableProperty",
            )
            assert isinstance(
                observable_property, peh.ObservableProperty
            ), f"Could not find observable property with id {observable_property_spec.observable_property} in cache."
            element_label = self._observable_property_element_label(
                observable_property
            )
            specs_by_element_label[element_label].append(
                (observable_property, observable_property_spec)
            )

        for element_label, specs in specs_by_element_label.items():
            if len(specs) == 1:
                if element_label in ret:
                    self._raise_resolved_target_element_label_collision(
                        observation, element_label
                    )
                ret[element_label] = specs[0][1]
                continue
            if label_collision_strategy == "error":
                self._raise_target_element_label_collision(
                    observation,
                    element_label,
                    [observable_property for observable_property, _ in specs],
                )
            for observable_property, observable_property_spec in specs:
                resolved_element_label = (
                    self._resolve_target_element_label_collision(
                        element_label,
                        observable_property,
                        observable_property_spec,
                        label_collision_strategy=label_collision_strategy,
                        source_dataset_series=source_dataset_series,
                    )
                )
                if resolved_element_label in ret:
                    self._raise_resolved_target_element_label_collision(
                        observation, resolved_element_label
                    )
                ret[resolved_element_label] = observable_property_spec
        return ret

    def get_dataset_by_observation_id(
        self, dataset_series: DatasetSeries, observation_id: str
    ) -> Dataset:
        gen = dataset_series.get_datasets_by_observation(observation_id)
        dataset = next(gen)
        try:
            _ = next(gen)
            raise AssertionError(
                "Expected only one dataset, but generator yielded more"
            )
        except StopIteration:
            pass
        return dataset

    def _build_unique_label(
        self,
        candidate: str,
        used_labels: set[str],
        dataset_label: str | None = None,
        observable_property_id: str | None = None,
        label_collision_strategy: LabelCollisionStrategy = (
            "prefix_source_dataset"
        ),
    ) -> str:
        if candidate not in used_labels:
            return candidate

        if label_collision_strategy == "error":
            raise ValueError(
                f"Output field label {candidate!r} would collide while "
                "splitting DatasetSeries by observation."
            )

        if label_collision_strategy == "prefix_observable_property_id":
            prefix = (
                self._identifier_tail(observable_property_id)
                if observable_property_id is not None
                else dataset_label
            )
        else:
            prefix = dataset_label if dataset_label is not None else "field"
        if prefix is None:
            prefix = "field"
        numbered_prefix = f"{prefix}__{candidate}"
        if numbered_prefix not in used_labels:
            return numbered_prefix

        idx = 2
        while True:
            unique = f"{numbered_prefix}_{idx}"
            if unique not in used_labels:
                return unique
            idx += 1

    @staticmethod
    def _ensure_split_indices(
        dataset_series: DatasetSeries[T_DataType],
    ) -> None:
        if len(dataset_series._obs_index) == 0:
            dataset_series.build_observation_index()
        if len(dataset_series._context_index) == 0:
            raise ValueError(
                "Cannot split DatasetSeries by observation without a context "
                "index. Add observations through `DatasetSeries.add_observation` "
                "or populate `_context_index` first."
            )

    @staticmethod
    def _collect_observable_property_context(
        dataset_series: DatasetSeries[T_DataType],
        observation_id: str,
        source_dataset_labels: list[str],
    ) -> dict[str, SourceFieldRef]:
        observable_property_context: dict[str, SourceFieldRef] = {}
        for (
            context_observation_id,
            observable_property_id,
        ), contextual_ref in dataset_series._context_index.items():
            if context_observation_id != observation_id:
                continue
            source_label, element_label = contextual_ref
            if source_label not in source_dataset_labels:
                continue
            observable_property_context[observable_property_id] = (
                SourceFieldRef(
                    dataset_label=source_label,
                    element_label=element_label,
                )
            )
        if len(observable_property_context) == 0:
            raise ValueError(
                f"Could not determine contextual fields for observation "
                f"'{observation_id}'."
            )
        return observable_property_context

    @staticmethod
    def _collect_required_fields_by_dataset(
        observable_property_context: dict[str, SourceFieldRef],
    ) -> dict[str, set[str]]:
        required_fields_by_dataset: dict[str, set[str]] = defaultdict(set)
        for source_ref in observable_property_context.values():
            required_fields_by_dataset[source_ref.dataset_label].add(
                source_ref.element_label
            )
        return required_fields_by_dataset

    @staticmethod
    def _pick_base_dataset_label(
        source_dataset_labels: list[str],
        required_fields_by_dataset: dict[str, set[str]],
    ) -> str:
        source_order = {
            label: idx for idx, label in enumerate(source_dataset_labels)
        }
        return max(
            source_dataset_labels,
            key=lambda label: (
                len(required_fields_by_dataset.get(label, set())),
                -source_order[label],
            ),
        )

    @staticmethod
    def _resolve_join_specs(
        dataset_series: DatasetSeries[T_DataType],
        observation_id: str,
        source_dataset_labels: list[str],
        base_dataset_label: str,
        required_fields_by_dataset: dict[str, set[str]],
    ) -> tuple[list[JoinSpec], dict[SourceFieldRef, SourceFieldRef]]:
        raw_join_specs: list[JoinSpec] = []
        right_to_left_join_key: dict[SourceFieldRef, SourceFieldRef] = {}

        for source_label in source_dataset_labels:
            if source_label == base_dataset_label:
                continue
            join_spec = dataset_series.resolve_join(
                base_dataset_label, source_label
            )
            if join_spec is None:
                raise ValueError(
                    f"Could not resolve join path between datasets "
                    f"'{base_dataset_label}' and '{source_label}' for "
                    f"observation '{observation_id}'."
                )
            raw_join_specs.append(join_spec)
            required_fields_by_dataset[join_spec.left_dataset].update(
                join_spec.left_elements
            )
            required_fields_by_dataset[join_spec.right_dataset].update(
                join_spec.right_elements
            )
            for left_element, right_element in zip(
                join_spec.left_elements, join_spec.right_elements
            ):
                right_to_left_join_key[
                    SourceFieldRef(join_spec.right_dataset, right_element)
                ] = SourceFieldRef(join_spec.left_dataset, left_element)

        return raw_join_specs, right_to_left_join_key

    def _build_field_label_mapping(
        self,
        source_dataset_labels: list[str],
        required_fields_by_dataset: dict[str, set[str]],
        label_collision_strategy: LabelCollisionStrategy = (
            "prefix_source_dataset"
        ),
        observable_property_by_source_field: dict[SourceFieldRef, str]
        | None = None,
        join_key_aliases: dict[SourceFieldRef, SourceFieldRef] | None = None,
    ) -> dict[SourceFieldRef, str]:
        used_output_labels: set[str] = set()
        field_label_mapping: dict[SourceFieldRef, str] = {}
        join_key_aliases = join_key_aliases or {}
        canonical_join_keys = set(join_key_aliases.values())
        all_source_fields = [
            SourceFieldRef(
                dataset_label=source_label,
                element_label=field_label,
            )
            for source_label in source_dataset_labels
            for field_label in sorted(
                required_fields_by_dataset.get(source_label, set())
            )
        ]

        def assign_unique_label(source_field: SourceFieldRef) -> None:
            unique_label = self._build_unique_label(
                source_field.element_label,
                used_output_labels,
                dataset_label=source_field.dataset_label,
                observable_property_id=(
                    observable_property_by_source_field or {}
                ).get(source_field),
                label_collision_strategy=label_collision_strategy,
            )
            used_output_labels.add(unique_label)
            field_label_mapping[source_field] = unique_label

        for source_field in all_source_fields:
            if source_field in canonical_join_keys:
                assign_unique_label(source_field)

        for source_field in all_source_fields:
            if (
                source_field in canonical_join_keys
                or source_field in join_key_aliases
            ):
                continue
            assign_unique_label(source_field)

        for source_field, canonical_source_field in join_key_aliases.items():
            if source_field not in all_source_fields:
                continue
            canonical_label = field_label_mapping.get(canonical_source_field)
            if canonical_label is None:
                assign_unique_label(canonical_source_field)
                canonical_label = field_label_mapping[canonical_source_field]
            field_label_mapping[source_field] = canonical_label

        return field_label_mapping

    def _prepare_datasets_for_join(
        self,
        dataset_series: DatasetSeries[T_DataType],
        observation_id: str,
        source_dataset_labels: list[str],
        required_fields_by_dataset: dict[str, set[str]],
        field_label_mapping: dict[SourceFieldRef, str],
    ) -> dict[str, T_DataType]:
        datasets_for_join: dict[str, T_DataType] = {}

        for source_label in source_dataset_labels:
            source_dataset = dataset_series[source_label]
            assert source_dataset is not None
            source_data = source_dataset.data
            if source_data is None:
                raise ValueError(
                    f"Dataset '{source_label}' has no data; cannot split "
                    f"observation '{observation_id}'."
                )

            selected_fields = sorted(
                required_fields_by_dataset.get(source_label, set())
            )
            data_subset = self.subset(
                source_data, element_group=selected_fields
            )
            relabel_mapping = {
                field_label: field_label_mapping[
                    SourceFieldRef(source_label, field_label)
                ]
                for field_label in selected_fields
                if field_label_mapping[
                    SourceFieldRef(source_label, field_label)
                ]
                != field_label
            }
            if len(relabel_mapping) > 0:
                data_subset = self.relabel(data_subset, relabel_mapping)
            datasets_for_join[source_label] = data_subset

        return datasets_for_join

    @staticmethod
    def _build_adjusted_join_plan(
        base_dataset_label: str,
        source_dataset_labels: list[str],
        raw_join_specs: list[JoinSpec],
        required_fields_by_dataset: dict[str, set[str]],
        field_label_mapping: dict[SourceFieldRef, str],
        *,
        how: JoinHow,
    ) -> JoinPlan:
        """
        Build a JoinPlan after route-specific field relabeling.

        `split_by_observation` and `extract_from_source` use this helper to
        assemble observation-shaped data across peer source datasets. These
        routes should preserve rows from every participating source dataset, so
        their callers pass `how="full"`. Validation and enrichment build their
        own plans with `how="left"` because they intentionally preserve the row
        set of the dataset being validated or enriched.
        """
        adjusted_join_specs = [
            JoinSpec(
                left_elements=tuple(
                    field_label_mapping[SourceFieldRef(js.left_dataset, el)]
                    for el in js.left_elements
                ),
                left_dataset=js.left_dataset,
                right_elements=tuple(
                    field_label_mapping[SourceFieldRef(js.right_dataset, el)]
                    for el in js.right_elements
                ),
                right_dataset=js.right_dataset,
            )
            for js in raw_join_specs
        ]
        adjusted_required_fields: dict[str, set[str]] = defaultdict(set)
        for source_label in source_dataset_labels:
            adjusted_required_fields[source_label].update(
                field_label_mapping[SourceFieldRef(source_label, field_label)]
                for field_label in required_fields_by_dataset.get(
                    source_label, set()
                )
            )
        return JoinPlan.from_join_specs(
            base_dataset_label=base_dataset_label,
            join_specs=adjusted_join_specs,
            required_fields_by_dataset=adjusted_required_fields,
            how=how,
        )

    @staticmethod
    def _canonical_source_field(
        source_field: SourceFieldRef,
        join_key_aliases: dict[SourceFieldRef, SourceFieldRef],
    ) -> SourceFieldRef:
        return join_key_aliases.get(source_field, source_field)

    def _resolve_output_fields_by_observable_property(
        self,
        observation_id: str,
        observable_property_context: dict[str, SourceFieldRef],
        right_to_left_join_key: dict[SourceFieldRef, SourceFieldRef],
        field_label_mapping: dict[SourceFieldRef, str],
    ) -> dict[str, str]:
        final_fields_by_observable_property: dict[str, str] = {}
        canonical_source_by_field: dict[str, SourceFieldRef] = {}

        for (
            observable_property_id,
            source_field,
        ) in observable_property_context.items():
            canonical_source = self._canonical_source_field(
                source_field, right_to_left_join_key
            )
            final_field = field_label_mapping[canonical_source]
            existing_source = canonical_source_by_field.get(final_field)
            if (
                existing_source is not None
                and existing_source != canonical_source
            ):
                raise ValueError(
                    f"Observation '{observation_id}' resolves multiple "
                    "unrelated observable properties to the same output field "
                    "after join normalization. This is currently unsupported."
                )
            canonical_source_by_field[final_field] = canonical_source
            final_fields_by_observable_property[observable_property_id] = (
                final_field
            )
        return final_fields_by_observable_property

    def _build_output_dataset_for_observation(
        self,
        target_series: DatasetSeries[T_DataType],
        source_series: DatasetSeries[T_DataType],
        observation_id: str,
        source_dataset_labels: list[str],
        target_dataset_label: str,
        observable_property_context: dict[str, SourceFieldRef],
        final_fields_by_observable_property: dict[str, str],
        final_data: T_DataType,
    ) -> None:
        output_dataset = target_series.add_empty_dataset(
            target_dataset_label,
            metadata={
                "source_datasets": source_dataset_labels,
                "observation_id": observation_id,
                SOURCE_FIELDS_BY_OBSERVABLE_PROPERTY_METADATA_KEY: {},
            },
        )
        output_dataset.observation_ids.add(observation_id)
        output_source_fields = output_dataset.metadata[
            SOURCE_FIELDS_BY_OBSERVABLE_PROPERTY_METADATA_KEY
        ]

        for (
            observable_property_id,
            final_field_label,
        ) in final_fields_by_observable_property.items():
            source_field = observable_property_context[observable_property_id]
            source_label = source_field.dataset_label
            source_field_label = source_field.element_label
            source_dataset = source_series[source_label]
            assert source_dataset is not None
            source_schema_element = source_dataset.get_schema_element_by_label(
                source_field_label
            )
            if source_schema_element is None:
                raise ValueError(
                    f"Schema element '{source_field_label}' missing in "
                    f"dataset '{source_label}'."
                )
            is_primary_key = (
                source_field_label in source_dataset.schema.primary_keys
            )
            if (
                output_dataset.get_schema_element_by_label(final_field_label)
                is None
            ):
                output_dataset.add_observable_property(
                    observable_property_id=observable_property_id,
                    data_type=source_schema_element.data_type,
                    element_label=final_field_label,
                    is_primary_key=is_primary_key,
                )
            elif is_primary_key:
                assert output_dataset.schema is not None
                output_dataset.schema.primary_keys.add(final_field_label)
            target_series._register_observable_property(
                observable_property_id=observable_property_id,
                observation_id=observation_id,
                dataset_label=target_dataset_label,
                element_label=final_field_label,
            )
            output_source_fields[observable_property_id] = {
                "dataset_label": source_label,
                "element_label": source_field_label,
            }

        output_dataset.data = final_data

    @staticmethod
    def _resolve_observation_dataset_label(
        observation: peh.Observation,
        fallback_id: str,
    ) -> str:
        for label_field in ("ui_label", "short_name"):
            label = getattr(observation, label_field, None)
            if isinstance(label, str) and len(label) > 0:
                return label
        return fallback_id

    def _build_target_dataset_labels_by_observation(
        self,
        observation_ids: Sequence[str],
        cache_view: CacheContainerView,
    ) -> dict[str, str]:
        labels_by_observation: dict[str, str] = {}
        observation_by_label: dict[str, str] = {}

        for observation_id in observation_ids:
            observation = cache_view.require(observation_id)
            assert isinstance(observation, peh.Observation)
            label = self._resolve_observation_dataset_label(
                observation, fallback_id=observation_id
            )

            if label in observation_by_label:
                raise ValueError(
                    "Observation labels used as split dataset labels must be "
                    f"unique. Label '{label}' resolved for observations "
                    f"'{observation_by_label[label]}' and "
                    f"'{observation_id}'."
                )

            labels_by_observation[observation_id] = label
            observation_by_label[label] = observation_id

        return labels_by_observation

    def extract_from_source(
        self,
        source: DatasetSeries[T_DataType],
        target: DatasetSeries[T_DataType],
    ) -> DatasetSeries[T_DataType]:
        """
        Reshape `source` data into the shape requested by `target` and attach
        the resulting data to each Dataset in `target.parts`.

        `target._context_index` is the SSOT for what to
        extract: each `(observation_id, observable_property_id) ->
        (target_dataset_label, target_element_label)` entry is resolved
        against `source.context_lookup(observation_id, observable_property_id)`
        to determine which source `(dataset_label, field_label)` provides the
        value. When fields for a single target dataset come from multiple
        source datasets, the existing join helpers shared with
        `split_by_observation` are used to join through foreign keys present
        in the source.
        """
        for target_dataset_label in target.parts:
            target_label_for: dict[SourceFieldRef, str] = {}
            for (
                observation_id,
                observable_property_id,
            ), contextual_ref in target._context_index.items():
                ctx_dataset_label, target_element_label = contextual_ref
                if ctx_dataset_label != target_dataset_label:
                    continue
                source_ref = source.context_lookup(
                    observation_id, observable_property_id
                )
                source_field = SourceFieldRef.from_tuple(source_ref)
                existing = target_label_for.get(source_field)
                if existing is not None and existing != target_element_label:
                    raise ValueError(
                        f"Multiple target outputs in dataset "
                        f"{target_dataset_label!r} resolve to the same source "
                        f"field ({source_field.dataset_label!r}, "
                        f"{source_field.element_label!r}): "
                        f"{existing!r} and {target_element_label!r}."
                    )
                target_label_for[source_field] = target_element_label

            if len(target_label_for) == 0:
                continue

            required_fields_by_dataset: dict[str, set[str]] = defaultdict(set)
            for source_field in target_label_for:
                required_fields_by_dataset[source_field.dataset_label].add(
                    source_field.element_label
                )
            source_dataset_labels = sorted(required_fields_by_dataset.keys())

            sentinel_observation_id = (
                f"<export target dataset {target_dataset_label}>"
            )
            base_dataset_label = self._pick_base_dataset_label(
                source_dataset_labels, required_fields_by_dataset
            )
            raw_join_specs, _ = self._resolve_join_specs(
                source,
                sentinel_observation_id,
                source_dataset_labels,
                base_dataset_label,
                required_fields_by_dataset,
            )

            field_label_mapping: dict[SourceFieldRef, str] = {}
            used_output_labels: set[str] = set(target_label_for.values())
            for source_label in source_dataset_labels:
                for field_label in sorted(
                    required_fields_by_dataset.get(source_label, set())
                ):
                    source_field = SourceFieldRef(
                        dataset_label=source_label,
                        element_label=field_label,
                    )
                    target_label = target_label_for.get(source_field)
                    if target_label is not None:
                        field_label_mapping[source_field] = target_label
                    else:
                        unique = self._build_unique_label(
                            field_label,
                            used_output_labels,
                            dataset_label=source_label,
                        )
                        used_output_labels.add(unique)
                        field_label_mapping[source_field] = unique

            datasets_for_join = self._prepare_datasets_for_join(
                source,
                sentinel_observation_id,
                source_dataset_labels,
                required_fields_by_dataset,
                field_label_mapping,
            )
            base_data = datasets_for_join[base_dataset_label]
            if len(raw_join_specs) > 0:
                join_plan = self._build_adjusted_join_plan(
                    base_dataset_label,
                    source_dataset_labels,
                    raw_join_specs,
                    required_fields_by_dataset,
                    field_label_mapping,
                    how=OBSERVATION_ASSEMBLY_JOIN_HOW,
                )
                joined_data = self.execute_join_plan(
                    base_data=base_data,
                    datasets=datasets_for_join,
                    join_plan=join_plan,
                )
            else:
                joined_data = base_data

            final_target_labels = sorted(set(target_label_for.values()))
            final_data = self.subset(
                joined_data, element_group=final_target_labels
            )
            target.parts[target_dataset_label].data = final_data

        return target

    def concatenate_dataset_series(
        self,
        dataset_series: Sequence[DatasetSeries[T_DataType]],
        *,
        plan: DatasetSeriesConcatenationPlan[T_DataType] | None = None,
        output_label: str | None = None,
    ) -> DatasetSeries[T_DataType]:
        if plan is None:
            plan = DatasetSeriesConcatenationPlan.from_strict_dataset_series(
                dataset_series,
                output_label=output_label,
            )
        ret = DatasetSeries[T_DataType](
            label=plan.output_label,
            metadata={
                "source_dataset_series": [
                    {"label": ref.series_label, "index": ref.series_index}
                    for ref in plan.sources
                ],
                "concatenation_mode": "strict_observable_property_id",
            },
        )

        for dataset_mapping in plan.datasets:
            canonical_ref = dataset_mapping.sources[0]
            canonical_dataset = dataset_series[
                canonical_ref.series_index
            ].parts[canonical_ref.dataset_label]
            output_dataset = Dataset[T_DataType](
                label=dataset_mapping.output_dataset_label,
                schema=dataset_mapping.build_output_schema(canonical_dataset),
                metadata={
                    "source_datasets": [
                        {
                            "series_label": ref.series_label,
                            "series_index": ref.series_index,
                            "dataset_label": ref.dataset_label,
                        }
                        for ref in dataset_mapping.sources
                    ]
                },
            )
            output_observation_ids = set(
                dataset_mapping.output_observation_ids
            )
            data_parts: list[T_DataType] = []
            ordered_output_labels = [
                element.output_element_label
                for element in dataset_mapping.elements
            ]

            for dataset_ref in dataset_mapping.sources:
                source_dataset = dataset_series[
                    dataset_ref.series_index
                ].parts[dataset_ref.dataset_label]
                if source_dataset.data is None:
                    raise ValueError(
                        f"Dataset {dataset_ref.dataset_label!r} in series "
                        f"{dataset_ref.series_label!r} has no data; cannot "
                        "concatenate."
                    )
                source_to_output = {
                    source.element_label: element.output_element_label
                    for element in dataset_mapping.elements
                    for source in element.sources
                    if source.dataset == dataset_ref
                    and source.element_label != element.output_element_label
                }
                source_labels = [
                    source.element_label
                    for element in dataset_mapping.elements
                    for source in element.sources
                    if source.dataset == dataset_ref
                ]
                source_labels = list(dict.fromkeys(source_labels))
                data = self.subset(
                    source_dataset.data, element_group=source_labels
                )
                if len(source_to_output) > 0:
                    data = self.relabel(data, source_to_output)
                data_parts.append(
                    self.subset(data, element_group=ordered_output_labels)
                )
                if len(dataset_mapping.output_observation_ids) == 0:
                    output_observation_ids.update(
                        source_dataset.observation_ids
                    )

            output_dataset.data = self.concatenate_data(data_parts)
            output_dataset.observation_ids.update(output_observation_ids)
            ret.register_dataset(output_dataset)

            for element in dataset_mapping.elements:
                for observation_id in output_observation_ids:
                    ret._register_observable_property(
                        observable_property_id=(
                            element.output_observable_property_id
                        ),
                        observation_id=observation_id,
                        dataset_label=dataset_mapping.output_dataset_label,
                        element_label=element.output_element_label,
                        allow_existing=True,
                    )

        ret.build_observation_index()
        return ret

    def split_by_observation(
        self,
        dataset_series: DatasetSeries[T_DataType],
        *,
        new_label: str | None = None,
        cache_view: CacheContainerView | None = None,
        label_collision_strategy: LabelCollisionStrategy = (
            "prefix_source_dataset"
        ),
    ) -> DatasetSeries[T_DataType]:
        """
        Return a new DatasetSeries where each Dataset maps to exactly one Observation.

        This operation can split datasets with multiple observations and join
        multiple datasets that jointly represent one observation.
        """
        self._ensure_split_indices(dataset_series)

        series_label = (
            new_label
            if new_label is not None
            else f"{dataset_series.label}_by_observation"
        )
        ret = DatasetSeries[T_DataType](
            label=series_label,
            metadata=dict(dataset_series.metadata),
            identifier_provider=dataset_series.identifier_provider,
        )

        observation_ids = sorted(dataset_series._obs_index.keys())
        target_dataset_labels: dict[str, str] | None = None
        if cache_view is not None:
            target_dataset_labels = (
                self._build_target_dataset_labels_by_observation(
                    observation_ids, cache_view
                )
            )

        for observation_id in observation_ids:
            source_dataset_labels = sorted(
                dataset_series._obs_index.get(observation_id, set())
            )
            if len(source_dataset_labels) == 0:
                continue

            observable_property_context = (
                self._collect_observable_property_context(
                    dataset_series,
                    observation_id,
                    source_dataset_labels,
                )
            )
            required_fields_by_dataset = (
                self._collect_required_fields_by_dataset(
                    observable_property_context
                )
            )
            base_dataset_label = self._pick_base_dataset_label(
                source_dataset_labels, required_fields_by_dataset
            )

            raw_join_specs, right_to_left_join_key = self._resolve_join_specs(
                dataset_series,
                observation_id,
                source_dataset_labels,
                base_dataset_label,
                required_fields_by_dataset,
            )
            observable_property_by_source_field = {
                source_ref: observable_property_id
                for observable_property_id, source_ref in (
                    observable_property_context.items()
                )
            }
            field_label_mapping = self._build_field_label_mapping(
                source_dataset_labels,
                required_fields_by_dataset,
                label_collision_strategy=label_collision_strategy,
                observable_property_by_source_field=(
                    observable_property_by_source_field
                ),
                join_key_aliases=right_to_left_join_key,
            )

            datasets_for_join = self._prepare_datasets_for_join(
                dataset_series,
                observation_id,
                source_dataset_labels,
                required_fields_by_dataset,
                field_label_mapping,
            )

            base_data = datasets_for_join[base_dataset_label]
            if len(raw_join_specs) > 0:
                join_plan = self._build_adjusted_join_plan(
                    base_dataset_label,
                    source_dataset_labels,
                    raw_join_specs,
                    required_fields_by_dataset,
                    field_label_mapping,
                    how=OBSERVATION_ASSEMBLY_JOIN_HOW,
                )
                joined_data = self.execute_join_plan(
                    base_data=base_data,
                    datasets=datasets_for_join,
                    join_plan=join_plan,
                )
            else:
                joined_data = base_data

            final_fields_by_observable_property = (
                self._resolve_output_fields_by_observable_property(
                    observation_id,
                    observable_property_context,
                    right_to_left_join_key,
                    field_label_mapping,
                )
            )

            final_fields = sorted(
                set(final_fields_by_observable_property.values())
            )
            final_data = self.subset(joined_data, element_group=final_fields)

            target_dataset_label = (
                target_dataset_labels[observation_id]
                if target_dataset_labels is not None
                else observation_id
            )

            self._build_output_dataset_for_observation(
                target_series=ret,
                source_series=dataset_series,
                observation_id=observation_id,
                source_dataset_labels=source_dataset_labels,
                target_dataset_label=target_dataset_label,
                observable_property_context=observable_property_context,
                final_fields_by_observable_property=final_fields_by_observable_property,
                final_data=final_data,
            )

        ret.build_indices()
        return ret

    @abstractmethod
    def normalize_input(self, data: T_DataType) -> T_DataType:
        raise NotImplementedError(
            "Abstract method on class DataOpsInterface was called without supporting implementation."
        )

    @abstractmethod
    def normalize_output(self, data: T_DataType) -> T_DataType:
        raise NotImplementedError(
            "Abstract method on class DataOpsInterface was called without supporting implementation."
        )


class ValidationInterface(DataOpsInterface, Generic[T_DataType]):
    @abstractmethod
    def _validate(
        self,
        data: dict[str, Sequence] | T_DataType,
        config: validation_dto.ValidationConfig,
    ) -> ValidationErrorReport:
        raise NotImplementedError(
            "Abstract method on class ValidationInterface was called without supporting implementation."
        )

    @classmethod
    def get_default_adapter_class(cls):
        try:
            adapter_module = importlib.import_module(
                "pypeh.adapters.validation.pandera_adapter.validation_adapter"
            )
            adapter_class = getattr(
                adapter_module, "DataFrameValidationAdapter"
            )
        except Exception as e:
            logger.error(
                "Exception encountered while attempting to import a Pandera-based DataFrameAdapter"
            )
            raise e
        return adapter_class

    def build_column_validation(
        self,
        dataset_schema_element: DatasetSchemaElement,
        type_annotations: dict[str, dict[str, ObservablePropertyValueType]],
        cache_view: CacheContainerView,
        data_layout_element: peh.DataLayoutElement | None = None,
        dataset_label: str | None = None,
        column_has_only_empty_values: bool = False,
        allow_incomplete: bool = False,
    ) -> validation_dto.ColumnValidation:
        # Set default validation check applicability flags
        apply_required_check = True
        apply_nullable_check = True
        apply_property_validation = True
        # Adapt the flags in accordance with the user request, project config and data
        if allow_incomplete:
            apply_required_check = False
            if column_has_only_empty_values:
                apply_nullable_check = False
                apply_property_validation = False

        validations = []
        observable_property_id = dataset_schema_element.observable_property_id
        observable_property = cache_view.require(
            observable_property_id, "ObservableProperty"
        )
        assert isinstance(
            observable_property, peh.ObservableProperty
        ), f"ObservableProperty with id {observable_property_id} not found"

        if apply_required_check:
            required = observable_property.required
        else:
            required = False

        if apply_nullable_check:
            nullable = (
                not required
            )  # required and nullable are now checking the same thing
        else:
            nullable = True

        if apply_property_validation:
            min_value = getattr(observable_property, "min", None)
            max_value = getattr(observable_property, "max", None)
            validation_designs = getattr(
                data_layout_element, "validation_designs", None
            )
            if not validation_designs:
                # LEGACY VALIDATION SUPPORT: remove this fallback when
                # ObservableProperty.validation_designs is no longer supported.
                # A DataLayoutElement with validation designs always takes
                # precedence over property-owned designs.
                validation_designs = getattr(
                    observable_property, "validation_designs", None
                )
            if validation_designs:
                validations.extend(
                    [
                        validation_dto.ValidationDesign.from_peh(
                            vd,
                            type_annotations=type_annotations,
                            dataset_label=dataset_label,
                        )
                        for vd in validation_designs
                    ]
                )
            if min_value is not None or max_value is not None:
                validations.extend(
                    validation_dto.ValidationDesign.list_from_bounds(
                        min_value=min_value,
                        max_value=max_value,
                        type_annotations=type_annotations,
                        dataset_label=dataset_label,
                    )
                )
            if value_metadata := getattr(
                observable_property, "value_metadata", None
            ):
                skip_fields = set()
                if min_value is not None:
                    skip_fields.add("min")
                if max_value is not None:
                    skip_fields.add("max")
                validations.extend(
                    validation_dto.ValidationDesign.list_from_metadata(
                        value_metadata,
                        type_annotations=type_annotations,
                        dataset_label=dataset_label,
                        skip_fields=skip_fields,
                    )
                )
            if getattr(observable_property, "categorical", None):
                value_options = getattr(
                    observable_property, "value_options", None
                )
                assert (
                    value_options is not None
                ), f"ObservableProperty {observable_property} lacks `value_options` for categorical type"
                assert (
                    dataset_schema_element.data_type
                    == ObservablePropertyValueType.STRING
                )
                validation_arg_values: list[str] = [
                    str(vo.key) for vo in value_options
                ]
                # TODO: ADD CUSTOM CHECKS ON CATEGORICAL VARIABLES HERE
                expr = validation_dto.ValidationExpression(
                    command="is_in",
                    arg_values=validation_arg_values,
                    arg_columns=None,
                    subject=None,
                )
                validation = validation_dto.ValidationDesign(
                    name="check_categorical",
                    error_level=validation_dto.ValidationErrorLevel.ERROR,
                    expression=expr,
                    error_message=None,  # CUSTOM ERROR MESSAGE CANNOT BE PROVIDED OR SHOULD BE HARDCODED
                )
                validations.append(validation)

            if dataset_schema_element.data_type in [
                ObservablePropertyValueType.CATEGORICAL,
                ObservablePropertyValueType.STRING,
            ]:
                expr = validation_dto.ValidationExpression(
                    command="trailing_spaces",
                    arg_values=None,
                    arg_columns=None,
                    subject=None,
                )
                validation = validation_dto.ValidationDesign(
                    name="check_trailing_spaces",
                    error_level=validation_dto.ValidationErrorLevel.ERROR,
                    expression=expr,
                    error_message="Trailing/leading spaces were detected. Remove unnecessary white spaces.",
                )
                validations.append(validation)

            significant_decimals_raw = getattr(
                observable_property, "significantdecimals", None
            )
            if (
                significant_decimals_raw is not None
                and dataset_schema_element.data_type
                == ObservablePropertyValueType.FLOAT
            ):
                try:
                    significant_decimals = int(significant_decimals_raw)
                except (TypeError, ValueError):
                    significant_decimals = -1

                if significant_decimals >= 0:
                    expr = validation_dto.ValidationExpression(
                        command="decimals_precision",
                        arg_values=[significant_decimals],
                        arg_columns=None,
                        subject=None,
                    )
                    validation = validation_dto.ValidationDesign(
                        name="check_significant_decimals",
                        error_level=validation_dto.ValidationErrorLevel.ERROR,
                        expression=expr,
                        error_message=(
                            f"Decimal precision exceeds {significant_decimals} "
                            "allowed decimal places."
                        ),
                    )
                    validations.append(validation)

        assert dataset_schema_element.data_type.value != "decimal"
        # transformation using context_magic
        assert isinstance(required, bool)
        return validation_dto.ColumnValidation(
            unique_name=dataset_schema_element.label,
            data_type=dataset_schema_element.data_type.value,
            required=required,
            nullable=nullable,
            validations=validations,
        )

    def collect_column_validations(
        self,
        dataset: Dataset,
        type_annotations: dict[str, dict[str, ObservablePropertyValueType]],
        cache_view: CacheContainerView,
        allow_incomplete: bool = False,
    ) -> list[validation_dto.ColumnValidation]:
        column_validations: list[validation_dto.ColumnValidation] = []
        layout_section_id = dataset.described_by
        layout_elements_by_label: dict[str, peh.DataLayoutElement] = {}
        if layout_section_id is not None:
            layout_section = cache_view.require(
                layout_section_id, "DataLayoutSection"
            )
            assert isinstance(layout_section, peh.DataLayoutSection)
            layout_elements_by_label = {
                element.label: element
                for element in layout_section.elements or []
                if element.label is not None
            }
        column_labels = dataset.get_element_labels()
        assert column_labels is not None
        for column_label in column_labels:
            dataset_schema_element = dataset.get_schema_element_by_label(
                column_label
            )
            assert dataset_schema_element is not None
            # Check whether the dataset has data in the column
            if dataset.data is None:
                column_has_only_empty_values = True
            else:
                column_has_only_empty_values = (
                    self.check_element_has_only_empty_values(
                        data=dataset.data,
                        element_label=column_label,
                    )
                )
            column_validation = self.build_column_validation(
                dataset_schema_element=dataset_schema_element,
                cache_view=cache_view,
                type_annotations=type_annotations,
                data_layout_element=layout_elements_by_label.get(column_label),
                dataset_label=dataset.label,
                column_has_only_empty_values=column_has_only_empty_values,
                allow_incomplete=allow_incomplete,
            )
            column_validations.append(column_validation)

        return column_validations

    def build_dataset_level_validations(
        self,
        dataset: Dataset,
        dataset_series: DatasetSeries | None = None,
        cache_view: CacheContainerView | None = None,
    ) -> list[validation_dto.ValidationDesign] | None:
        dataset_level_validations: list[validation_dto.ValidationDesign] = []
        if cache_view is None:
            raise NotImplementedError(
                "ValidationInterface.build_dataset_level_validations requires a cache_view, but received None."
            )

        if dataset_series is not None:
            type_annotations = dataset_series.get_type_annotations()
        else:
            type_annotations = {dataset.label: dataset.get_type_annotations()}
        layout_section_id = dataset.described_by
        if layout_section_id is None:
            return None
        assert isinstance(layout_section_id, str)
        layout_section = cache_view.require(
            layout_section_id, "DataLayoutSection"
        )
        assert isinstance(layout_section, peh.DataLayoutSection)
        if layout_section.validation_designs:
            for vd in layout_section.validation_designs:
                assert isinstance(vd, peh.ValidationDesign)
                dataset_validation = validation_dto.ValidationDesign.from_peh(
                    vd, type_annotations
                )
                # For an expression that relies on a field reference spec for its arguments, set the validation arguments
                # as the actual values from the dataset (e.g. for an "is_in" check on a foreign key relation)
                validation_expression = vd.validation_expression
                assert isinstance(
                    validation_expression, peh.ValidationExpression
                )
                if validation_expression.validation_arg_contextual_field_references:
                    arg_values = validation_expression.validation_arg_values
                    assert isinstance(arg_values, list)
                    for ref in validation_expression.validation_arg_contextual_field_references:
                        assert isinstance(ref, peh.ContextualFieldReference)
                        dataset_label = ref.dataset_label
                        assert dataset_label is not None
                        field_label = ref.field_label
                        assert field_label is not None
                        if dataset_series is None:
                            assert dataset_label == dataset.label
                            dependent_dataset = dataset
                        else:
                            dependent_dataset = dataset_series[dataset_label]
                        assert dependent_dataset is not None
                        # fix this at the Interface level
                        column_arg_values = self.get_element_values(
                            dependent_dataset.data, field_label, as_list=True
                        )
                        arg_values.extend(column_arg_values)
                    dataset_validation.expression.arg_values = arg_values
                    dataset_validation.expression.arg_columns = None
                    dataset_level_validations.append(dataset_validation)

        return dataset_level_validations

    @classmethod
    def merge_contextual_field_reference_dependencies(
        cls, column_validations: list[validation_dto.ColumnValidation]
    ) -> dict[str, set[str]]:
        dependent_contextual_field_references = defaultdict(set)
        for column_validation in column_validations:
            if column_validation.validations is not None:
                for validation_design in column_validation.validations:
                    dependency_dict = (
                        validation_design.dependent_contextual_field_references
                    )
                    if dependency_dict is not None:
                        for ds, fields in dependency_dict.items():
                            dependent_contextual_field_references[ds].update(
                                fields
                            )

        return dependent_contextual_field_references

    def build_validation_config(
        self,
        dataset: Dataset,
        dataset_series: DatasetSeries | None = None,
        cache_view: CacheContainerView | None = None,
        allow_incomplete: bool = False,
    ) -> validation_dto.ValidationConfig:
        column_validations = []
        dataset_validations = []
        if cache_view is None:
            raise NotImplementedError(
                "ValidationInterface.build_validation_config requires a cache_view, but received None."
            )

        identifying_column_names = dataset.get_primary_keys()
        if identifying_column_names is not None:
            identifying_column_names = list(identifying_column_names)

        if dataset_series is None:
            type_annotations = {dataset.label: dataset.get_type_annotations()}
        else:
            type_annotations = dataset_series.get_type_annotations()
        column_validations = self.collect_column_validations(
            dataset=dataset,
            type_annotations=type_annotations,
            cache_view=cache_view,
            allow_incomplete=allow_incomplete,
        )
        dependent_contextual_field_references = (
            self.merge_contextual_field_reference_dependencies(
                column_validations
            )
        )
        dataset_validations = self.build_dataset_level_validations(
            dataset=dataset,
            dataset_series=dataset_series,
            cache_view=cache_view,
        )

        return validation_dto.ValidationConfig(
            name=dataset.label,
            columns=column_validations,
            identifying_column_names=identifying_column_names,
            validations=dataset_validations,
            dependent_contextual_field_references=dependent_contextual_field_references,
        )

    def validate(
        self,
        dataset: Dataset[T_DataType],
        dependent_dataset_series: DatasetSeries[T_DataType] | None = None,
        cache_view: CacheContainerView | None = None,
        allow_incomplete: bool = False,
    ) -> ValidationErrorReport:
        assert dataset.data is not None
        assert cache_view is not None
        to_validate = dataset.data
        assert to_validate is not None

        validation_config = self.build_validation_config(
            dataset=dataset,
            dataset_series=dependent_dataset_series,
            cache_view=cache_view,
            allow_incomplete=allow_incomplete,
        )
        # check whether data requires join to perform validation (cross DataLayoutSection validation)
        join_required = False
        dependent_contextual_field_references = (
            validation_config.dependent_contextual_field_references
        )
        if dependent_contextual_field_references is not None:
            join_required = len(dependent_contextual_field_references) > 0

        if join_required:
            if dependent_dataset_series is None:
                me = "`dependent_data` is required to perform all validations with `ValidationInterface`"
                logger.error(me)
                raise ValueError(me)
            else:
                assert (
                    dependent_contextual_field_references is not None
                ), "dependent_contextual_field_references in `ValidationInterface.validate` should not be None"
                assert dependent_dataset_series is not None
                join_specs: list[JoinSpec] = []
                required_fields_by_dataset: dict[str, set[str]] = defaultdict(
                    set
                )
                available_data: dict[str, T_DataType] = {}
                for (
                    dataset_label,
                    dependent_field_labels,
                ) in dependent_contextual_field_references.items():
                    other_dataset = dependent_dataset_series[dataset_label]
                    assert other_dataset is not None
                    other_data = other_dataset.data
                    assert other_data is not None
                    available_data[dataset_label] = other_data
                    join_spec = dataset.resolve_join(other_dataset)
                    if join_spec is None:
                        me = (
                            f"Cannot resolve explicit join path between "
                            f"'{dataset.label}' and '{dataset_label}'. "
                            "Add a `foreign_key_link` to the DataLayout elements."
                        )
                        logger.error(me)
                        raise ValueError(me)
                    join_specs.append(join_spec)
                    required_fields_by_dataset[dataset_label].update(
                        dependent_field_labels
                    )

                join_plan = JoinPlan.from_join_specs(
                    base_dataset_label=dataset.label,
                    join_specs=join_specs,
                    required_fields_by_dataset=required_fields_by_dataset,
                    how="left",
                )
                to_validate = self.execute_join_plan(
                    base_data=to_validate,
                    datasets=available_data,
                    join_plan=join_plan,
                )

        ret = self._validate(to_validate, validation_config)

        return ret


class DataExtractInterface(DataOpsInterface, Generic[T_DataType]):
    @abstractmethod
    def _filter(
        self,
        data: T_DataType,
        config: extract_dto.FilterConfig,
    ) -> T_DataType:
        raise NotImplementedError(
            "Abstract method on class DataExtractInterface."
        )

    @classmethod
    def get_default_adapter_class(cls):
        try:
            adapter_module = importlib.import_module(
                "pypeh.adapters.extract.dataframe_adapter"
            )
            adapter_class = getattr(adapter_module, "DataFrameExtractAdapter")
        except Exception as e:
            logger.error(
                "Exception encountered while attempting to import a dataguard-based DataFrameExtractAdapter"
            )
            raise e
        return adapter_class

    def build_filter_config(
        self,
        filter_expression: peh.FilterExpression | None,
        dataset_label: str,
        type_annotations: dict[str, dict[str, ObservablePropertyValueType]],
        select: list[str] | None = None,
        name: str | None = None,
    ) -> extract_dto.FilterConfig:
        filter_expression = extract_dto.FilterExpression.from_peh(
            filter_expression,
            type_annotations=type_annotations,
            dataset_label=dataset_label,
        )
        dependent_contextual_field_references = (
            filter_expression.dependent_contextual_field_references or {}
        )
        return extract_dto.FilterConfig(
            name=name or dataset_label,
            filter_expression=filter_expression,
            select=select,
            dependent_contextual_field_references=dependent_contextual_field_references,
        )

    @staticmethod
    def _merge_filter_type_annotations(
        reshaped_dataset_series: DatasetSeries[T_DataType],
        source_dataset_series: DatasetSeries[T_DataType] | None,
    ) -> dict[str, dict[str, ObservablePropertyValueType]]:
        """
        Build type annotations for filter parsing, falling back to the source
        series for datasets/fields that `extract_from_source` projected away.

        The reshaped series takes precedence; source annotations only fill in
        datasets or fields that are absent from the reshaped series.
        """
        type_annotations = reshaped_dataset_series.get_type_annotations()
        if source_dataset_series is None:
            return type_annotations
        for (
            dataset_label,
            source_fields,
        ) in source_dataset_series.get_type_annotations().items():
            merged = dict(source_fields)
            merged.update(type_annotations.get(dataset_label, {}))
            type_annotations[dataset_label] = merged
        return type_annotations

    @staticmethod
    def _resolve_filter_dependency_dataset(
        dependent_dataset_label: str,
        dependent_field_labels: set[str],
        reshaped_dataset_series: DatasetSeries[T_DataType],
        source_dataset_series: DatasetSeries[T_DataType] | None,
    ) -> Dataset:
        """
        Locate the Dataset providing a filter's dependency fields.

        Prefer the reshaped series, but fall back to `source_dataset_series`
        when the referenced fields were dropped during extraction (e.g. a
        condition column that is not itself an exported output).
        """

        def _satisfies(dataset: Dataset | None) -> bool:
            if dataset is None or dataset.data is None:
                return False
            return set(dependent_field_labels).issubset(
                set(dataset.get_element_labels())
            )

        candidate = reshaped_dataset_series[dependent_dataset_label]
        if _satisfies(candidate):
            assert candidate is not None
            return candidate

        if source_dataset_series is not None:
            source_candidate = source_dataset_series[dependent_dataset_label]
            if _satisfies(source_candidate):
                assert source_candidate is not None
                return source_candidate

        me = (
            f"Filter references fields "
            f"{sorted(dependent_field_labels)!r} from dataset "
            f"'{dependent_dataset_label}' that are not available in the "
            "reshaped DatasetSeries"
        )
        if source_dataset_series is None:
            me += (
                " and no `source_dataset_series` fallback was provided. Pass "
                "the pre-extraction source series so filter dependencies that "
                "were projected away can be resolved."
            )
        else:
            me += " or the provided `source_dataset_series` fallback."
        logger.error(me)
        raise ValueError(me)

    def apply_filter(
        self,
        reshaped_dataset_series: DatasetSeries[T_DataType],
        filter_expression: peh.FilterExpression | None,
        dataset_label: str,
        source_dataset_series: DatasetSeries[T_DataType] | None = None,
    ) -> DatasetSeries[T_DataType]:
        """
        Apply a single DataLayoutSection's filter (peh.DataFilter.filter_expression)
        to the already-reshaped `dataset_label` part of `reshaped_dataset_series`,
        resolving any cross-DataLayoutSection joins the filter depends on.

        A filter predicate may reference fields that `extract_from_source`
        projected away (e.g. exporting a single non-identifying column while
        filtering on a condition column that is not itself exported). When such
        a dependency cannot be satisfied from `reshaped_dataset_series`, it is
        resolved against the optional `source_dataset_series` fallback.
        """
        base_dataset = reshaped_dataset_series.parts[dataset_label]
        assert base_dataset is not None
        assert base_dataset.data is not None
        to_filter = base_dataset.data

        select = base_dataset.get_element_labels()
        type_annotations = self._merge_filter_type_annotations(
            reshaped_dataset_series, source_dataset_series
        )
        filter_config = self.build_filter_config(
            filter_expression=filter_expression,
            dataset_label=dataset_label,
            type_annotations=type_annotations,
            select=select,
        )

        # check whether the filter references fields in other datasets and
        # therefore requires a join (cross DataLayoutSection filtering)
        dependent_contextual_field_references = (
            filter_config.dependent_contextual_field_references
        )
        join_required = bool(dependent_contextual_field_references)

        if join_required:
            join_specs: list[JoinSpec] = []
            required_fields_by_dataset: dict[str, set[str]] = defaultdict(set)
            available_data: dict[str, T_DataType] = {}
            for (
                dependent_dataset_label,
                dependent_field_labels,
            ) in dependent_contextual_field_references.items():
                other_dataset = self._resolve_filter_dependency_dataset(
                    dependent_dataset_label,
                    dependent_field_labels,
                    reshaped_dataset_series,
                    source_dataset_series,
                )
                other_data = other_dataset.data
                assert other_data is not None
                available_data[dependent_dataset_label] = other_data
                join_spec = base_dataset.resolve_join(other_dataset)
                if join_spec is None:
                    me = (
                        f"Cannot resolve explicit join path between "
                        f"'{dataset_label}' and '{dependent_dataset_label}'. "
                        "Add a `foreign_key_link` to the DataLayout elements."
                    )
                    logger.error(me)
                    raise ValueError(me)
                join_specs.append(join_spec)
                required_fields_by_dataset[dependent_dataset_label].update(
                    dependent_field_labels
                )

            join_plan = JoinPlan.from_join_specs(
                base_dataset_label=dataset_label,
                join_specs=join_specs,
                required_fields_by_dataset=required_fields_by_dataset,
                how="left",
            )
            to_filter = self.execute_join_plan(
                base_data=to_filter,
                datasets=available_data,
                join_plan=join_plan,
            )

        filtered = self._filter(to_filter, filter_config)
        reshaped_dataset_series.add_data(
            dataset_label,
            filtered,
            data_labels=self.get_element_labels(filtered),
        )

        return reshaped_dataset_series


class DataEnrichmentInterface(DataOpsInterface, Generic[T_DataType]):
    @classmethod
    def get_default_adapter_class(cls):
        try:
            adapter_module = importlib.import_module(
                "pypeh.adapters.enrichment.dataframe_adapter"
            )
            adapter_class = getattr(
                adapter_module, "DataFrameEnrichmentAdapter"
            )
        except Exception as e:
            logger.error(
                "Exception encountered while attempting to import enrichment DataFrameAdapter"
            )
            raise e
        return adapter_class

    @abstractmethod
    def apply_map(
        self, dataset, map_fn, field_label, output_dtype, base_fields, **kwargs
    ): ...

    @abstractmethod
    def map_type(self, peh_value_type: str): ...

    def build_callable(self, delayed_node: graph.Delayed) -> Callable:
        map_fn = delayed_node.map_fn
        arg_sources = delayed_node.arg_sources
        arg_values = delayed_node.arg_values
        join_specs = delayed_node.join_specs
        output_dtype = self.type_mapper(delayed_node.output_dtype)

        def _apply(datasets: dict, *, node: graph.Node, base_fields: dict):
            """
            datasets: dict of dataset_label → dataset object (lazy or eager)
            parent_results: mapping from parent Node → computed result for this node
            """
            ds = datasets[node.dataset_label]
            # Apply all joins
            if join_specs:
                required_fields_by_dataset: dict[str, set[str]] = defaultdict(
                    set
                )
                for parent_node in arg_sources.values():
                    if parent_node.dataset_label != node.dataset_label:
                        required_fields_by_dataset[
                            parent_node.dataset_label
                        ].add(parent_node.field_label)
                join_plan = JoinPlan.from_join_specs(
                    base_dataset_label=node.dataset_label,
                    join_specs=join_specs,
                    required_fields_by_dataset=required_fields_by_dataset,
                    how="left",
                )
                ds = self.execute_join_plan(
                    base_data=ds,
                    datasets=datasets,
                    join_plan=join_plan,
                )

            # Build column expressions for the map function
            kwargs = {}
            for arg_name, parent_node in arg_sources.items():
                col_name = parent_node.field_label
                kwargs[arg_name] = self.select_field(ds, col_name)
            kwargs.update(arg_values)

            # Apply the map
            base_fields_subset = base_fields.get(node.dataset_label, None)
            assert base_fields_subset is not None
            out = self.apply_map(
                ds,
                map_fn,
                node.field_label,
                output_dtype,
                base_fields_subset,
                **kwargs,
            )
            base_fields_subset.append(node.field_label)

            return out

        return _apply

    def compile_dependency_graph(
        self, dependency_graph: graph.Graph
    ) -> graph.ExecutionPlan:
        sorted_nodes = dependency_graph.topological_sort()
        steps: list[graph.ExecutionStep] = []

        for node in sorted_nodes:
            delayed = dependency_graph.delayed_fns.get(node)
            if delayed is None:
                continue

            compute_fn = self.build_callable(delayed)
            steps.append(graph.ExecutionStep(node=node, compute=compute_fn))

        ret = graph.ExecutionPlan(steps)
        dependency_graph.execution_plan = ret

        return ret

    def compute_with_dependency_graph(
        self, dependency_graph: graph.Graph, datasets: dict[str, Dataset]
    ):
        if dependency_graph.execution_plan is None:
            raise AssertionError(
                "A dependency graph needs to be compiled first to set up an execution plan"
            )

        base_fields = {
            label: dataset.get_element_labels()
            for label, dataset in datasets.items()
        }
        raw_datasets = {
            label: self.normalize_input(dataset.data)
            for label, dataset in datasets.items()
        }
        dependency_graph.execution_plan.run(raw_datasets, base_fields)

        for dataset_label in datasets:
            datasets[dataset_label].data = self.normalize_output(
                raw_datasets[dataset_label]
            )

    def build_dependency_graph(
        self,
        observations: list[peh.Observation],
        context_index: ContextIndexProtocol,
        cache_view: CacheContainerView,
        join_spec_mapping: dict[frozenset, JoinSpec | None] | None = None,
    ) -> graph.Graph:
        dependency_graph = graph.Graph()
        # the source_observations also need to be added to the dependency graph!!!!!
        for observation in observations:
            assert observation.observation_design is not None
            assert isinstance(
                observation.observation_design, peh.ObservationDesignId
            )
            observation_design = cache_view.require(
                observation.observation_design, "ObservationDesign"
            )
            assert isinstance(observation_design, peh.ObservationDesign)
            assert (
                observation_design.observable_property_specifications
                is not None
            )
            for (
                observable_property_spec
            ) in observation_design.observable_property_specifications:
                assert isinstance(
                    observable_property_spec,
                    peh.ObservablePropertySpecification,
                )
                assert isinstance(
                    observable_property_spec.observable_property,
                    (peh.ObservableProperty, peh.ObservablePropertyId, str),
                )
                if isinstance(
                    observable_property_spec.observable_property,
                    (peh.ObservablePropertyId, str),
                ):
                    observable_property = cache_view.require(
                        observable_property_spec.observable_property,
                        "ObservableProperty",
                    )
                elif isinstance(
                    observable_property_spec.observable_property,
                    peh.ObservableProperty,
                ):
                    observable_property = (
                        observable_property_spec.observable_property
                    )
                assert observable_property is not None
                assert isinstance(observable_property, peh.ObservableProperty)
                target_contextual_field_ref = context_index.context_lookup(
                    observation.id, observable_property.id
                )
                assert (
                    target_contextual_field_ref is not None
                ), f"Target contextual reference could not be found for property {observable_property.id} in observation {observation.id}."
                target_dataset_label, target_field_label = (
                    target_contextual_field_ref
                )
                if observable_property_spec.calculation_design is not None:
                    # EXTRA INFO FROM CALCULATION DESIGN AND UPDATE DEPENDENCY GRAPH
                    calculation_design = (
                        observable_property_spec.calculation_design
                    )
                    assert isinstance(
                        calculation_design, peh.CalculationDesign
                    )
                    calculation_implementation = (
                        calculation_design.calculation_implementation
                    )
                    assert isinstance(
                        calculation_implementation,
                        peh.CalculationImplementation,
                    )
                    function_name = calculation_implementation.function_name
                    assert isinstance(function_name, str)
                    output_dtype = observable_property.value_type
                    assert output_dtype is not None

                    child = graph.Node(
                        dataset_label=target_dataset_label,
                        field_label=target_field_label,
                    )
                    dependency_graph.add_calculation_target(
                        child,
                        function_name=function_name,
                        result_dtype=output_dtype,
                    )
                    function_kwargs = (
                        calculation_implementation.function_kwargs
                    )
                    assert function_kwargs is not None
                    for function_kwarg in function_kwargs:
                        assert isinstance(
                            function_kwarg, peh.CalculationKeywordArgument
                        )
                        map_name = function_kwarg.mapping_name
                        assert map_name is not None
                        source_field_ref = getattr(
                            function_kwarg,
                            "contextual_field_reference",
                            None,
                        )
                        scalar_value = getattr(function_kwarg, "value", None)
                        scalar_value_type = getattr(
                            function_kwarg, "value_type", None
                        )
                        if scalar_value is not None:
                            scalar_value = self._resolve_scalar_value(
                                scalar_value, scalar_value_type
                            )

                        if source_field_ref is not None:
                            assert isinstance(
                                source_field_ref, peh.ContextualFieldReference
                            )
                            source_observation_id = (
                                source_field_ref.dataset_label
                            )
                            assert source_observation_id is not None
                            source_observable_property_id = (
                                source_field_ref.field_label
                            )
                            assert source_observable_property_id is not None
                            source_contextual_field_ref = (
                                context_index.context_lookup(
                                    source_observation_id,
                                    source_observable_property_id,
                                )
                            )
                            assert (
                                source_contextual_field_ref is not None
                            ), f"Source contextual reference could not be found for property {source_observable_property_id} in observation {source_observation_id}."
                            source_dataset_label, source_field_label = (
                                source_contextual_field_ref
                            )
                            parent = graph.Node(
                                dataset_label=source_dataset_label,
                                field_label=source_field_label,
                            )
                            join_spec = None
                            if join_spec_mapping is not None:
                                join_spec = join_spec_mapping.get(
                                    frozenset(
                                        [
                                            target_dataset_label,
                                            source_dataset_label,
                                        ]
                                    ),
                                    None,
                                )
                            if (
                                source_dataset_label != target_dataset_label
                                and join_spec is None
                            ):
                                raise ValueError(
                                    f"Could not resolve join path between datasets '{target_dataset_label}' and '{source_dataset_label}' for calculation argument '{map_name}'."
                                )
                            dependency_graph.add_calculation_source(
                                parent,
                                child,
                                map_name,
                                join_spec=join_spec,
                            )
                        elif scalar_value is not None:
                            dependency_graph.add_calculation_scalar_argument(
                                child, map_name, scalar_value
                            )
                        else:
                            raise ValueError(
                                f"CalculationKeywordArgument {map_name} has neither contextual_field_reference nor value."
                            )

        return dependency_graph

    def enrich(
        self,
        source_dataset_series: DatasetSeries,
        target_observations: list[peh.Observation],
        target_derived_from: list[peh.Observation],
        cache_view: CacheContainerView,
        target_label_collision_strategy: LabelCollisionStrategy = "error",
    ) -> DatasetSeries:
        # ADD TARGET OBSERVATION TO SOURCE_DATASET_SERIES
        for source_obs, target_observation in zip(
            target_derived_from, target_observations
        ):
            # TODO: ENSURE PREREQUISTE IS MET: DATASETSERIES SPLIT INTO OBSERVATIONS
            source_dataset = self.get_dataset_by_observation_id(
                dataset_series=source_dataset_series,
                observation_id=source_obs.id,
            )
            assert source_dataset is not None
            source_dataset_label = source_dataset.label
            labeled_observable_property_specifications = (
                self.extract_labeled_observable_property_specifications(
                    target_observation,
                    cache_view=cache_view,
                    label_collision_strategy=target_label_collision_strategy,
                    source_dataset_series=source_dataset_series,
                )
            )
            source_dataset_series.add_observation(
                source_dataset_label,
                target_observation,
                labeled_observable_property_specifications=labeled_observable_property_specifications,
                cache_view=cache_view,
            )
        join_spec_mapping = source_dataset_series.resolve_all_joins()
        # BUILD DEPENDENCY GRAPH
        all_observations = []
        for nested_observations in source_dataset_series.observations.values():
            for observation_id in nested_observations:
                observation = cache_view.require(observation_id, "Observation")
                all_observations.append(observation)

        dependency_graph = self.build_dependency_graph(
            observations=all_observations,
            context_index=source_dataset_series,
            join_spec_mapping=join_spec_mapping,
            cache_view=cache_view,
        )
        # EXECUTE THE DEFINED COMPUTATIONS
        self.compile_dependency_graph(dependency_graph=dependency_graph)
        self.compute_with_dependency_graph(
            dependency_graph=dependency_graph,
            datasets=source_dataset_series.parts,
        )
        # RETURN THE UPDATED SOURCE_DATASET_SERIES
        return source_dataset_series


class AggregationInterface(DataOpsInterface, Generic[T_DataType]):
    @abstractmethod
    def _calculate_for_stratum(
        self,
        df: T_DataType,
        group_cols: list[str] | None,
        value_col: str,
        stat_builders: list,
        **kwargs,
    ) -> T_DataType:
        raise NotImplementedError(
            "Abstract method on class AggregationInterface was called without supporting implementation."
        )

    @abstractmethod
    def calculate_for_strata(
        self,
        df: T_DataType,
        stratifications: list[list[str]] | None,
        value_col: str,
        stat_builders: list[str],
        **kwargs,
    ) -> T_DataType:
        raise NotImplementedError(
            "Abstract method on class AggregationInterface was called without supporting implementation."
        )

    @abstractmethod
    def group_results(
        self,
        results_to_collect: list[T_DataType],
        strata: list[str] | None = None,
    ) -> T_DataType:
        raise NotImplementedError(
            "Abstract method on class AggregationInterface was called without supporting implementation."
        )

    @classmethod
    def get_default_adapter_class(cls):
        try:
            adapter_module = importlib.import_module(
                "pypeh.adapters.aggregation.polars_adapter.dataframe_adapter"
            )

            adapter_class = getattr(
                adapter_module, "DataFrameAggregationAdapter"
            )
        except Exception as e:
            logger.error(
                "Exception encountered while attempting to import a Polars-based DataFrameAggregationAdapter"
            )
            raise e
        return adapter_class

    def _resolve_aggregation_function_kwargs(
        self,
        function_kwargs: list[peh.CalculationKeywordArgument] | None,
        source_obs: peh.Observation,
        source_dataset_series: DatasetSeries,
    ) -> tuple[str | None, dict]:
        value_col = None
        resolved_kwargs = {}

        if function_kwargs is None:
            return value_col, resolved_kwargs

        for function_kwarg in function_kwargs:
            assert isinstance(function_kwarg, peh.CalculationKeywordArgument)
            map_name = function_kwarg.mapping_name
            source_field_ref = getattr(
                function_kwarg,
                "contextual_field_reference",
                None,
            )
            scalar_value = getattr(function_kwarg, "value", None)
            scalar_value_type = getattr(function_kwarg, "value_type", None)

            if scalar_value is not None:
                scalar_value = self._resolve_scalar_value(
                    scalar_value, scalar_value_type
                )

            if source_field_ref is not None:
                assert isinstance(
                    source_field_ref, peh.ContextualFieldReference
                )
                kwarg_source_observation_id = source_field_ref.dataset_label
                assert kwarg_source_observation_id is not None
                if kwarg_source_observation_id != source_obs.id:
                    raise ValueError(
                        "All CalculationKeywordArguments should refer to "
                        f"specified source observation: {source_obs.id}"
                    )
                kwarg_source_observable_property_id = (
                    source_field_ref.field_label
                )
                assert kwarg_source_observable_property_id is not None
                _, source_element_label = source_dataset_series.context_lookup(
                    kwarg_source_observation_id,
                    kwarg_source_observable_property_id,
                )

                if map_name is None:
                    value_col = source_element_label
                else:
                    resolved_kwargs[map_name] = source_element_label
            elif scalar_value is not None:
                if map_name is None:
                    raise ValueError(
                        "Scalar CalculationKeywordArguments require "
                        "mapping_name."
                    )
                resolved_kwargs[map_name] = scalar_value
            else:
                raise ValueError(
                    "CalculationKeywordArgument has neither "
                    "contextual_field_reference nor value."
                )

        return value_col, resolved_kwargs

    def summarize(
        self,
        source_dataset_series: DatasetSeries,
        target_observations: list[peh.Observation],
        target_derived_from: list[peh.Observation],
        cache_view: CacheContainerView,
        target_label_collision_strategy: LabelCollisionStrategy = "error",
    ) -> DatasetSeries:
        # ADD TARGET OBSERVATION TO A NEW DATASET_SERIES
        aggregated_dataset_series: DatasetSeries = DatasetSeries(
            label=f"{source_dataset_series.label}_aggregated",
            identifier_provider=source_dataset_series.identifier_provider,
        )
        assert len(target_observations) == len(target_derived_from)

        for source_obs, target_observation in zip(
            target_derived_from, target_observations
        ):
            collected_results = []
            # FOR LOOP COMPUTES ALL SUMMARY STATS ASSOCIATED WITH A SINGLE SOURCE OBSERVABLE PROPERTY
            source_dataset = self.get_dataset_by_observation_id(
                dataset_series=source_dataset_series,
                observation_id=source_obs.id,
            )
            source_data = source_dataset.data
            assert source_data is not None

            # COMPILE LIST OF LABELED OBSERVABLE PROPERTIES FOR TARGET
            if label := target_observation.ui_label:
                labeled_observable_property_specifications = (
                    self.extract_labeled_observable_property_specifications(
                        target_observation,
                        cache_view=cache_view,
                        label_collision_strategy=(
                            target_label_collision_strategy
                        ),
                        source_dataset_series=source_dataset_series,
                    )
                )
                target_dataset = aggregated_dataset_series.add_observation(
                    label,
                    target_observation,
                    labeled_observable_property_specifications=labeled_observable_property_specifications,
                    cache_view=cache_view,
                )
            else:
                raise ValueError(
                    f"Source observation {source_obs.id} lacks a `ui_label` which is required to add the target observation to the DatasetSeries"
                )

            # COMPILE STRATIFICATIONS
            stratification_ids = []
            # COMPILE AGGREGATION FUNCTION LIST
            stat_specs_by_value_col = {}
            # LOOP OVER ALL OBSERVABLE PROPERTY SPECIFICATIONS
            target_observation_design_id = (
                target_observation.observation_design
            )
            assert isinstance(target_observation_design_id, str)
            target_observation_design = cache_view.require(
                target_observation_design_id, "ObservationDesign"
            )
            assert isinstance(target_observation_design, peh.ObservationDesign)
            observable_property_specs = (
                target_observation_design.observable_property_specifications
            )
            assert observable_property_specs is not None
            for observable_property_spec in observable_property_specs:
                assert isinstance(
                    observable_property_spec,
                    peh.ObservablePropertySpecification,
                )
                observable_property_id = (
                    observable_property_spec.observable_property
                )
                assert isinstance(observable_property_id, str)
                observable_property = cache_view.require(
                    observable_property_id, "ObservableProperty"
                )
                assert isinstance(observable_property, peh.ObservableProperty)
                specification_category = (
                    observable_property_spec.specification_category
                )
                assert specification_category is not None
                identifying = (
                    str(specification_category)
                    == peh.ObservablePropertySpecificationCategory.identifying.text
                )
                if identifying:
                    stratification_ids.append(observable_property_id)

                # EXTRACT CALCULATION DESIGN
                if observable_property_spec.calculation_design is not None:
                    calculation_design = (
                        observable_property_spec.calculation_design
                    )
                    assert isinstance(
                        calculation_design, peh.CalculationDesign
                    )
                    calculation_implementation = (
                        calculation_design.calculation_implementation
                    )
                    assert isinstance(
                        calculation_implementation,
                        peh.CalculationImplementation,
                    )
                    output_dtype = ObservablePropertyValueType(
                        getattr(observable_property, "value_type", "string")
                    )
                    assert output_dtype is not None
                    function_name = calculation_implementation.function_name
                    assert function_name is not None
                    map_fn = _extract_callable(function_name)
                    function_kwargs = cast(
                        list[peh.CalculationKeywordArgument] | None,
                        calculation_implementation.function_kwargs,
                    )
                    value_col, stat_kwargs = (
                        self._resolve_aggregation_function_kwargs(
                            function_kwargs,
                            source_obs=source_obs,
                            source_dataset_series=source_dataset_series,
                        )
                    )
                    if value_col is None:
                        raise ValueError(
                            "Aggregation calculations require one "
                            "contextual_field_reference without mapping_name "
                            "to identify the value column."
                        )
                    _, target_label = aggregated_dataset_series.context_lookup(
                        target_observation.id,
                        observable_property.id,
                    )
                    stat_specs = stat_specs_by_value_col.setdefault(
                        value_col,
                        {
                            "stat_builders": [],
                            "result_aliases": [],
                            "stat_kwargs": [],
                        },
                    )
                    stat_specs["stat_builders"].append(map_fn)
                    stat_specs["result_aliases"].append(target_label)
                    stat_specs["stat_kwargs"].append(stat_kwargs)

            # LOOKUP STRATIFICATION LABELS
            stratification_labels = None
            if len(stratification_ids) > 0:
                stratification_labels = []
                for strat_id in stratification_ids:
                    _, element_label = source_dataset_series.context_lookup(
                        source_obs.id, strat_id
                    )
                    stratification_labels.append(element_label)
            # COMPUTE SUMMARY STAT FOR EACH SOURCE ELEMENT
            normalized_source_data = self.normalize_input(source_data)
            for value_col, stat_specs in stat_specs_by_value_col.items():
                target_data = self._calculate_for_stratum(
                    df=normalized_source_data,
                    group_cols=stratification_labels,
                    value_col=value_col,
                    stat_builders=stat_specs["stat_builders"],
                    result_aliases=stat_specs["result_aliases"],
                    stat_kwargs=stat_specs["stat_kwargs"],
                )
                collected_results.append(target_data)

            target_data = self.group_results(
                collected_results, strata=stratification_labels
            )
            data_labels = self.get_element_labels(target_data)
            target_dataset.add_data(data=target_data, data_labels=data_labels)

        return aggregated_dataset_series
