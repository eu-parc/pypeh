"""
The metadata interface provides the study-metadata service: given an
imported `DatasetSeries` and its `DataImportConfig`, it builds a
nested metadata tree (variable catalogue, datasets, provenance) by
walking the PEH resources in the session cache.

Usage:
    Session.create_study_metadata(...) resolves this interface through
    the registered "metadata" adapter.

"""

from __future__ import annotations

import importlib
import importlib.metadata
import logging
import math

from abc import abstractmethod
from peh_model import peh
from typing import TYPE_CHECKING, Any, Generic

from pypeh.core.cache.containers import CacheContainerView
from pypeh.core.interfaces.dataops import DataOpsInterface
from pypeh.core.models import metadata_dto
from pypeh.core.models.internal_data_layout import (
    DatasetSchemaElement,
    DatasetSeries,
)
from pypeh.core.models.typing import T_DataType

if TYPE_CHECKING:
    from pypeh.core.models.validation_errors import (
        ValidationErrorReportCollection,
    )

logger = logging.getLogger(__name__)


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    text = getattr(value, "text", None)
    return text if isinstance(text, str) else str(value)


def _clean_text(value: Any) -> str | None:
    text = _as_text(value)
    return text.strip() if isinstance(text, str) else None


def _as_number(value: Any, digits: int = 3) -> Any:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return _as_text(value)


