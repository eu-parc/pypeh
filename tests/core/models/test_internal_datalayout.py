import pytest
import peh_model.peh as peh
from dataclasses import asdict

from pypeh.core.cache.containers import (
    CacheContainer,
    CacheContainerFactory,
    CacheContainerView,
)
from pypeh.core.models.internal_data_layout import (
    Dataset,
    DatasetSeries,
    DatasetSchema,
    DatasetSchemaElement,
    ForeignKey,
    ElementReference,
    JoinSpec,
)
from pypeh.core.models.constants import ObservablePropertyValueType
from pypeh.core.utils.namespaces import NamespaceManager
from pypeh.adapters.persistence.hosts import DirectoryIO
from pypeh.core.cache.utils import load_entities_from_tree

from tests.test_utils.dirutils import get_absolute_path


@pytest.mark.core
class TestInternalDataLayout:
    @pytest.fixture(scope="class")
    def get_cache(self) -> CacheContainerView:
        source = get_absolute_path("input")
        container = CacheContainerFactory.new()
        host = DirectoryIO()
        roots = host.load(source, format="yaml")
        for root in roots:
            for entity in load_entities_from_tree(root):
                container.add(entity)

        return CacheContainerView(container)

    def test_dataset_contained_in_schema(self, get_cache):
        cache_view = get_cache
        layout_id = "peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA"
        layout = get_cache.get(layout_id, "DataLayoutLayout")
        dataset_series = DatasetSeries.from_peh_datalayout(
            layout,
            cache_view=cache_view,
        )
        dataset = dataset_series.parts.get("SAMPLETIMEPOINT_BS")
        assert isinstance(dataset, Dataset)
        result_success = dataset.contained_in_schema(
            ["id_sample", "adults_u_crt"]
        )
        assert result_success
        with pytest.raises(AssertionError, match=r".* my_imaginary_friend .*"):
            dataset.contained_in_schema(
                ["id_sample", "adults_u_crt", "my_imaginary_friend"]
            )

    @pytest.mark.parametrize("use_identifier_provider", [False, True])
    def test_dataset_series(self, get_cache, use_identifier_provider):
        cache_view = get_cache
        layout_id = "peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA"
        layout = get_cache.get(layout_id, "DataLayoutLayout")
        all_sections = set()
        for section in layout.sections:
            section_id = section.id
            if section.id is not None:
                all_sections.add(section_id)
        identifier_provider = None
        if use_identifier_provider:
            namespace_manager = NamespaceManager("https://w3id.org/peh/")
            identifier_provider = namespace_manager.get_identifier_provider()
        dataset_series = DatasetSeries.from_peh_datalayout(
            layout,
            cache_view=cache_view,
            identifier_provider=identifier_provider,
        )
        assert isinstance(dataset_series, DatasetSeries)
        assert (
            dataset_series.described_by
            == "peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA"
        )
        for dataset in dataset_series.parts.values():
            assert dataset.described_by in all_sections

        schema = dataset_series.get_type_annotations()
        expected_schema = {
            "SAMPLE": {
                "id_sample": ObservablePropertyValueType.STRING,
                "matrix": ObservablePropertyValueType.STRING,
            },
            "SAMPLETIMEPOINT_BS": {
                "id_sample": ObservablePropertyValueType.STRING,
                "adults_u_crt": ObservablePropertyValueType.DECIMAL,
            },
        }
        for key, subschema in expected_schema.items():
            for subkey, value in subschema.items():
                assert schema[key][subkey] == value

        if use_identifier_provider:
            assert dataset_series.identifier.startswith(
                "https://w3id.org/peh/dataset-series/"
            )

    def test_dataset_series_add_data(self, get_cache):
        cache_view = get_cache
        layout_id = "peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA"
        layout = get_cache.get(layout_id, "DataLayoutLayout")
        dataset_series = DatasetSeries.from_peh_datalayout(
            layout,
            cache_view=cache_view,
        )
        assert isinstance(dataset_series, DatasetSeries)

        dataset_failure = {
            "id_sample": [1, 2, 3],
            "adults_u_crt": [0.132, 1.452, 24.51],
            "my_imaginary_friend": [0.132, 1.452, 24.51],
        }

        with pytest.raises(AssertionError) as assertion_error:
            dataset_series.add_data(
                "SAMPLETIMEPOINT_BS",
                dataset_failure,
                list(dataset_failure.keys()),
            )
        assert (
            str(assertion_error.value)
            == "Data Schema Error: label(s) my_imaginary_friend are undefined"
        )

        dataset_success = {
            "id_sample": [1, 2, 3],
            "adults_u_crt": [0.132, 1.452, 24.51],
        }

        result_success = dataset_series.add_data(
            "SAMPLETIMEPOINT_BS", dataset_success, list(dataset_success.keys())
        )
        assert result_success is None

    def test_identifier_provider_assigns_class_specific_identifiers(self):
        namespace_manager = NamespaceManager("https://w3id.org/peh/")
        identifier_provider = namespace_manager.get_identifier_provider(
            suffix_strategy=lambda: "fixed-id"
        )
        dataset_series = DatasetSeries(
            label="series",
            identifier_provider=identifier_provider,
        )
        dataset = dataset_series.add_empty_dataset("dataset")
        schema_element = dataset_series.add_observable_property(
            observation_id="observation",
            observable_property_id="observable-property",
            data_type=ObservablePropertyValueType.STRING,
            dataset_label=dataset.label,
            element_label="element",
        )
        dataset.schema.add_foreign_key_link(
            element_label="element",
            foreign_key_dataset_label="dataset",
            foreign_key_element_label="element",
        )
        foreign_key = dataset.schema.foreign_keys["element"]

        assert (
            dataset_series.identifier
            == "https://w3id.org/peh/dataset-series/fixed-id"
        )
        assert dataset.identifier == "https://w3id.org/peh/dataset/fixed-id"
        assert (
            dataset.schema.identifier
            == "https://w3id.org/peh/dataset-schema/fixed-id"
        )
        assert (
            schema_element.identifier
            == "https://w3id.org/peh/dataset-schema-element/fixed-id"
        )
        assert (
            foreign_key.identifier
            == "https://w3id.org/peh/foreign-key/fixed-id"
        )

    def test_identifier_provider_preserves_existing_identifiers(self):
        namespace_manager = NamespaceManager("https://w3id.org/peh/")
        identifier_provider = namespace_manager.get_identifier_provider(
            suffix_strategy=lambda: "minted-id"
        )
        schema_element = DatasetSchemaElement(
            label="element",
            observable_property_id="observable-property",
            data_type=ObservablePropertyValueType.STRING,
            identifier="existing-schema-element-id",
            identifier_provider=identifier_provider,
        )
        foreign_key = ForeignKey(
            element_label="element",
            reference=ElementReference(
                dataset_label="dataset",
                element_label="element",
            ),
            identifier="existing-foreign-key-id",
            identifier_provider=identifier_provider,
        )
        schema = DatasetSchema(
            elements={"element": schema_element},
            foreign_keys={"element": foreign_key},
            identifier="existing-schema-id",
            identifier_provider=identifier_provider,
        )
        dataset = Dataset(
            label="dataset",
            identifier="existing-dataset-id",
            schema=schema,
            identifier_provider=identifier_provider,
        )
        dataset_series = DatasetSeries(
            label="series",
            identifier="existing-series-id",
            identifier_provider=identifier_provider,
        )
        dataset_series.register_dataset(dataset)

        assert dataset_series.identifier == "existing-series-id"
        assert dataset.identifier == "existing-dataset-id"
        assert dataset.schema.identifier == "existing-schema-id"
        assert (
            dataset.schema.elements["element"].identifier
            == "existing-schema-element-id"
        )
        assert (
            dataset.schema.foreign_keys["element"].identifier
            == "existing-foreign-key-id"
        )

    def test_add_observable_property_registers_resolved_label(self):
        dataset_series = DatasetSeries(label="series")
        dataset = dataset_series.add_empty_dataset("dataset")
        dataset.add_observation_to_index("obs")

        dataset_series.add_observable_property(
            observation_id="obs",
            observable_property_id="prop",
            data_type=ObservablePropertyValueType.STRING,
            dataset_label="dataset",
            element_label=None,
        )

        assert dataset_series.context_lookup("obs", "prop") == (
            "dataset",
            "prop",
        )

    def test_add_observation_registers_existing_identifying_label(self):
        container = CacheContainerFactory.new()
        observable_property = peh.ObservableProperty(
            id="prop",
            value_type="string",
        )
        container.add(observable_property)
        cache_view = CacheContainerView(container)

        dataset_series = DatasetSeries(label="series")
        dataset = dataset_series.add_empty_dataset("dataset")
        dataset.add_observation_to_index("source_obs")
        dataset_series.add_observable_property(
            observation_id="source_obs",
            observable_property_id="prop",
            data_type=ObservablePropertyValueType.STRING,
            dataset_label="dataset",
            element_label="subject_id",
            is_primary_key=True,
        )

        target_observation = peh.Observation(
            id="target_obs",
            observation_design="target_design",
        )
        identifying_spec = peh.ObservablePropertySpecification(
            observable_property="prop",
            specification_category=peh.ObservablePropertySpecificationCategory.identifying,
        )
        dataset_series.add_observation(
            dataset_label="dataset",
            observation=target_observation,
            labeled_observable_property_specifications={
                None: identifying_spec
            },
            cache_view=cache_view,
        )

        assert dataset_series.context_lookup("target_obs", "prop") == (
            "dataset",
            "subject_id",
        )

    def test_apply_context(self, get_cache):
        cache_view = get_cache
        layout_id = "peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA"
        layout = get_cache.get(layout_id, "DataLayoutLayout")
        all_sections = set()
        for section in layout.sections:
            section_id = section.id
            if section.id is not None:
                all_sections.add(section_id)
        dataset_series = DatasetSeries.from_peh_datalayout(
            layout,
            cache_view=cache_view,
        )
        assert isinstance(dataset_series, DatasetSeries)

        cache = cache_view._container
        assert isinstance(cache, CacheContainer)
        dataset_series.apply_context(cache)
        adults_u_crt = cache_view.get("peh:adults_u_crt", "ObservableProperty")
        expression = adults_u_crt.validation_designs[0].validation_expression
        contextual_field_reference = (
            expression.validation_subject_contextual_field_references[0]
        )
        assert contextual_field_reference.dataset_label == "SAMPLETIMEPOINT_BS"
        assert contextual_field_reference.field_label == "adults_u_crt"

