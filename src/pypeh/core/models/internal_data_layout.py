from __future__ import annotations

from collections import defaultdict
import itertools
import logging
import uuid

from dataclasses import dataclass, field
from peh_model import peh
from typing import TYPE_CHECKING, Generic, Sequence

from pypeh.core.cache.containers import CacheContainerView
from pypeh.core.models.proxy import TypedLazyProxy
from pypeh.core.models.typing import T_DataType
from pypeh.core.models.constants import ObservablePropertyValueType

if TYPE_CHECKING:
    from typing import Any
    from pypeh.core.interfaces.outbound.dataops import OutDataOpsInterface


logger = logging.getLogger(__name__)
CSVW_CONTEXT = {"csvw": "http://www.w3.org/ns/csvw#"}
DCAT_CONTEXT = {"dcat": "http://www.w3.org/ns/dcat#"}


# TODO: Refactoring: relocate or add as a method on an appropriate class
def get_observations_from_data_import_config(data_import_config: peh.DataImportConfig, cache: CacheContainerView):
    observations = []
    for link in data_import_config.section_mapping.section_mapping_links:
        observations.extend([cache.get(observation_id, "Observation") for observation_id in link.observation_id_list])
    return observations


# TODO: Refactoring: relocate or add as a method on an appropriate class
# TODO: Refactoring: to be replaced with InternalDataLayout based implementation
# TODO: To be fixed: Does not account for observable_property_id reuse across datasets
def get_observable_property_id_to_dataset_label_dict(
    observable_property_id_list: Sequence[str], dependent_data: dict[str, dict[str, Sequence]] | dict[str, T_DataType]
):
    ret = {}
    for observable_property_id in observable_property_id_list:
        for k, v in dependent_data.items():
            if isinstance(v.observed_data, dict):
                dependent_property_id_list = v.observed_data.keys()
            elif hasattr(v.observed_data, "columns"):
                dependent_property_id_list = [str(c) for c in v.observed_data.columns]
            else:
                raise NotImplementedError(f"Unsupported observed_data type encountered while processing dataset {k}")

            if observable_property_id in dependent_property_id_list:
                ret[observable_property_id] = k
    return ret


@dataclass
class ObservationResultProxy(Generic[T_DataType]):
    observed_data: T_DataType
    observation_result_type: str = "measurement"
    id: uuid.UUID = uuid.uuid4()


class BiMap:
    def __init__(self):
        self.forward = {}
        self.backward = {}

    def insert(self, key, value):
        if key in self.forward or value in self.backward:
            raise ValueError("Duplicate key or value")
        self.forward[key] = value
        self.backward[value] = key

    def get_by_key(self, key):
        return self.forward.get(key)

    def get_by_value(self, value):
        return self.backward.get(value)

    def __repr__(self):
        return self.forward.__repr__()

    def __len__(self):
        return len(self.forward)


class ElementToObservableProperty(BiMap):
    """
    Bidirectional mapping of DataLayoutElements and ObservableProperties.
    Note this enforces DataLayoutElement.label uniqueness per DataLayoutSection
    """

    @classmethod
    def from_peh(cls, data_layout_section: peh.DataLayoutSection) -> ElementToObservableProperty:
        ret = cls()
        elements = getattr(data_layout_section, "elements")
        if elements is None:
            pass
        for element in elements:
            assert isinstance(element, peh.DataLayoutElement)
            observable_property_id = element.observable_property
            assert (
                observable_property_id is not None
            ), f"could not find an observable_property field for {element.label}"
            _ = ret.insert(element.label, observable_property_id)

        return ret

    def collect_schema(self, cache_view: CacheContainerView) -> dict[str, ObservablePropertyValueType]:
        ret = {}

        for element_label, observable_property_id in self.forward.items():
            observable_property = cache_view.get(observable_property_id, "ObservableProperty")
            assert observable_property is not None, f"could not find an observable_property for {element_label}"
            value_type = getattr(observable_property, "value_type")
            ret[element_label] = ObservablePropertyValueType(value_type)

        return ret


