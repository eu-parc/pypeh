"""
Each of these Interface subclasses provides a protocol on how
the corresponding Adapter subclass should be implemented.

Usage: TODO: add usage info

"""

from __future__ import annotations
import importlib

import itertools
import logging

from abc import abstractmethod
from peh_model.peh import (
    DataImportConfig,
    DataLayout,
    DataLayoutSection,
    ValidationDesign,
    EntityList,
    Observation,
    ObservableProperty,
    ObservationDesign,
)
from typing import TYPE_CHECKING, Generic, cast, List

from pypeh.core.cache.containers import CacheContainerView
from pypeh.core.models.internal_data_layout import Dataset, DatasetSeries, InternalDataLayout, ObservationResultProxy
from pypeh.core.models.internal_data_layout import get_observable_property_id_to_dataset_label_dict
from pypeh.core.models.typing import T_DataType
from pypeh.core.models.settings import FileSystemSettings
from pypeh.core.models import validation_dto
from pypeh.core.models.proxy import TypedLazyProxy
from pypeh.core.session.connections import ConnectionManager

if TYPE_CHECKING:
    from typing import Sequence, Mapping, Any
    from pypeh.core.models.validation_errors import ValidationErrorReport

logger = logging.getLogger(__name__)


class OutDataOpsInterface(Generic[T_DataType]):
    """
    Example of DataOps methods
    def validate(self, data: Mapping, config: Mapping):
        pass

    def summarize(self, dat: Mapping, config: Mapping):
        pass
    """

    @abstractmethod
    def _join_data(
        self,
        identifying_observable_property_ids: list[str],
        data: dict[str, Sequence] | T_DataType,
        dependent_data: Mapping[str, dict[str, Sequence]] | Mapping[str, T_DataType],
        dependent_observable_property_ids: set[str],
        observable_property_id_to_dataset_label_dict: dict[str, str],
    ) -> T_DataType:
        raise NotImplementedError

    # TEMP: to replace _join_data
    @abstractmethod
    def _join_dataset(
        self,
        identifying_observable_property_ids: list[str],
        dataset: Dataset[T_DataType],
        dependent_data: Mapping[str, Dataset[T_DataType]],
        dependent_observable_property_ids: set[str],
        observable_property_id_to_dataset_label_dict: dict[str, str],
    ) -> T_DataType:
        raise NotImplementedError

    @abstractmethod
    def select_field(self, dataset, field_label: str):
        raise NotImplementedError

    @abstractmethod
    def get_element_labels(self, data: T_DataType) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def get_element_values(self, data: T_DataType, element_label: str) -> set[str]:
        raise NotImplementedError

    @abstractmethod
    def subset(
        self,
        data: T_DataType,
        element_group: list[str],
        id_group: list[tuple[Any]] | None = None,
        identifying_elements: list[str] | None = None,
    ) -> T_DataType: ...

    def relabel(self, data: T_DataType, element_mapping: dict[str, str]) -> T_DataType: ...

    @abstractmethod
    def collect(self, datasets: dict):
        raise NotImplementedError