<<<<<<< HEAD
    def test_from_peh_data_config_with_export_config_construction(
        self, get_cache
    ):
        cache_view = get_cache
        existing = cache_view.get(
            "peh:IMPORT_CONFIG_CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA",
            "DataImportConfig",
        )
        assert isinstance(existing, peh.DataImportConfig)

        data_export_config = peh.DataExportConfig(
            id="peh:EXPORT_CONFIG_CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA",
            layout=existing.layout,
            section_mapping=peh.DataImportSectionMapping(
                section_mapping_links=[
                    peh.DataImportSectionMappingLink(
                        section=link.section,
                        observation_id_list=list(link.observation_id_list),
                    )
                    for link in existing.section_mapping.section_mapping_links
                ]
            ),
        )

        target = DatasetSeries.from_peh_data_config(
            data_config=data_export_config,
            cache_view=cache_view,
        )
        via_import = DatasetSeries.from_peh_data_config(
            data_config=existing,
            cache_view=cache_view,
        )

        expected_dataset_labels = {
            cache_view.require(link.section, "DataLayoutSection").ui_label
            for link in data_export_config.section_mapping.section_mapping_links
        }
        assert set(target.parts) == expected_dataset_labels

        for link in data_export_config.section_mapping.section_mapping_links:
            dataset_label = cache_view.require(
                link.section, "DataLayoutSection"
            ).ui_label
            dataset = target.parts[dataset_label]
            for observation_id in link.observation_id_list:
                assert observation_id in dataset.observation_ids

            layout_section = cache_view.require(
                link.section, "DataLayoutSection"
            )
            element_labels_in_section = {
                element.label for element in layout_section.elements
            }
            schema_labels = set(dataset.get_element_labels())
            assert schema_labels.issubset(element_labels_in_section)

        assert dict(target._context_index) == dict(via_import._context_index)
        assert {
            obs_id: set(labels) for obs_id, labels in target._obs_index.items()
        } == {
            obs_id: set(labels)
            for obs_id, labels in via_import._obs_index.items()
        }

        sample_key, expected_pair = next(iter(target._context_index.items()))
        sample_observation_id, sample_property_id = sample_key
        assert (
            target.context_lookup(sample_observation_id, sample_property_id)
            == expected_pair
        )