class InternalDataLayout(dict[str, ElementToObservableProperty]):
    # TODO: add entity tree: should have structure of observations

    @classmethod
    def from_peh(cls, data_layout: peh.DataLayout) -> InternalDataLayout:
        ret = cls()
        sections = getattr(data_layout, "sections")
        if sections is None:
            raise ValueError("No sections found in DataLayout")
        for section in sections:
            label = getattr(section, "ui_label")
            ret[label] = ElementToObservableProperty.from_peh(section)

        return ret

    def collect_schema(
        self, cache_view: CacheContainerView
    ) -> dict[str, dict[str, ObservablePropertyValueType]] | None:
        ret = {}
        try:
            for section_label, bimap in self.items():
                ret[section_label] = bimap.collect_schema(cache_view)

            return ret
        except Exception as _:
            logger.info("Could not infer schema with provided cache_view")
            return


@dataclass
class JoinSpec:
    left_element: str
    left_dataset: str
    right_element: str
    right_dataset: str


@dataclass
class DatasetSchemaElement:
    label: str
    observable_property_id: str
    data_type: ObservablePropertyValueType

    @classmethod
    def from_peh_data_layout_element(cls, data_layout_element: peh.DataLayoutElement, cache_view: CacheContainerView):
        label = data_layout_element.label
        assert label is not None
        observable_property_id = data_layout_element.observable_property
        assert observable_property_id is not None
        observable_property = cache_view.get(observable_property_id, "ObservableProperty")
        assert isinstance(observable_property, peh.ObservableProperty)
        data_type = getattr(observable_property, "value_type")

        return cls(
            label=label,
            observable_property_id=observable_property.id,
            data_type=ObservablePropertyValueType(data_type),
        )


@dataclass
class ElementReference:
    dataset_label: str = field(metadata={"id": "resource", "context": CSVW_CONTEXT})
    element_label: str = field(metadata={"id": "columnReference", "context": CSVW_CONTEXT})

    __metadata__ = {
        "id": "csvw:TableReference",
        "context": CSVW_CONTEXT,
    }


@dataclass
class ForeignKey:
    element_label: str = field(metadata={"id": "columnReference", "context": CSVW_CONTEXT})
    reference: ElementReference = field(metadata={"id": "reference", "context": CSVW_CONTEXT})

    __metadata__ = {
        "id": "csvw:ForeignKey",
        "context": CSVW_CONTEXT,
    }