def _package_version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def _check_json_value(
    value: Any,
    key: str,
    open_containers: set[int] | None = None,
) -> None:
    """
    Enforce the JSON-serialization contract on caller-provided
    `extra_provenance` values: finite str / int / float / bool /
    None, lists, and str-keyed dicts, recursively. Anything else
    (Path, Decimal, set, the non-finite floats NaN / Infinity, ...)
    and self-referencing containers raise ValueError naming the
    offending key.
    """
    if open_containers is None:
        open_containers = set()
    if value is None or isinstance(value, (str, int, bool)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(
                "StudyMetadataConfig.extra_provenance field "
                f"{key!r} holds the non-finite float {value}; NaN "
                "and Infinity are not valid JSON — convert it with "
                "str(...)."
            )
        return
    if isinstance(value, (list, dict)):
        # open_containers tracks the nesting stack so that only true
        # cycles (which json.dumps rejects too) are flagged, not
        # plain re-referencing of the same list or dict.
        if id(value) in open_containers:
            raise ValueError(
                "StudyMetadataConfig.extra_provenance field "
                f"{key!r} holds a self-referencing "
                f"{type(value).__name__}."
            )
        open_containers.add(id(value))
        if isinstance(value, list):
            for item in value:
                _check_json_value(item, key, open_containers)
        else:
            for sub_key, item in value.items():
                if not isinstance(sub_key, str):
                    raise ValueError(
                        "StudyMetadataConfig.extra_provenance field "
                        f"{key!r} holds a dict key of type "
                        f"{type(sub_key).__name__}; expected str — "
                        "convert it with str(...)."
                    )
                _check_json_value(item, key, open_containers)
        open_containers.remove(id(value))
        return
    raise ValueError(
        "StudyMetadataConfig.extra_provenance field "
        f"{key!r} holds a {type(value).__name__}; expected str, int, "
        "float, bool, None, list or dict — convert it with "
        "str(...)."
    )


def _to_plain(value: Any) -> Any:
    """
    Rebuild the tree from builtin types only: `str` subclasses (peh
    ids, str enums) become `str`, and every container is copied, so
    no two branches share an object. The result serializes cleanly to
    JSON / YAML (no python tags, no anchors / aliases).
    """
    if isinstance(value, dict):
        return {_to_plain(key): _to_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(item) for item in value]
    if isinstance(value, str):
        return str.__str__(value)
    return value


class MetadataInterface(DataOpsInterface, Generic[T_DataType]):
    """
    Builds the study-metadata tree for an imported DatasetSeries.

    The orchestration (cache traversal, tree assembly, section gating
    via `StudyMetadataConfig`) lives on this interface, written
    generically over `T_DataType`. Adapters implement only the one
    dataframe-dependent primitive: `map_data_type`.
    """

    @abstractmethod
    def map_data_type(self, schema_element: DatasetSchemaElement) -> str:
        """
        Map a dataset schema element to its wire-format data type
        label (e.g. "STRING", "INTEGER", "FLOAT").
        """
        raise NotImplementedError(
            "Abstract method on class MetadataInterface was called "
            "without supporting implementation."
        )

    @classmethod
    def get_default_adapter_class(cls):
        try:
            adapter_module = importlib.import_module(
                "pypeh.adapters.metadata.dataframe_adapter"
            )
            adapter_class = getattr(adapter_module, "DataFrameMetadataAdapter")
        except Exception as e:
            logger.error(
                "Exception encountered while attempting to import a "
                "Polars-based DataFrameMetadataAdapter"
            )
            raise e
        return adapter_class

    #### ORCHESTRATION ####

    def build_study_metadata(
        self,
        dataset_series: DatasetSeries[T_DataType],
        data_import_config: peh.DataImportConfig,
        metadata_config: metadata_dto.StudyMetadataConfig,
        cache_view: CacheContainerView,
        validation_report: "ValidationErrorReportCollection | None" = None,
    ) -> dict[str, Any]:
        """
        Build the study-metadata tree.

        Sections gated off in `metadata_config` are omitted from the
        returned tree entirely, so a present key means "requested".
        The tree holds builtin types only (dict / list / str / numbers
        / bool / None).
        """
        reachable = self._reachable_observations(
            cache_view, data_import_config
        )
        lineage = set(reachable)
        self._check_series_matches_config(
            dataset_series, data_import_config, lineage
        )
        designs = self._observation_designs(cache_view, reachable)
        if metadata_config.exclude_control_variables:
            # Union of both views: the design walk classifies what the
            # reachable observations specify, the schema walk what the
            # datasets contain. The schema pass also covers datasets
            # whose observation design is missing from the cache
            # (missing designs are tolerated elsewhere).
            control_ids = self._collect_control_ids(
                cache_view, designs
            ) | self._collect_schema_control_ids(cache_view, dataset_series)
        else:
            control_ids = set()
        tree: dict[str, Any] = {}

        structure_by_op: dict[str, dict] = {}
        if metadata_config.include_variable_catalogue:
            tree["observations"] = self._catalogue_section(
                cache_view,
                designs,
                control_ids,
                structure_by_op,
            )

        if metadata_config.include_datasets:
            tree["datasets"] = self._datasets_section(
                dataset_series,
                structure_by_op,
                control_ids,
            )

        if metadata_config.include_provenance:
            tree["provenance"] = self._provenance_section(
                dataset_series=dataset_series,
                data_import_config=data_import_config,
                cache_view=cache_view,
                metadata_config=metadata_config,
                lineage=lineage,
                validation_report=validation_report,
            )

        return _to_plain(tree)

    #### OBSERVATION LINEAGE ####

    @staticmethod
    def _config_observations(
        data_import_config: peh.DataImportConfig,
    ) -> list[str]:
        observation_ids: list[str] = []
        section_mapping = data_import_config.section_mapping
        if section_mapping is None:
            return observation_ids
        for link in section_mapping.section_mapping_links or []:
            for observation_id in _as_list(link.observation_id_list):
                if observation_id not in observation_ids:
                    observation_ids.append(observation_id)
        return observation_ids

    def _reachable_observations(
        self,
        cache_view: CacheContainerView,
        data_import_config: peh.DataImportConfig,
    ) -> list[str]:
        """
        The configured observations plus everything derived from them
        (transitively): enrichment / aggregation DerivedObservations.

        Ordered deterministically in dependency order: the configured
        observations first, then a breadth-first walk of the
        derivation graph, so every derived observation follows the
        observation it was derived from. Siblings keep cache order.
        """
        children: dict[str, list[str]] = {}
        for derived in cache_view.get_all("DerivedObservation"):
            derived_id = getattr(derived, "id", None)
            parent_id = getattr(derived, "was_derived_from", None)
            if derived_id is None or parent_id is None:
                continue
            children.setdefault(parent_id, []).append(derived_id)

        ordered = self._config_observations(data_import_config)
        known = set(ordered)
        index = 0
        while index < len(ordered):
            for child_id in children.get(ordered[index], []):
                if child_id not in known:
                    known.add(child_id)
                    ordered.append(child_id)
            index += 1
        return ordered

    @staticmethod
    def _check_series_matches_config(
        dataset_series: DatasetSeries[T_DataType],
        data_import_config: peh.DataImportConfig,
        lineage: set[str],
    ) -> None:
        """
        Every observation indexed by the series must be configured by
        the import config or derived from it; otherwise the tree would
        silently mix two unrelated imports.
        """
        unknown = sorted(
            {
                observation_id
                for dataset in dataset_series.parts.values()
                for observation_id in dataset.observation_ids
                if observation_id not in lineage
            }
        )
        if unknown:
            raise ValueError(
                f"DatasetSeries {dataset_series.label!r} holds "
                "observations that are neither configured by nor "
                "derived from data import config "
                f"{data_import_config.id!r}: {', '.join(unknown)}."
            )

    def _observation_designs(
        self,
        cache_view: CacheContainerView,
        observation_ids: list[str],
    ) -> list[tuple[str, Any, peh.ObservationDesign]]:
        """
        Resolve (observation id, observation, design) for each
        reachable observation. Observations or designs missing from
        the cache are skipped with a warning.
        """
        resolved: list[tuple[str, Any, peh.ObservationDesign]] = []
        for observation_id in observation_ids:
            observation = self._get_observation(cache_view, observation_id)
            if observation is None:
                logger.warning(
                    f"Observation {observation_id!r} is not in the cache; "
                    "it is left out of the study metadata."
                )
                continue
            design_id = observation.observation_design
            design = (
                cache_view.get(design_id, "ObservationDesign")
                if design_id is not None
                else None
            )
            if design is None:
                logger.warning(
                    f"ObservationDesign {design_id!r} of observation "
                    f"{observation_id!r} is not in the cache; the "
                    "observation is left out of the study metadata."
                )
                continue
            resolved.append((observation_id, observation, design))
        return resolved

    def _collect_control_ids(
        self,
        cache_view: CacheContainerView,
        designs: list[tuple[str, Any, peh.ObservationDesign]],
    ) -> set[str]:
        """
        LOD / LOQ `control` observable properties are assay quality
        controls, not catalogue variables.
        """
        control_ids: set[str] = set()
        for _, _, design in designs:
            for spec in _as_list(design.observable_property_specifications):
                op = self._resolve_observable_property(cache_view, spec)
                if op is None:
                    continue
                if (
                    _as_text(op.observation_result_type) == "control"
                    and op.id not in control_ids
                ):
                    control_ids.add(op.id)
        return control_ids

    def _collect_schema_control_ids(
        self,
        cache_view: CacheContainerView,
        dataset_series: DatasetSeries[T_DataType],
    ) -> set[str]:
        """
        Classify `control` observable properties the same way as in
        `_collect_control_ids`, but driven by the dataset schemas
        instead of the observation designs: a schema element whose
        observation design is missing from the cache would otherwise
        escape the exclusion despite `exclude_control_variables`.
        """
        control_ids: set[str] = set()
        for dataset in dataset_series.parts.values():
            if dataset.schema is None:
                continue
            for element in dataset.schema.elements.values():
                op_id = element.observable_property_id
                if op_id is None or op_id in control_ids:
                    continue
                op = cache_view.get(op_id, "ObservableProperty")
                if op is None:
                    continue
                if _as_text(op.observation_result_type) == "control":
                    control_ids.add(op.id)
        return control_ids

    #### VARIABLE CATALOGUE ####

    def _catalogue_section(
        self,
        cache_view: CacheContainerView,
        designs: list[tuple[str, Any, peh.ObservationDesign]],
        control_ids: set[str],
        structure_by_op: dict[str, dict],
    ) -> list[dict[str, Any]]:
        """
        Per reachable observation, its observable properties (model
        grain). Each observable property is emitted under the first
        observation that specifies it.
        """
        seen: set[str] = set()
        observations: list[dict[str, Any]] = []
        for observation_id, observation, design in designs:
            properties: list[dict[str, Any]] = []
            for spec in _as_list(design.observable_property_specifications):
                op = self._resolve_observable_property(cache_view, spec)
                if op is None or op.id in seen:
                    continue
                if op.id in control_ids:
                    continue
                seen.add(op.id)
                variable = self._variable_tree(cache_view, op, spec)
                structure_by_op[op.id] = variable
                properties.append(variable)
            observations.append(
                {
                    "id": observation_id,
                    "label": self._label_of(observation),
                    "observable_properties": properties,
                }
            )
        return observations

    def _variable_tree(
        self,
        cache_view: CacheContainerView,
        op: peh.ObservableProperty,
        spec: peh.ObservablePropertySpecification | None = None,
    ) -> dict[str, Any]:
        variable: dict[str, Any] = {
            "id": op.id,
            "label": getattr(op, "short_name", None)
            or getattr(op, "ui_label", None),
            "name": getattr(op, "name", None),
            "kind": _as_text(op.observation_result_type),
            "value_type": _as_text(op.value_type),
            "unit": _as_text(op.unit),
            "categorical": op.categorical,
            "multivalued": op.multivalued,
            "required": op.required,
            "value_options": [
                self._option_key(option)
                for option in _as_list(op.value_options)
            ],
            "groups": self._grouping_labels(cache_view, op.grouping_id_list),
        }
        semantics = self._semantics_tree(cache_view, op)
        if semantics is not None:
            variable["semantics"] = semantics
        calculation_design = None
        if spec is not None:
            calculation_design = getattr(spec, "calculation_design", None)
        if calculation_design is None:
            calculation_design = getattr(op, "calculation_design", None)
        if calculation_design is not None:
            calculation = self._calculation_tree(
                cache_view, calculation_design
            )
            if calculation is not None:
                variable["calculation"] = calculation
        return variable

    @staticmethod
    def _option_key(option: Any) -> str | None:
        for attr in ("key", "value", "label"):
            text = _as_text(getattr(option, attr, None))
            if text is not None:
                return text
        return None

    def _grouping_labels(
        self, cache_view: CacheContainerView, grouping_id_list: Any
    ) -> list[str]:
        labels = []
        for group_id in _as_list(grouping_id_list):
            group = cache_view.get(group_id, "Grouping")
            labels.append(self._label_of(group, group_id))
        return labels

    def _semantics_tree(
        self, cache_view: CacheContainerView, op: peh.ObservableProperty
    ) -> dict[str, Any] | None:
        """
        The analyte chain of an indicator measurement: indicator ->
        matrix / biochemical entity, plus quantity kind and
        constraints. Returns None when the observable property has no
        resolvable indicator (nothing loaded). Only the first
        resolvable indicator is emitted; further ones are logged.
        """
        indicators = [
            (indicator_id, indicator)
            for indicator_id in _as_list(op.has_observable_property_type)
            if (indicator := cache_view.get(indicator_id, "IndicatorSubClass"))
            is not None
        ]
        if not indicators:
            return None
        if len(indicators) > 1:
            logger.warning(
                f"ObservableProperty {op.id!r} resolves to "
                f"{len(indicators)} indicators; only the first "
                f"({indicators[0][0]!r}) is emitted under semantics."
            )
        indicator_id, indicator = indicators[0]
        matrix_id = getattr(indicator, "matrix", None)
        matrix = (
            cache_view.get(matrix_id, "MatrixSubClass") if matrix_id else None
        )
        biochem_id = getattr(indicator, "biochementity", None)
        biochem = (
            cache_view.get(biochem_id, "BioChemEntitySubClass")
            if biochem_id
            else None
        )
        return {
            "indicator": {
                "id": indicator_id,
                "label": self._label_of(indicator, indicator_id),
                "definition": _clean_text(indicator.description),
                "indicator_type": _as_text(indicator.indicator_type),
                "quantity_kind": _as_text(indicator.quantity_kind),
                "exact_matches": [
                    _as_text(match)
                    for match in _as_list(indicator.exact_matches)
                ],
                "relevant_observable_entity_types": [
                    _as_text(entity_type)
                    for entity_type in _as_list(
                        indicator.relevant_observable_entity_types
                    )
                ],
                "suggester": _as_text(indicator.suggester),
            },
            "matrix": {
                "id": matrix_id,
                "label": self._label_of(matrix, matrix_id),
                "definition": _clean_text(
                    getattr(matrix, "description", None)
                ),
                "exact_matches": [
                    _as_text(match)
                    for match in _as_list(
                        getattr(matrix, "exact_matches", None)
                    )
                ],
            },
            "biochem_entity": {
                "id": biochem_id,
                "label": self._label_of(biochem, biochem_id),
                "definition": _clean_text(
                    getattr(biochem, "description", None)
                ),
                # BioChemEntitySubClass.exact_matches holds CHEBI ids
                "exact_matches": [
                    _as_text(match)
                    for match in _as_list(
                        getattr(biochem, "exact_matches", None)
                    )
                ],
                "aliases": _as_list(getattr(biochem, "aliases", None)),
                "molecular_weight_gram_per_mol": _as_number(
                    getattr(biochem, "molweight_grampermol", None)
                ),
                "groups": _as_list(getattr(biochem, "group_labels", None)),
                "is_metabolite_of": [
                    _as_text(metabolite)
                    for metabolite in _as_list(
                        getattr(biochem, "is_metabolite_of", None)
                    )
                ],
            },
            "quantity_kind": _as_text(indicator.quantity_kind),
            "constraints": [
                getattr(constraint, "constraint_id", constraint)
                for constraint in _as_list(indicator.constraints)
            ],
        }

    def _calculation_tree(
        self,
        cache_view: CacheContainerView,
        calculation_design: peh.CalculationDesign,
    ) -> dict[str, Any] | None:
        """
        Function and input/output links of a derived (calculation)
        variable, making the derivation graph explicit.
        """
        implementation = calculation_design.calculation_implementation
        if implementation is None:
            return None
        inputs: list[dict[str, Any]] = []
        for kwarg in _as_list(implementation.function_kwargs):
            reference = getattr(kwarg, "contextual_field_reference", None)
            source_id = (
                getattr(reference, "field_label", None)
                if reference is not None
                else None
            )
            source = (
                cache_view.get(source_id, "ObservableProperty")
                if source_id
                else None
            )
            inputs.append(
                {
                    "argument": getattr(kwarg, "mapping_name", None),
                    # execution resolves inputs by observation + property
                    # (dataops: context_lookup), so both are needed to
                    # pin the dependency when observations share a
                    # property.
                    "source_observation": (
                        getattr(reference, "dataset_label", None)
                        if reference is not None
                        else None
                    ),
                    "source_variable": source_id,
                    "source_label": (
                        getattr(source, "short_name", None)
                        or getattr(source, "ui_label", None)
                    )
                    if source
                    else None,
                    "value": getattr(kwarg, "value", None),
                }
            )
        return {
            "name": getattr(calculation_design, "calculation_name", None),
            "function": getattr(implementation, "function_name", None),
            "inputs": inputs,
            "results": [
                getattr(result, "mapping_name", None)
                for result in _as_list(implementation.function_results)
            ],
        }

    #### DATASETS ####

    def _datasets_section(
        self,
        dataset_series: DatasetSeries[T_DataType],
        structure_by_op: dict[str, dict],
        control_ids: set[str],
    ) -> list[dict[str, Any]]:
        datasets: list[dict[str, Any]] = []
        for dataset_label, dataset in dataset_series.parts.items():
            assert dataset.schema is not None
            variables: list[dict[str, Any]] = []
            for (
                element_label,
                element,
            ) in dataset.schema.elements.items():
                if element.observable_property_id in control_ids:
                    continue
                op_tree = structure_by_op.get(element.observable_property_id)
                variables.append(
                    {
                        "label": element_label,
                        "observable_property": op_tree
                        if op_tree is not None
                        else {"id": element.observable_property_id},
                        "data_type": self.map_data_type(element),
                        "primary_key": element_label
                        in dataset.schema.primary_keys,
                    }
                )
            datasets.append(
                {
                    "label": dataset_label,
                    "described_by": dataset.described_by,
                    "observations": sorted(dataset.observation_ids),
                    "variables": variables,
                }
            )
        return datasets

    #### PROVENANCE ####

    def _provenance_section(
        self,
        dataset_series: DatasetSeries[T_DataType],
        data_import_config: peh.DataImportConfig,
        cache_view: CacheContainerView,
        metadata_config: metadata_dto.StudyMetadataConfig,
        lineage: set[str],
        validation_report: "ValidationErrorReportCollection | None",
    ) -> dict[str, Any]:
        """
        What produced this metadata: source config / layout ids, the
        dataset sections, the derivation chain and the pypeh /
        peh_model versions. The validation report is accepted from
        the caller, never run here; it is embedded in its JSON form.
        Caller-provided `extra_provenance` fields are appended but may
        not override any of these built-in fields, and their values
        must be JSON-serializable (finite str / int / float / bool /
        None / list / str-keyed dict); NaN, Infinity and
        self-referencing containers raise ValueError like any other
        unsupported value.
        """
        provenance: dict[str, Any] = {
            "series_label": dataset_series.label,
            "data_import_config": data_import_config.id,
            "data_layout": data_import_config.layout,
            "sections": [
                {
                    "dataset": dataset.label,
                    "described_by": dataset.described_by,
                }
                for dataset in dataset_series.parts.values()
            ],
            "derived_observations": [
                {
                    "derived_observation": derived.id,
                    "was_derived_from": derived.was_derived_from,
                }
                for derived in cache_view.get_all("DerivedObservation")
                if getattr(derived, "id", None) in lineage
            ],
            "pypeh_version": _package_version("pypeh"),
            "peh_model_version": _package_version("peh_model"),
            "validation_report": (
                {
                    observation_id: report.model_dump(mode="json")
                    for observation_id, report in validation_report.items()
                }
                if validation_report is not None
                else None
            ),
        }
        collisions = sorted(
            set(metadata_config.extra_provenance) & set(provenance)
        )
        if collisions:
            raise ValueError(
                "StudyMetadataConfig.extra_provenance may not override "
                f"built-in provenance fields: {', '.join(collisions)}."
            )
        for key, value in metadata_config.extra_provenance.items():
            if not isinstance(key, str):
                raise ValueError(
                    "StudyMetadataConfig.extra_provenance key of "
                    f"type {type(key).__name__}; expected str — "
                    "convert it with str(...)."
                )
            _check_json_value(value, key)
        provenance.update(metadata_config.extra_provenance)
        return provenance

    #### HELPERS ####

    @staticmethod
    def _get_observation(
        cache_view: CacheContainerView, observation_id: str
    ) -> Any | None:
        return cache_view.get(observation_id, "Observation") or cache_view.get(
            observation_id, "DerivedObservation"
        )

    @staticmethod
    def _resolve_observable_property(
        cache_view: CacheContainerView, spec: Any
    ) -> peh.ObservableProperty | None:
        reference = getattr(spec, "observable_property", None)
        if reference is None:
            return None
        op_id = reference if isinstance(reference, str) else reference.id
        return cache_view.get(op_id, "ObservableProperty")

    @staticmethod
    def _label_of(entity: Any, reference: str | None = None) -> str | None:
        if entity is None:
            return reference
        for attr in ("ui_label", "name", "short_name"):
            value = getattr(entity, attr, None)
            if value:
                return value
        return getattr(entity, "id", None) or reference