=======
    def test_from_peh_data_config_matches_import_config(self, get_cache):
        cache_view = get_cache
        data_import_config = cache_view.get(
            "peh:IMPORT_CONFIG_CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA",
            "DataImportConfig",
        )
        assert isinstance(data_import_config, peh.DataImportConfig)

        via_import = DatasetSeries.from_peh_data_import_config(
            data_import_config=data_import_config,
            cache_view=cache_view,
        )
        via_shared = DatasetSeries.from_peh_data_config(
            data_config=data_import_config,
            cache_view=cache_view,
        )

        assert set(via_import.parts) == set(via_shared.parts)
        for dataset_label, dataset in via_import.parts.items():
            other = via_shared.parts[dataset_label]
            assert dataset.observation_ids == other.observation_ids
            assert set(dataset.get_element_labels()) == set(
                other.get_element_labels()
            )
        assert dict(via_import._context_index) == dict(
            via_shared._context_index
        )
        assert {
            obs_id: set(labels)
            for obs_id, labels in via_import._obs_index.items()
        } == {
            obs_id: set(labels)
            for obs_id, labels in via_shared._obs_index.items()
        }

>>>>>>> ab721c1 (add from peh_data_config class method)
    def test_one_observation_to_many_datasets(self):
        ds = DatasetSeries(label="test")
        with pytest.raises(AssertionError, match=r".*obs_test.*"):
            ds._register_observation(
                observation_id="obs_test", dataset_label="test"
            )
        d = Dataset(label="test-dataset")
        d2 = Dataset(label="test-dataset-2")
        ds.parts[d.label] = d
        ds.parts[d2.label] = d2
        ds._register_observation(
            observation_id="obs_test", dataset_label=d.label
        )
        assert len(ds._obs_index) == 1