@dataclass
class DatasetSchema:
    elements: dict[str, DatasetSchemaElement]
    primary_keys: set[str] | None = None
    foreign_keys: dict[str, ForeignKey] = field(default_factory=dict)

    __metadata__ = {
        "id": "csvw:Schema",
        "context": CSVW_CONTEXT,
    }

    def __post_init__(self):
        self._type = self.get_type_annotations()
        self._elements_by_observable_property = self.build_observable_property_index()

    def get_type_annotations(self) -> dict[str, ObservablePropertyValueType]:
        ret: dict[str, ObservablePropertyValueType] = dict()
        for element in self.elements.values():
            data_type = element.data_type
            if data_type is not None:
                ret[element.label] = data_type

        return ret

    def build_observable_property_index(self) -> dict[str, str]:
        elements_by_observable_property: dict[str, str] = {}
        for element_label, element in self.elements.items():
            elements_by_observable_property[element.observable_property_id] = element_label
        return elements_by_observable_property

    def get_type(self, element_label: str) -> ObservablePropertyValueType:
        return self._type[element_label]

    def get_element_by_label(self, element_label: str) -> DatasetSchemaElement | None:
        return self.elements.get(element_label, None)

    def get_element_by_observable_property_id(self, observable_property_id: str) -> DatasetSchemaElement | None:
        element_label = self._elements_by_observable_property[observable_property_id]
        return self.get_element_by_label(element_label=element_label)

    def get_observable_property_ids(self) -> list[str]:
        return [element.observable_property_id for element in self.elements.values()]

    def subset(self, element_group: Sequence[str]) -> DatasetSchema:
        elements = {}
        foreign_keys = {}

        for element_label in element_group:
            element = self.get_element_by_label(element_label)
            assert element is not None, f"Element with label {element_label} not found in schema"
            elements[element_label] = element
            if element_label in self.foreign_keys:
                foreign_keys[element_label] = self.foreign_keys[element_label]
            elements[element_label] = element

        return DatasetSchema(
            elements=elements,
            primary_keys=self.primary_keys,
            foreign_keys=foreign_keys,
        )

    def relabel(self, element_mapping: dict[str, str]):
        elements: dict[str, DatasetSchemaElement] = dict()
        all_type_info: dict[str, ObservablePropertyValueType] = dict()
        elements_by_observable_property: dict[str, str] = {}
        primary_keys: set[str] | None = set()
        foreign_keys: dict[str, ForeignKey] = {}

        for element_label, new_element_label in element_mapping.items():
            schema_element = self.elements.pop(element_label)
            elements[new_element_label] = schema_element
            schema_element.label = new_element_label

            # _type dict
            type_info = self._type.pop(element_label)
            all_type_info[new_element_label] = type_info

            # _elements_by_observable_property
            observable_property_id = schema_element.observable_property_id
            element_label = self._elements_by_observable_property.pop(observable_property_id)
            elements_by_observable_property[observable_property_id] = element_label

            # primary_keys
            if self.primary_keys is not None:
                if element_label in self.primary_keys:
                    self.primary_keys.discard(element_label)
                    primary_keys.add(new_element_label)

            # foreign_keys
            if element_label in self.foreign_keys:
                foreign_key = self.foreign_keys.pop(element_label)
                foreign_keys[new_element_label] = foreign_key

        if len(self.elements) > 0:
            for element in self.elements:
                if element in elements:
                    raise ValueError("Schema element label {element} is non unique")
            elements = {**elements, **self.elements}
            all_type_info = {**all_type_info, **self._type}
            elements_by_observable_property = {
                **elements_by_observable_property,
                **self._elements_by_observable_property,
            }
            foreign_keys = {**foreign_keys, **self.foreign_keys}
            if self.primary_keys is not None:
                primary_keys = primary_keys | self.primary_keys
            else:
                assert len(primary_keys) == 0
                primary_keys = None

        num_elements = len(elements)
        assert len(elements_by_observable_property) == num_elements
        assert len(all_type_info) == num_elements
        assert len(foreign_keys) <= num_elements

        self.elements = elements
        self._elements_by_observable_property = elements_by_observable_property
        self._type = all_type_info
        self.foreign_keys = foreign_keys
        self.primary_keys = primary_keys

    def __len__(self):
        return len(self.elements)

    @classmethod
    def from_peh_data_layout_elements(
        cls, data_layout_elements: list[peh.DataLayoutElement], cache_view: CacheContainerView
    ):
        schema_elements = {}
        processed_foreign_keys = {}
        processed_primary_keys = set()
        for element in data_layout_elements:
            assert isinstance(element, peh.DataLayoutElement)
            element_label = element.label
            assert element_label is not None
            observable_property_id = element.observable_property
            assert observable_property_id is not None
            foreign_key = element.foreign_key_link
            if foreign_key is not None:
                assert isinstance(foreign_key, peh.DataLayoutElementLink)
                section_id = foreign_key.section
                assert isinstance(section_id, str)
                foreign_key_element_label = foreign_key.label
                assert foreign_key_element_label is not None
                section = cache_view.get(section_id, "DataLayoutSection")
                assert section is not None
                assert section.ui_label is not None
                foreign_key_object = ForeignKey(
                    element_label=element_label,
                    reference=ElementReference(
                        dataset_label=section.ui_label,
                        element_label=foreign_key_element_label,
                    ),
                )
                processed_foreign_keys[element_label] = foreign_key_object

            is_primary_key = element.is_observable_entity_key
            if is_primary_key is not None:
                if is_primary_key:
                    processed_primary_keys.add(element_label)

            schema_elements[element_label] = DatasetSchemaElement.from_peh_data_layout_element(element, cache_view)

        return cls(
            elements=schema_elements,
            foreign_keys=processed_foreign_keys,
            primary_keys=processed_primary_keys,
        )

    def detect_join(
        self,
        dataset_label: str,
        other_schema: DatasetSchema,
        other_dataset_label: str,
    ) -> list[JoinSpec] | None:
        # Case 1: A → B directly
        for col, fk in self.foreign_keys.items():
            if fk.reference.dataset_label == other_dataset_label:
                return [
                    JoinSpec(
                        left_element=fk.element_label,
                        left_dataset=dataset_label,
                        right_element=fk.reference.element_label,
                        right_dataset=other_dataset_label,
                    )
                ]

        # Case 2: B → A directly
        for col, fk in other_schema.foreign_keys.items():
            if fk.reference.dataset_label == dataset_label:
                return [
                    JoinSpec(
                        left_element=fk.reference.element_label,
                        left_dataset=dataset_label,
                        right_element=fk.element_label,
                        right_dataset=other_dataset_label,
                    )
                ]

        # Case 3: shared third dataset: requires two `JoinSpec`
        refs_a = {
            fk.reference.dataset_label: (fk.element_label, fk.reference.element_label)
            for fk in self.foreign_keys.values()
        }
        refs_b = {
            fk.reference.dataset_label: (fk.element_label, fk.reference.element_label)
            for fk in other_schema.foreign_keys.values()
        }

        shared = set(refs_a.keys()).intersection(set(refs_b.keys()))
        if shared:
            shared_label = next(iter(shared))
            a_col_local, a_other = refs_a[shared_label]
            b_col_local, b_other = refs_b[shared_label]

            return [
                JoinSpec(
                    left_element=a_col_local,
                    left_dataset=dataset_label,
                    right_element=a_other,
                    right_dataset=shared_label,
                ),
                JoinSpec(left_element=b_col_local, left_dataset="", right_element=b_other, right_dataset=shared_label),
            ]

        return None