class ValidationInterface(OutDataOpsInterface, Generic[T_DataType]):
    @abstractmethod
    def _validate(
        self, data: dict[str, Sequence] | T_DataType, config: validation_dto.ValidationConfig
    ) -> ValidationErrorReport:
        raise NotImplementedError

    @classmethod
    def get_default_adapter_class(cls):
        try:
            adapter_module = importlib.import_module(
                "pypeh.adapters.outbound.validation.pandera_adapter.validation_adapter"
            )
            adapter_class = getattr(adapter_module, "DataFrameValidationAdapter")
        except Exception as e:
            logger.error("Exception encountered while attempting to import a Pandera-based DataFrameAdapter")
            raise e
        return adapter_class

    # TEMP method signature, to replace `validate`
    def _validate_dataset(
        self,
        dataset: Dataset[T_DataType],
        dependent_dataset_series: DatasetSeries[T_DataType] | None = None,
        cache_view: CacheContainerView | None = None,
    ) -> ValidationErrorReport:
        assert dataset.data is not None
        to_validate: T_DataType = dataset.data

        # Get Dataset level validations if they exist for the describing DataLayoutSection
        dataset_validations = []
        layout_section_id = dataset.described_by
        if layout_section_id:
            layout_section = cache_view.get(layout_section_id, "DataLayoutSection")
            assert layout_section is not None
            assert isinstance(layout_section, DataLayoutSection)
            if layout_section.validation_designs:
                for vd in layout_section.validation_designs:
                    dataset_validation = validation_dto.ValidationDesign.from_peh(vd, cache_view)
                    # For an expression that relies on a field reference spec for its arguments, set the validation arguments
                    # as the actual values from the dataset (e.g. for an "is_in" check on a foreign key relation)
                    if vd.validation_expression.validation_arg_contextual_field_references:
                        arg_values = vd.validation_expression.validation_arg_values
                        for ref in vd.validation_expression.validation_arg_contextual_field_references:
                            arg_values.extend(
                                dependent_dataset_series[ref.dataset_label].data.get_column(ref.field_label).to_list()
                            )
                        dataset_validation.expression.arg_values = arg_values
                        dataset_validation.expression.arg_columns = None
                    dataset_validations.append(dataset_validation)

        validation_config = validation_dto.ValidationConfig.from_dataset(
            dataset,
            dataset_validations,
            cache_view,
        )
        join_required = False
        # check whether data requires join to perform validation (cross DataLayoutSection validation)
        dependent_observable_property_ids = validation_config.dependent_observable_property_ids
        if dependent_observable_property_ids is not None:
            join_required = len(dependent_observable_property_ids) > 0

        if join_required:
            if dependent_dataset_series is None:
                me = f"`dependent_data` is required to perform all validations. One or more of the following `ObservableProperty`s cannot be found in the current `DataLayoutSection`: {', '.join(dependent_observable_property_ids)}"
                logger.error(me)
                raise ValueError(me)
            else:
                assert (
                    dependent_observable_property_ids is not None
                ), "dependent_observable_property_ids in `ValidationInterface.validate` should not be None"
                assert dependent_dataset_series is not None
                # TEMP: looping over datasets should not be necessary when contextual_field_references are implemented
                observable_property_id_to_dataset_label_dict = dict()
                for observable_property_id in dependent_observable_property_ids:
                    for dataset_label in dependent_dataset_series:
                        dependent_dataset = dependent_dataset_series[dataset_label]
                        assert dependent_dataset is not None
                        all_obs_props = set(dependent_dataset.get_observable_property_ids())
                        if observable_property_id in all_obs_props:
                            observable_property_id_to_dataset_label_dict[observable_property_id] = dataset_label
                            break

                identifying_obs_prop_id_list = dataset.schema.primary_keys
                assert (
                    identifying_obs_prop_id_list is not None
                ), "identifying_obs_prop_id_list in `ValidationInterface.validate` should not be None"

                to_validate = self._join_dataset(
                    identifying_observable_property_ids=identifying_obs_prop_id_list,
                    dataset=dataset,
                    dependent_data=dependent_dataset_series.parts,
                    dependent_observable_property_ids=dependent_observable_property_ids,
                    observable_property_id_to_dataset_label_dict=observable_property_id_to_dataset_label_dict,
                )

        ret = self._validate(to_validate, validation_config)

        return ret

    def validate(
        self,
        data: dict[str, Sequence] | T_DataType,
        observation: Observation,
        observable_properties: List[ObservableProperty],
        dataset_validations: Sequence[ValidationDesign] | None = None,
        dependent_data: dict[str, dict[str, Sequence]] | dict[str, T_DataType] | None = None,
        cache_view: CacheContainerView | None = None,
    ) -> ValidationErrorReport:
        # TODO: Temporary column label read from dataset; to be replaced with smarter object
        if isinstance(data, dict):
            observable_property_id_selection = data.keys()
        elif hasattr(data, "columns"):
            observable_property_id_selection = [str(c) for c in data.columns]
        else:
            raise NotImplementedError(
                f"Unsupported data argument encountered while validating observation {observation.id}"
            )

        validation_config = validation_dto.ValidationConfig.from_observation(
            observation, observable_properties, dataset_validations, cache_view=cache_view
        )
        to_validate = data
        join_required = False
        # check whether data requires join to perform validation (cross DataLayoutSection validation)
        dependent_observable_property_ids = validation_config.dependent_observable_property_ids
        if dependent_observable_property_ids is not None:
            # This test is obsolete, and should have been tested already when
            # constructing the list of dependent_observable_property_ids
            for obs_prop in dependent_observable_property_ids:
                if obs_prop not in observable_property_id_selection:
                    join_required = True
                    break

        if join_required:
            if dependent_data is None:
                me = f"`dependent_data` is required to perform all validations. One or more of the following `ObservableProperty`s cannot be found in the current `DataLayoutSection`: {', '.join(dependent_observable_property_ids)}"
                logger.error(me)
                raise ValueError(me)
            else:
                observable_property_id_to_dataset_label_dict = get_observable_property_id_to_dataset_label_dict(
                    dependent_observable_property_ids, dependent_data
                )
                identifying_obs_prop_id_list = getattr(
                    observation.observation_design, "identifying_observable_property_id_list", None
                )
                assert (
                    identifying_obs_prop_id_list is not None
                ), "identitfying_obs_prop_id_list in `ValidationInterface.validate` should not be None"
                assert (
                    observable_property_id_to_dataset_label_dict is not None
                ), "label_dict in `ValidationInterface.validate` should not be None"
                assert (
                    dependent_observable_property_ids is not None
                ), "dependent_observable_property_ids in `ValidationInterface.validate` should not be None"
                to_validate = self._join_data(
                    identifying_observable_property_ids=identifying_obs_prop_id_list,
                    data=data,
                    dependent_data=dependent_data,
                    dependent_observable_property_ids=dependent_observable_property_ids,
                    observable_property_id_to_dataset_label_dict=observable_property_id_to_dataset_label_dict,
                )

        ret = self._validate(to_validate, validation_config)

        return ret