@pytest.mark.core
class TestJoinConditions:
    def test_left_to_right_join(self):
        left_schema = DatasetSchema(
            elements={
                "b_id": DatasetSchemaElement(
                    label="b_id",
                    observable_property_id="prop",
                    data_type=ObservablePropertyValueType.STRING,
                )
            },
            foreign_keys={
                "b_id": ForeignKey(
                    element_label="b_id",
                    reference=ElementReference(
                        dataset_label="B", element_label="id"
                    ),
                )
            },
        )

        right_schema = DatasetSchema(
            elements={
                "id": DatasetSchemaElement(
                    label="id",
                    observable_property_id="prop",
                    data_type=ObservablePropertyValueType.STRING,
                )
            }
        )

        join = left_schema.detect_join("A", right_schema, "B")
        assert join is not None
        assert isinstance(join, JoinSpec)
        assert join.left_elements == ("b_id",)
        assert join.right_elements == ("id",)
        assert join.right_dataset == "B"

    def test_right_to_left_join(self):
        left_schema = DatasetSchema(
            elements={
                "id": DatasetSchemaElement(
                    label="id",
                    observable_property_id="prop",
                    data_type=ObservablePropertyValueType.STRING,
                )
            }
        )

        right_schema = DatasetSchema(
            elements={
                "a_id": DatasetSchemaElement(
                    label="a_id",
                    observable_property_id="prop",
                    data_type=ObservablePropertyValueType.STRING,
                )
            },
            foreign_keys={
                "a_id": ForeignKey(
                    element_label="a_id",
                    reference=ElementReference(
                        dataset_label="A", element_label="id"
                    ),
                )
            },
        )

        join = left_schema.detect_join("A", right_schema, "B")
        assert join is not None
        assert isinstance(join, JoinSpec)
        assert join.left_elements == ("id",)
        assert join.right_elements == ("a_id",)
        assert join.right_dataset == "B"

    def test_shared_reference_join(self):
        left_schema = DatasetSchema(
            elements={
                "c_ref": DatasetSchemaElement(
                    label="c_ref",
                    observable_property_id="c_ref",
                    data_type=ObservablePropertyValueType.STRING,
                )
            },
            foreign_keys={
                "c_ref": ForeignKey(
                    element_label="c_ref",
                    reference=ElementReference(
                        dataset_label="C", element_label="id"
                    ),
                )
            },
        )

        right_schema = DatasetSchema(
            elements={
                "c_fk": DatasetSchemaElement(
                    label="c_fk",
                    observable_property_id="c_fk",
                    data_type=ObservablePropertyValueType.STRING,
                )
            },
            foreign_keys={
                "c_fk": ForeignKey(
                    element_label="c_fk",
                    reference=ElementReference(
                        dataset_label="C", element_label="id"
                    ),
                )
            },
        )

        join = left_schema.detect_join("A", right_schema, "B")
        assert join is not None
        assert isinstance(join, JoinSpec)
        assert join.left_elements == ("c_ref",)
        assert join.right_elements == ("c_fk",)
        assert join.right_dataset == "B"

    def test_shared_reference_join_none_without_shared_ref_columns(self):
        left_schema = DatasetSchema(
            elements={
                "c_ref": DatasetSchemaElement(
                    label="c_ref",
                    observable_property_id="c_ref",
                    data_type=ObservablePropertyValueType.STRING,
                )
            },
            foreign_keys={
                "c_ref": ForeignKey(
                    element_label="c_ref",
                    reference=ElementReference(
                        dataset_label="C", element_label="id_other"
                    ),
                )
            },
        )
        right_schema = DatasetSchema(
            elements={
                "c_fk": DatasetSchemaElement(
                    label="c_fk",
                    observable_property_id="c_fk",
                    data_type=ObservablePropertyValueType.STRING,
                )
            },
            foreign_keys={
                "c_fk": ForeignKey(
                    element_label="c_fk",
                    reference=ElementReference(
                        dataset_label="C", element_label="id"
                    ),
                )
            },
        )

        join = left_schema.detect_join("A", right_schema, "B")
        assert join is None

    def test_direct_multi_column_join(self):
        left_schema = DatasetSchema(
            elements={
                "k1": DatasetSchemaElement(
                    label="k1",
                    observable_property_id="k1",
                    data_type=ObservablePropertyValueType.STRING,
                ),
                "k2": DatasetSchemaElement(
                    label="k2",
                    observable_property_id="k2",
                    data_type=ObservablePropertyValueType.STRING,
                ),
            },
            foreign_keys={
                "k1": ForeignKey(
                    element_label="k1",
                    reference=ElementReference(
                        dataset_label="B", element_label="id1"
                    ),
                ),
                "k2": ForeignKey(
                    element_label="k2",
                    reference=ElementReference(
                        dataset_label="B", element_label="id2"
                    ),
                ),
            },
        )
        right_schema = DatasetSchema(
            elements={
                "id1": DatasetSchemaElement(
                    label="id1",
                    observable_property_id="id1",
                    data_type=ObservablePropertyValueType.STRING,
                ),
                "id2": DatasetSchemaElement(
                    label="id2",
                    observable_property_id="id2",
                    data_type=ObservablePropertyValueType.STRING,
                ),
            }
        )

        join = left_schema.detect_join("A", right_schema, "B")
        assert join is not None
        assert join.left_elements == ("k1", "k2")
        assert join.right_elements == ("id1", "id2")
        assert join.right_dataset == "B"

    def test_shared_hub_multi_column_join(self):
        left_schema = DatasetSchema(
            elements={
                "h1_local": DatasetSchemaElement(
                    label="h1_local",
                    observable_property_id="h1_local",
                    data_type=ObservablePropertyValueType.STRING,
                ),
                "h2_local": DatasetSchemaElement(
                    label="h2_local",
                    observable_property_id="h2_local",
                    data_type=ObservablePropertyValueType.STRING,
                ),
            },
            foreign_keys={
                "h1_local": ForeignKey(
                    element_label="h1_local",
                    reference=ElementReference(
                        dataset_label="HUB", element_label="id1"
                    ),
                ),
                "h2_local": ForeignKey(
                    element_label="h2_local",
                    reference=ElementReference(
                        dataset_label="HUB", element_label="id2"
                    ),
                ),
            },
        )
        right_schema = DatasetSchema(
            elements={
                "h1_fk": DatasetSchemaElement(
                    label="h1_fk",
                    observable_property_id="h1_fk",
                    data_type=ObservablePropertyValueType.STRING,
                ),
                "h2_fk": DatasetSchemaElement(
                    label="h2_fk",
                    observable_property_id="h2_fk",
                    data_type=ObservablePropertyValueType.STRING,
                ),
            },
            foreign_keys={
                "h1_fk": ForeignKey(
                    element_label="h1_fk",
                    reference=ElementReference(
                        dataset_label="HUB", element_label="id1"
                    ),
                ),
                "h2_fk": ForeignKey(
                    element_label="h2_fk",
                    reference=ElementReference(
                        dataset_label="HUB", element_label="id2"
                    ),
                ),
            },
        )

        join = left_schema.detect_join("A", right_schema, "B")
        assert join is not None
        assert join.left_elements == ("h1_local", "h2_local")
        assert join.right_elements == ("h1_fk", "h2_fk")
        assert join.right_dataset == "B"

    def test_dataset_series_resolve_join_via_shared_parent(self):
        dataset_a = Dataset(
            label="A",
            schema=DatasetSchema(
                elements={
                    "id": DatasetSchemaElement(
                        label="id",
                        observable_property_id="id",
                        data_type=ObservablePropertyValueType.STRING,
                    )
                }
            ),
        )
        dataset_b = Dataset(
            label="B",
            schema=DatasetSchema(
                elements={
                    "a_id": DatasetSchemaElement(
                        label="a_id",
                        observable_property_id="a_id",
                        data_type=ObservablePropertyValueType.STRING,
                    )
                },
                foreign_keys={
                    "a_id": ForeignKey(
                        element_label="a_id",
                        reference=ElementReference(
                            dataset_label="A", element_label="id"
                        ),
                    )
                },
            ),
        )
        dataset_c = Dataset(
            label="C",
            schema=DatasetSchema(
                elements={
                    "a_id": DatasetSchemaElement(
                        label="a_id",
                        observable_property_id="a_id",
                        data_type=ObservablePropertyValueType.STRING,
                    )
                },
                foreign_keys={
                    "a_id": ForeignKey(
                        element_label="a_id",
                        reference=ElementReference(
                            dataset_label="A", element_label="id"
                        ),
                    )
                },
            ),
        )
        series = DatasetSeries(
            label="series",
            parts={"A": dataset_a, "B": dataset_b, "C": dataset_c},
        )

        join = series.resolve_join("B", "C")
        assert join is not None
        assert join.left_elements == ("a_id",)
        assert join.right_elements == ("a_id",)
        assert join.right_dataset == "C"