@dataclass(kw_only=True)
class Resource:
    label: str
    identifier: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)

    __metadata__ = {
        "id": "dcat:resource",
        "context": DCAT_CONTEXT,
    }

    def add_metadata(self, metadata_key: str, metadata_value: Any) -> bool:
        if metadata_key in self.metadata:
            raise KeyError(f"{metadata_key} key already used in metadata mapping")
        self.metadata[metadata_key] = metadata_value

        return True

    @property
    def described_by(self) -> str | peh.NamedThingId | None:
        return self.metadata.get("described_by", None)


@dataclass(kw_only=True)
class Dataset(Resource, Generic[T_DataType]):
    schema: DatasetSchema
    data: T_DataType | None = field(default=None)
    part_of: DatasetSeries | None = field(default=None)

    __metadata__ = {
        "id": "dcat:dataset",
        "context": DCAT_CONTEXT,
    }

    def get_type_annotations(self) -> dict[str, ObservablePropertyValueType]:
        return self.schema.get_type_annotations()

    @classmethod
    def from_peh_datalayout_section(
        cls,
        data_layout_section: peh.DataLayoutSection,
        cache_view: CacheContainerView,
        part_of_dataset_series: DatasetSeries | None = None,
    ) -> Dataset[T_DataType]:
        label = data_layout_section.ui_label
        assert label is not None
        elements = getattr(data_layout_section, "elements")
        if elements is not None:
            for element in elements:
                assert isinstance(element, peh.DataLayoutElement)
                observable_property_id = element.observable_property
                assert (
                    observable_property_id is not None
                ), f"could not find an observable_property field for {element.label}"

        schema = DatasetSchema.from_peh_data_layout_elements(elements, cache_view)

        ret: Dataset[T_DataType] = cls(
            label=label,
            schema=schema,
            part_of=part_of_dataset_series,
        )
        _ = ret.add_metadata("described_by", data_layout_section.id)

        return ret

    @property
    def non_empty(self):
        return self.metadata.get("non_empty_dataset_elements", None)

    def get_schema_element_by_label(self, element_label: str) -> DatasetSchemaElement | None:
        return self.schema.get_element_by_label(element_label)

    def get_schema_element_by_observable_property_id(self, observable_property_id: str) -> DatasetSchemaElement | None:
        return self.schema.get_element_by_observable_property_id(observable_property_id)

    def get_observable_property_ids(self) -> list[str]:
        return self.schema.get_observable_property_ids()

    def get_primary_keys(self) -> set[str] | None:
        return self.schema.primary_keys

    def subset(
        self,
        element_groups: dict[str, list[str]],
        dataops_adapter: OutDataOpsInterface,
        metadata: dict[str, dict] | None = None,
    ) -> bool:
        dataset_series: DatasetSeries = self.part_of  # type: ignore[attr-defined] ## can't figure out the type checker issue
        if dataset_series is not None:
            _ = dataset_series.parts.pop(self.label)

        for dataset_label, element_group in element_groups.items():
            # split data
            # TODO: allow subsetting based on identifying_observable_properties
            data_subset = dataops_adapter.subset(
                data=self.data,
                element_group=element_group,
            )
            # split schema
            schema_subset = self.schema.subset(element_group)
            # add both to new dataset
            new_dataset = Dataset(
                schema=schema_subset,
                label=dataset_label,
                data=data_subset,
                part_of=dataset_series,
            )
            if dataset_series is not None:
                dataset_series[dataset_label] = new_dataset
            if metadata is not None:
                new_dataset.metadata.update(metadata.get(dataset_label, {}))

        return True

    def relabel(self, element_mapping: dict[str, str], dataops_adapter: OutDataOpsInterface) -> bool:
        # uniqueness check
        if len(set(element_mapping.values())) != len(element_mapping):
            raise ValueError("Not all values in the element_mapping are unique")
        # relabel schema
        _ = self.schema.relabel(element_mapping)
        # relabel dataset
        self.data = dataops_adapter.relabel(self.data, element_mapping)

        return True

    def resolve_join(self, other: Dataset) -> list[JoinSpec] | None:
        schema = self.schema
        assert schema is not None
        return schema.detect_join(dataset_label=self.label, other_schema=other.schema, other_dataset_label=other.label)