class DataEnrichmentInterface(OutDataOpsInterface, Generic[T_DataType]):
    @abstractmethod
    def _enrich_data(self, data: dict[str, Sequence] | T_DataType, config: dict) -> T_DataType:
        raise NotImplementedError

    @classmethod
    def get_default_adapter_class(cls):
        try:
            adapter_module = importlib.import_module("pypeh.adapters.outbound.enrichment.dataframe_adapter")
            adapter_class = getattr(adapter_module, "DataFrameEnrichmentAdapter")
        except Exception as e:
            logger.error("Exception encountered while attempting to import enrichment DataFrameAdapter")
            raise e
        return adapter_class

    @abstractmethod
    def apply_joins(self, dataset, datasets, join_specs, node): ...

    @abstractmethod
    def apply_map(self, dataset, map_fn, field_label, output_dtype, base_fields, **kwargs): ...

    @abstractmethod
    def map_type(self, peh_value_type: str): ...


class DataImportInterface(OutDataOpsInterface, Generic[T_DataType]):
    @classmethod
    def get_default_adapter_class(cls):
        try:
            adapter_module = importlib.import_module(
                "pypeh.adapters.outbound.validation.pandera_adapter.validation_adapter"
            )
            adapter_class = getattr(adapter_module, "DataFrameValidationAdapter")
        except Exception as e:
            logger.error("Exception encountered while attempting to import a Pandera-based DataFrameAdapter")
            raise e
        return adapter_class

    @abstractmethod
    def import_data(self, source: str, config: FileSystemSettings) -> T_DataType | List[T_DataType]:
        raise NotImplementedError

    def import_data_layout(
        self,
        source: str,
        config: FileSystemSettings,
        **kwargs,
    ) -> DataLayout | List[DataLayout]:
        provider = ConnectionManager._create_adapter(config)
        layout = provider.load(source)
        if isinstance(layout, EntityList):
            layout = layout.layouts
        if isinstance(layout, list):
            if not all(isinstance(item, DataLayout) for item in layout):
                me = "Imported layouts should all be DataLayout instances"
                logger.error(me)
                raise TypeError(me)
            return cast(List[DataLayout], layout)

        elif isinstance(layout, DataLayout):
            return layout

        else:
            me = f"Imported layout should be a DataLayout instance not {type(layout)}"
            logger.error(me)
            raise TypeError(me)

    def _extract_observed_value_provenance(self) -> bool:
        return True

    def _normalize_observable_properties(self) -> bool:
        raise NotImplementedError

    def _raw_data_to_observation_data(
        self,
        raw_data: T_DataType,
        data_layout_element_labels: list[str],
        identifying_layout_element_label: str,
        entity_id_list: list[str] | None = None,
    ) -> T_DataType:
        raise NotImplementedError

    # TODO: Refactoring: to be replaced with InternalDataLayout based implementation
    def _data_layout_to_observation_results(
        self,
        raw_data: dict[str, T_DataType],
        data_import_config: DataImportConfig,
        cache_view: CacheContainerView,
        internal_data_layout: InternalDataLayout,
    ) -> dict[str, ObservationResultProxy[T_DataType]]:
        observed_data_dict = {}
        layout_section_mapping = data_import_config.section_mapping
        for section_mapping_link in layout_section_mapping.section_mapping_links:
            section = cache_view.get(section_mapping_link.section, "DataLayoutSection")
            section_label = getattr(section, "ui_label", None)
            assert section_label is not None, f"section_label for {section_mapping_link.section} is None"
            assert section_label in raw_data, f"section_label {section_label} not found"
            assert hasattr(
                raw_data[section_label], "columns"
            ), f"Unsupported data type for section_label {section_label}"
            bimap = internal_data_layout.get(section_label, None)
            assert bimap is not None

            for observation_id in section_mapping_link.observation_id_list:
                observation = cache_view.get(observation_id, "Observation")
                assert observation is not None, f"observation with id {observation_id} is None"
                observation_design = observation.observation_design
                if isinstance(observation_design, str):
                    raise NotImplementedError  # TODO: get from cache
                elif isinstance(observation_design, TypedLazyProxy):
                    raise NotImplementedError
                else:
                    assert isinstance(
                        observation_design, ObservationDesign
                    ), "observation_design for observation {observation.id} has wrong type"

                # create filter based on ObservableProperties per Observation
                assert isinstance(observation_design.identifying_observable_property_id_list, list)
                assert isinstance(observation_design.required_observable_property_id_list, list)
                assert isinstance(observation_design.optional_observable_property_id_list, list)
                observable_property_ids = list(
                    itertools.chain(
                        observation_design.identifying_observable_property_id_list,
                        observation_design.required_observable_property_id_list,
                        observation_design.optional_observable_property_id_list,
                    )
                )
                if len(observation_design.identifying_observable_property_id_list) > 1:
                    raise NotImplementedError
                identifying_observable_property = observation_design.identifying_observable_property_id_list[0]
                identifying_layout_element_label = bimap.get_by_value(identifying_observable_property)
                mapped_observable_property_ids = []
                for observable_property_id in observable_property_ids:
                    column_name = bimap.get_by_value(observable_property_id)
                    assert column_name is not None
                    mapped_observable_property_ids.append(column_name)

                # create filter based on entity_id_list
                entity_id_list = observation_design.observable_entity_id_list
                assert isinstance(entity_id_list, list)

                # Apply filter to raw_data
                filtered_df = self._raw_data_to_observation_data(
                    raw_data[section_label],
                    data_layout_element_labels=mapped_observable_property_ids,
                    identifying_layout_element_label=identifying_layout_element_label,
                    entity_id_list=entity_id_list,
                )

                # Rename column names
                new_column_names = [bimap.get_by_key(label) for label in filtered_df.columns]
                filtered_df.columns = new_column_names
                observed_data_dict[observation_id] = filtered_df

            del raw_data[section_label]

        transformed_results = {
            observation_id: ObservationResultProxy(
                observed_data=observed_data_dict[observation_id],
            )
            for observation_id in observed_data_dict.keys()
        }

        return transformed_results