@pytest.mark.core
class TestToTarget:
    @staticmethod
    def _strip_identifiers(obj):
        if isinstance(obj, dict):
            return {
                k: TestToTarget._strip_identifiers(v)
                for k, v in obj.items()
                if k != "identifier"
            }
        if isinstance(obj, list):
            return [TestToTarget._strip_identifiers(v) for v in obj]
        if isinstance(obj, set):
            return {TestToTarget._strip_identifiers(v) for v in obj}
        return obj

    @classmethod
    def _assert_schema_equal_ignoring_identifiers(
        cls, actual: DatasetSchema, expected: DatasetSchema
    ) -> None:
        actual_dict = cls._strip_identifiers(asdict(actual))
        expected_dict = cls._strip_identifiers(asdict(expected))
        assert actual_dict == expected_dict

    @pytest.fixture(scope="class")
    def dataset_series_input(self) -> tuple[DatasetSeries, DatasetSchema]:
        # Schema for urine_lab
        partial_urine_lab_schema = DatasetSchema(
            elements={
                "id_subject": DatasetSchemaElement(
                    label="id_subject",
                    observable_property_id="peh:id_subject",
                    data_type=ObservablePropertyValueType.STRING,
                ),
                "matrix": DatasetSchemaElement(
                    label="matrix",
                    observable_property_id="peh:matrix",
                    data_type=ObservablePropertyValueType.STRING,
                ),
            },
            primary_keys={"id_subject"},
            foreign_keys={},
        )

        urine_lab_schema = DatasetSchema(
            elements={
                "id_subject": DatasetSchemaElement(
                    label="id_subject",
                    observable_property_id="peh:id_subject",
                    data_type=ObservablePropertyValueType.STRING,
                ),
                "matrix": DatasetSchemaElement(
                    label="matrix",
                    observable_property_id="peh:matrix",
                    data_type=ObservablePropertyValueType.STRING,
                ),
                "crt": DatasetSchemaElement(
                    label="crt",
                    observable_property_id="peh:crt",
                    data_type=ObservablePropertyValueType.FLOAT,
                ),
                "crt_lod": DatasetSchemaElement(
                    label="crt_lod",
                    observable_property_id="peh:crt_lod",
                    data_type=ObservablePropertyValueType.FLOAT,
                ),
                "crt_loq": DatasetSchemaElement(
                    label="crt_loq",
                    observable_property_id="peh:crt_loq",
                    data_type=ObservablePropertyValueType.FLOAT,
                ),
                "sg": DatasetSchemaElement(
                    label="sg",
                    observable_property_id="peh:sg",
                    data_type=ObservablePropertyValueType.FLOAT,
                ),
            },
            primary_keys={"id_subject"},
            foreign_keys={},
        )

        # Schema for analyticalinfo
        analyticalinfo_schema = DatasetSchema(
            elements={
                "id_subject": DatasetSchemaElement(
                    label="id_subject",
                    observable_property_id="peh:id_subject",
                    data_type=ObservablePropertyValueType.STRING,
                ),
                "biomarkercode": DatasetSchemaElement(
                    label="biomarkercode",
                    observable_property_id="peh:biomarkercode",
                    data_type=ObservablePropertyValueType.STRING,
                ),
                "matrix": DatasetSchemaElement(
                    label="matrix",
                    observable_property_id="peh:matrix",
                    data_type=ObservablePropertyValueType.STRING,
                ),
                "labinstitution": DatasetSchemaElement(
                    label="labinstitution",
                    observable_property_id="peh:labinstitution",
                    data_type=ObservablePropertyValueType.STRING,
                ),
            },
            primary_keys={"id_subject", "biomarkercode"},
            foreign_keys={
                "fk_subject": ForeignKey(
                    element_label="id_subject",
                    reference=ElementReference(
                        dataset_label="urine_lab",
                        element_label="id_subject",
                    ),
                )
            },
        )

        # --- DATASET INSTANCES ------------------------------------------------------
        partial_urine_lab_dataset = Dataset(
            label="partial_urine_lab",
            schema=partial_urine_lab_schema,
            data=None,
            observation_ids=set(["peh:urine_lab_this"]),
        )

        analyticalinfo_dataset = Dataset(
            label="analyticalinfo",
            schema=analyticalinfo_schema,
            data=None,
            observation_ids=set(["peh:analyticalinfo_obs"]),
        )

        # --- DATASET SERIES ---------------------------------------------------------

        series = DatasetSeries(
            label="urine_study_series",
            parts={
                "analyticalinfo": analyticalinfo_dataset,
                "partial_urine_lab": partial_urine_lab_dataset,
            },
        )
        # Make the reverse link (Dataset.part_of)
        partial_urine_lab_dataset.part_of = series
        analyticalinfo_dataset.part_of = series
        series.build_indices()

        return series, urine_lab_schema

    @pytest.fixture(scope="class")
    def cache_view(self) -> CacheContainerView:
        ods = [
            peh.ObservationDesign(
                id="peh:urine_lab_other_design",
                observable_property_specifications=[
                    peh.ObservablePropertySpecification(
                        observable_property="peh:id_subject",
                        specification_category=peh.ObservablePropertySpecificationCategory.identifying,
                    ),
                    peh.ObservablePropertySpecification(
                        observable_property="peh:crt",
                        specification_category=peh.ObservablePropertySpecificationCategory.required,
                    ),
                    peh.ObservablePropertySpecification(
                        observable_property="peh:crt_lod",
                        specification_category=peh.ObservablePropertySpecificationCategory.required,
                    ),
                    peh.ObservablePropertySpecification(
                        observable_property="peh:crt_loq",
                        specification_category=peh.ObservablePropertySpecificationCategory.required,
                    ),
                    peh.ObservablePropertySpecification(
                        observable_property="peh:sg",
                        specification_category=peh.ObservablePropertySpecificationCategory.required,
                    ),
                ],
            )
        ]
        obs = [
            peh.Observation(
                id="peh:urine_lab_other",
                ui_label="urine_lab_other",
                observation_design="peh:urine_lab_other_design",
            ),
        ]
        observable_properties = [
            peh.ObservableProperty(
                id="peh:id_subject",
                ui_label="id_subject",
                value_type="float",
            ),
            peh.ObservableProperty(
                id="peh:crt",
                ui_label="crt",
                value_type="float",
            ),
            peh.ObservableProperty(
                id="peh:crt_lod",
                ui_label="crt_lod",
                value_type="float",
            ),
            peh.ObservableProperty(
                id="peh:crt_loq",
                ui_label="crt_loq",
                value_type="float",
            ),
            peh.ObservableProperty(
                id="peh:sg",
                ui_label="sg",
                value_type="float",
            ),
        ]

        container = CacheContainerFactory.new()
        for entity_list in (ods, obs, observable_properties):
            for entity in entity_list:
                container.add(entity)
        return CacheContainerView(container)

    def test_add_observation(self, dataset_series_input, cache_view):
        obs = cache_view.get("peh:urine_lab_other", "Observation")
        assert isinstance(obs, peh.Observation)
        obs_design = cache_view.get(
            obs.observation_design, "ObservationDesign"
        )
        assert isinstance(obs_design, peh.ObservationDesign)
        source_dataset_series, expected_schema = dataset_series_input
        assert isinstance(source_dataset_series, DatasetSeries)
        labeled_observable_property_specifications = {}
        for spec in obs_design.observable_property_specifications:
            obsprop = cache_view.get(
                spec.observable_property, "ObservableProperty"
            )
            labeled_observable_property_specifications[obsprop.ui_label] = spec
        source_dataset_series.add_observation(
            dataset_label="partial_urine_lab",
            observation=obs,
            labeled_observable_property_specifications=labeled_observable_property_specifications,
            cache_view=cache_view,
        )
        partial_urine_data = source_dataset_series["partial_urine_lab"]
        assert partial_urine_data is not None
        self._assert_schema_equal_ignoring_identifiers(
            partial_urine_data.schema, expected_schema
        )

        expected_observation_index = {
            "peh:analyticalinfo_obs": {"analyticalinfo"},
            "peh:urine_lab_this": {"partial_urine_lab"},
            "peh:urine_lab_other": {"partial_urine_lab"},
        }
        expected_context_index = {
            # analyticalinfo_obs
            ("peh:analyticalinfo_obs", "peh:id_subject"): (
                "analyticalinfo",
                "id_subject",
            ),
            ("peh:analyticalinfo_obs", "peh:biomarkercode"): (
                "analyticalinfo",
                "biomarkercode",
            ),
            ("peh:analyticalinfo_obs", "peh:matrix"): (
                "analyticalinfo",
                "matrix",
            ),
            ("peh:analyticalinfo_obs", "peh:labinstitution"): (
                "analyticalinfo",
                "labinstitution",
            ),
            # partial_urine_lab (this)
            ("peh:urine_lab_this", "peh:id_subject"): (
                "partial_urine_lab",
                "id_subject",
            ),
            ("peh:urine_lab_this", "peh:matrix"): (
                "partial_urine_lab",
                "matrix",
            ),
            # partial_urine_lab (other)
            ("peh:urine_lab_other", "peh:id_subject"): (
                "partial_urine_lab",
                "id_subject",
            ),
            ("peh:urine_lab_other", "peh:crt"): ("partial_urine_lab", "crt"),
            ("peh:urine_lab_other", "peh:crt_loq"): (
                "partial_urine_lab",
                "crt_loq",
            ),
            ("peh:urine_lab_other", "peh:sg"): ("partial_urine_lab", "sg"),
            ("peh:urine_lab_other", "peh:crt_lod"): (
                "partial_urine_lab",
                "crt_lod",
            ),
        }
        assert source_dataset_series._obs_index == expected_observation_index
        assert (
            dict(source_dataset_series._context_index)
            == expected_context_index
        )

    def test_register_observable_property_rejects_context_remap(self):
        dataset_series = DatasetSeries(label="context_collision")
        dataset_series.add_empty_dataset("first_dataset")
        dataset_series.add_empty_dataset("second_dataset")
        dataset_series._register_observable_property(
            "peh:measure", "peh:observation", "first_dataset", "measure"
        )

        with pytest.raises(
            ValueError,
            match=(
                "already contains observation .* and observable property "
                ".* cannot remap"
            ),
        ):
            dataset_series._register_observable_property(
                "peh:measure",
                "peh:observation",
                "second_dataset",
                "measure",
            )

        assert dataset_series.context_lookup(
            "peh:observation", "peh:measure"
        ) == ("first_dataset", "measure")

    def test_add_observable_property_rejects_context_remap(self):
        dataset_series = DatasetSeries(label="context_collision")
        dataset_series.add_empty_dataset("first_dataset")
        dataset_series.add_empty_dataset("second_dataset")
        dataset_series.add_observable_property(
            observation_id="peh:observation",
            observable_property_id="peh:measure",
            data_type=ObservablePropertyValueType.STRING,
            dataset_label="first_dataset",
            element_label="measure",
        )

        with pytest.raises(ValueError, match="cannot remap"):
            dataset_series.add_observable_property(
                observation_id="peh:observation",
                observable_property_id="peh:measure",
                data_type=ObservablePropertyValueType.STRING,
                dataset_label="second_dataset",
                element_label="measure",
            )

        assert dataset_series.context_lookup(
            "peh:observation", "peh:measure"
        ) == ("first_dataset", "measure")