@dataclass(kw_only=True)
class DatasetSeries(Resource, Generic[T_DataType]):
    parts: dict[str, Dataset[T_DataType]]

    __metadata__ = {
        "id": "dcat:datasetSeries",
        "context": DCAT_CONTEXT,
    }

    @classmethod
    def from_peh_datalayout(cls, data_layout: peh.DataLayout, cache_view: CacheContainerView) -> DatasetSeries:
        parts = dict()
        label = data_layout.ui_label
        assert label is not None
        sections = getattr(data_layout, "sections")
        if sections is None:
            raise ValueError("No sections found in DataLayout")
        for section in sections:
            label = getattr(section, "ui_label")
            parts[label] = Dataset.from_peh_datalayout_section(
                section,
                cache_view,
            )

        ret = cls(label=label, parts=parts)
        for dataset in ret.parts.values():
            dataset.part_of = ret
        _ = ret.add_metadata("described_by", data_layout.id)

        return ret

    def get_type_annotations(self) -> dict[str, dict[str, ObservablePropertyValueType]]:
        ret: dict[str, dict[str, ObservablePropertyValueType]] = dict()
        for dataset in self.parts.values():
            label = dataset.label
            ret[label] = dataset.get_type_annotations()

        return ret

    def add_data(
        self, dataset_label: str, data: T_DataType, non_empty_dataset_elements: list[str] | None = None
    ) -> bool:
        dataset = self.parts.get(dataset_label, None)
        assert dataset is not None
        assert dataset.data is None
        observable_property_ids = dataset.get_observable_property_ids()

        if len(observable_property_ids) == 0:
            return False
        dataset.data = data
        dataset.metadata["non_empty_dataset_elements"] = non_empty_dataset_elements

        return True

    def subset_dataset(
        self,
        dataset_label: str,
        element_groups: dict[str, list[str]],
        dataops_adapter: OutDataOpsInterface,
        metadata: dict[str, dict[str, str]] | None = None,
    ) -> bool:
        """
        Element_groups: Contains the new `Dataset.label` as key, and the list[DatasetSchemaElement.label] to be included in the new `Dataset`
        """

        dataset = self.get(dataset_label)
        assert dataset is not None
        return dataset.subset(element_groups, dataops_adapter=dataops_adapter, metadata=metadata)

    def relabel_dataset(
        self, dataset_label: str, element_mapping: dict[str, str], dataops_adapter: OutDataOpsInterface
    ):
        dataset = self.get(dataset_label)
        assert dataset is not None
        return dataset.relabel(element_mapping, dataops_adapter=dataops_adapter)

    # TEMP: a better API to tackle casting the schema from one underlying object to
    # another will crystallize when other use cases pop up.
    def _cast_from_data_import_config(
        self,
        data_import_config: peh.DataImportConfig,
        dataops_adapter: OutDataOpsInterface,
        cache_view: CacheContainerView,
    ):
        """
        This method transforms a DatasetSeries from a DataLayout view on the data to an
        Observation view on the data. The transformation is done in place.

        :param data_import_config: Description
        :type data_import_config: peh.DataImportConfig
        :param dataops_adapter: DataImportAdapter with `subset()` and `relabel()` functionality
        :type dataops_adapter: OutDataOpsInterface
        :param cache_view: Immutable view on the cache associated with a session.
        :type cache_view: CacheContainerView
        """

        described_by = self.metadata.get("described_by", None)
        data_layout = data_import_config.layout
        if described_by is not None:
            assert (
                data_import_config.layout == described_by
            ), f"`DatasetSeries` {self.identifier} described by `DataLayout`{described_by} and not by provided `DataLayout` {data_layout}"

        layout_section_mapping = data_import_config.section_mapping
        section_mapping_links = getattr(layout_section_mapping, "section_mapping_links")
        assert section_mapping_links is not None
        visited = set()

        for section_mapping_link in section_mapping_links:
            section = cache_view.get(section_mapping_link.section, "DataLayoutSection")
            assert section is not None
            section_label = getattr(section, "ui_label", None)
            assert section_label is not None, f"section_label for {section_mapping_link.section} is None"
            dataset = self.get(section_label)
            assert dataset is not None, f"section_label {section_label} not found in `DatasetSeries`"
            observable_property_ids = set(dataset.get_observable_property_ids())
            new_observable_property_ids = set()
            element_label_mapping = {}
            element_groups = defaultdict(list)
            all_metadata = defaultdict(dict)

            for observation_id in section_mapping_link.observation_id_list:
                assert isinstance(observation_id, str)
                observation = cache_view.get(observation_id, "Observation")
                assert observation is not None, f"observation with id {observation_id} is None"
                observation_design = observation.observation_design
                if isinstance(observation_design, str):
                    raise NotImplementedError  # TODO: get from cache
                elif isinstance(observation_design, TypedLazyProxy):
                    raise NotImplementedError
                else:
                    assert isinstance(
                        observation_design, peh.ObservationDesign
                    ), "observation_design for observation {observation.id} has wrong type"

                assert isinstance(observation_design.identifying_observable_property_id_list, list)
                assert isinstance(observation_design.required_observable_property_id_list, list)
                assert isinstance(observation_design.optional_observable_property_id_list, list)

                for observable_property_id in itertools.chain(
                    observation_design.identifying_observable_property_id_list,
                    observation_design.required_observable_property_id_list,
                    observation_design.optional_observable_property_id_list,
                ):
                    element = dataset.get_schema_element_by_observable_property_id(observable_property_id)
                    assert element is not None
                    new_observable_property_ids.add(observable_property_id)
                    element_label_mapping[element.label] = observable_property_id
                    element_groups[observation_id].append(element.label)
                all_metadata[observation_id]["described_by"] = observation_id
                visited.add(observation_id)

            assert (
                new_observable_property_ids <= observable_property_ids
            ), f"The following `ObservableProperty`s could not be found in `DataLayoutSection` {section.id}: {','.join(obs for obs in (new_observable_property_ids - observable_property_ids))}"
            _ = self.subset_dataset(
                dataset_label=section_label,
                element_groups=element_groups,
                dataops_adapter=dataops_adapter,
                metadata=all_metadata,
            )

        for observation_id in section_mapping_link.observation_id_list:
            _ = self.relabel_dataset(
                dataset_label=observation_id,
                element_mapping=element_label_mapping,
                dataops_adapter=dataops_adapter,
            )

        # This removes data without a mapping from DataLayout to Observation
        to_remove = set(self.parts) - visited
        for dataset_label in to_remove:
            self.parts.pop(dataset_label)

    def resolve_join(self, left_dataset_label: str, right_dataset_label: str) -> list[JoinSpec] | None:
        left = self.get(left_dataset_label)
        assert left is not None
        right = self.get(right_dataset_label)
        assert right is not None
        return left.resolve_join(right)

    def resolve_all_joins(self) -> dict[frozenset, list[JoinSpec] | None]:
        ret = {}
        for combo in itertools.combinations(self.parts, 2):
            key = frozenset(combo)
            ret[key] = self.resolve_join(*combo)
        return ret

    def matches(self, dataset: dict[str, T_DataType], adapter) -> bool:
        ret = True
        for dataset_label in self.parts:
            if dataset_label not in dataset:
                return False

        # TODO finish comparison
        # this_dataset = self.get(dataset_label)
        # assert this_dataset is not None
        # type_annotations = this_dataset.get_type_annotations()
        # dataset_fields = adapter.get_element_labels(dataset[dataset_label])

        return ret

    @property
    def data_import_config(self) -> str | None:
        return self.metadata.get("data_import_config", None)

    def __len__(self):
        return len(self.parts)

    def get(self, key, default=None) -> Dataset | None:
        try:
            return self[key]
        except KeyError:
            return default

    def __getitem__(self, key: str) -> Dataset | None:
        return self.parts.get(key)

    def __setitem__(self, key: str, value: Dataset) -> None:
        self.parts[key] = value

    def update(self, *args, **kwargs):
        if args:
            if len(args) > 1:
                raise TypeError("update expected at most 1 arguments, " "got %d" % len(args))
            assert len(args) == 1
            other = dict(args[0])
            for key in other:
                self.parts[key] = other[key]
        for key in kwargs:
            self.parts[key] = kwargs[key]

    def __iter__(self):
        return iter(self.parts)
