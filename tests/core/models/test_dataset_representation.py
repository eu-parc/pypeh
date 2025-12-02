import pytest

from pypeh.core.cache.containers import CacheContainerFactory, CacheContainerView
from pypeh.core.models.internal_data_layout import (
    DatasetSeries,
    DatasetSchema,
    DatasetSchemaElement,
    ElementToObservableProperty,
    ForeignKey,
    ElementReference,
    InternalDataLayout,
    JoinSpec,
)
from pypeh.core.models.constants import ObservablePropertyValueType
from pypeh.adapters.outbound.persistence.hosts import DirectoryIO
from pypeh.core.cache.utils import load_entities_from_tree

from tests.test_utils.dirutils import get_absolute_path


@pytest.mark.core
class TestInternalDataLayout:
    @pytest.fixture(scope="class")
    def get_cache(self):
        source = get_absolute_path("input")
        container = CacheContainerFactory.new()
        host = DirectoryIO()
        roots = host.load(source, format="yaml")
        for root in roots:
            for entity in load_entities_from_tree(root):
                container.add(entity)

        return CacheContainerView(container)

    def test_bimap(self, get_cache):
        section_id = "SAMPLE_METADATA_SECTION_SAMPLE"
        section = get_cache.get(section_id, "DataLayoutSection")
        bimap = ElementToObservableProperty.from_peh(data_layout_section=section)
        expected = {"id_sample": "peh:adults_id_subject", "matrix": "peh:adults_u_matrix"}
        for expected_key, expected_value in expected.items():
            assert bimap.get_by_key(expected_key) == expected_value
            assert bimap.get_by_value(expected_value) == expected_key

        schema = bimap.collect_schema(get_cache)
        expected_schema = {
            "id_sample": ObservablePropertyValueType.STRING,
            "matrix": ObservablePropertyValueType.STRING,
        }
        assert len(schema) == len(bimap)
        for key, value in expected_schema.items():
            assert schema[key] == value

    def test_internal_data_layout(self, get_cache):
        layout_id = "peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA"
        layout = get_cache.get(layout_id, "DataLayoutLayout")
        internal_layout = InternalDataLayout.from_peh(data_layout=layout)
        schema = internal_layout.collect_schema(get_cache)
        assert schema is not None
        expected_schema = {
            "SAMPLE": {"id_sample": ObservablePropertyValueType.STRING, "matrix": ObservablePropertyValueType.STRING},
            "SAMPLETIMEPOINT_BS": {
                "id_sample": ObservablePropertyValueType.STRING,
                "adults_u_crt": ObservablePropertyValueType.DECIMAL,
            },
        }
        for key, subschema in expected_schema.items():
            for subkey, value in subschema.items():
                assert schema[key][subkey] == value

    def test_dataset_series(self, get_cache):
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
        assert dataset_series.described_by == "peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA"
        for dataset in dataset_series.parts.values():
            assert dataset.described_by in all_sections

        schema = dataset_series.get_type_annotations()
        expected_schema = {
            "SAMPLE": {"id_sample": ObservablePropertyValueType.STRING, "matrix": ObservablePropertyValueType.STRING},
            "SAMPLETIMEPOINT_BS": {
                "id_sample": ObservablePropertyValueType.STRING,
                "adults_u_crt": ObservablePropertyValueType.DECIMAL,
            },
        }
        for key, subschema in expected_schema.items():
            for subkey, value in subschema.items():
                assert schema[key][subkey] == value


class TestJoinConditions:
    def test_left_to_right_join(self):
        left_schema = DatasetSchema(
            elements={
                "b_id": DatasetSchemaElement(
                    label="b_id", observable_property_id="prop", data_type=ObservablePropertyValueType.STRING
                )
            },
            foreign_keys={
                "b_id": ForeignKey(
                    element_label="b_id", reference=ElementReference(dataset_label="B", element_label="id")
                )
            },
        )

        right_schema = DatasetSchema(
            elements={
                "id": DatasetSchemaElement(
                    label="id", observable_property_id="prop", data_type=ObservablePropertyValueType.STRING
                )
            }
        )

        join = left_schema.detect_join("A", right_schema, "B")
        assert join is not None
        join = join[0]
        assert isinstance(join, JoinSpec)
        assert join.left_element == "b_id"
        assert join.right_element == "id"
        assert join.right_dataset == "B"

    def test_right_to_left_join(self):
        left_schema = DatasetSchema(
            elements={
                "id": DatasetSchemaElement(
                    label="id", observable_property_id="prop", data_type=ObservablePropertyValueType.STRING
                )
            }
        )

        right_schema = DatasetSchema(
            elements={
                "a_id": DatasetSchemaElement(
                    label="a_id", observable_property_id="prop", data_type=ObservablePropertyValueType.STRING
                )
            },
            foreign_keys={
                "a_id": ForeignKey(
                    element_label="a_id", reference=ElementReference(dataset_label="A", element_label="id")
                )
            },
        )

        join = left_schema.detect_join("A", right_schema, "B")
        assert join is not None
        join = join[0]
        assert isinstance(join, JoinSpec)
        assert join.left_element == "id"
        assert join.right_element == "a_id"
        assert join.right_dataset == "B"

    def test_shared_reference_join(self):
        left_schema = DatasetSchema(
            elements={
                "c_ref": DatasetSchemaElement(
                    label="c_ref", observable_property_id="c_ref", data_type=ObservablePropertyValueType.STRING
                )
            },
            foreign_keys={
                "c_ref": ForeignKey(
                    element_label="c_ref", reference=ElementReference(dataset_label="C", element_label="id_other")
                )
            },
        )

        right_schema = DatasetSchema(
            elements={
                "c_fk": DatasetSchemaElement(
                    label="c_fk", observable_property_id="c_fk", data_type=ObservablePropertyValueType.STRING
                )
            },
            foreign_keys={
                "c_fk": ForeignKey(
                    element_label="c_fk", reference=ElementReference(dataset_label="C", element_label="id")
                )
            },
        )

        join = left_schema.detect_join("A", right_schema, "B")
        assert join is not None
        assert isinstance(join, list)
        assert join[0].left_element == "c_ref"
        assert join[0].right_element == "id_other"
        assert join[0].right_dataset == "C"
        assert join[1].left_element == "c_fk"
        assert join[1].right_element == "id"
        assert join[1].right_dataset == "C"
