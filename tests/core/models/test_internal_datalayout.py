import pytest
import peh_model.peh as peh

from pypeh.core.cache.containers import CacheContainer, CacheContainerFactory, CacheContainerView
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
from pypeh.adapters.outbound.persistence.hosts import DirectoryIO
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
        contextual_field_reference = expression.validation_subject_contextual_field_references[0]
        assert contextual_field_reference.dataset_label == "SAMPLETIMEPOINT_BS"
        assert contextual_field_reference.field_label == "adults_u_crt"


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


class TestToTarget:
    @pytest.fixture(scope="class")
    def dataset_series_input(self) -> tuple[DatasetSeries, DatasetSchema]:
        # Schema for urine_lab
        partial_urine_lab_schema = DatasetSchema(
            elements={
                "id_subject": DatasetSchemaElement(
                    label="id_subject",
                    observable_property_id="id_subject",
                    data_type=ObservablePropertyValueType.STRING,
                ),
                "matrix": DatasetSchemaElement(
                    label="matrix",
                    observable_property_id="matrix",
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
                    observable_property_id="id_subject",
                    data_type=ObservablePropertyValueType.STRING,
                ),
                "matrix": DatasetSchemaElement(
                    label="matrix",
                    observable_property_id="matrix",
                    data_type=ObservablePropertyValueType.STRING,
                ),
                "crt": DatasetSchemaElement(
                    label="crt",
                    observable_property_id="crt",
                    data_type=ObservablePropertyValueType.FLOAT,
                ),
                "crt_lod": DatasetSchemaElement(
                    label="crt_lod",
                    observable_property_id="crt_lod",
                    data_type=ObservablePropertyValueType.FLOAT,
                ),
                "crt_loq": DatasetSchemaElement(
                    label="crt_loq",
                    observable_property_id="crt_loq",
                    data_type=ObservablePropertyValueType.FLOAT,
                ),
                "sg": DatasetSchemaElement(
                    label="sg",
                    observable_property_id="sg",
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
                    observable_property_id="id_subject",
                    data_type=ObservablePropertyValueType.STRING,
                ),
                "biomarkercode": DatasetSchemaElement(
                    label="biomarkercode",
                    observable_property_id="biomarkercode",
                    data_type=ObservablePropertyValueType.STRING,
                ),
                "matrix": DatasetSchemaElement(
                    label="matrix",
                    observable_property_id="matrix",
                    data_type=ObservablePropertyValueType.STRING,
                ),
                "labinstitution": DatasetSchemaElement(
                    label="labinstitution",
                    observable_property_id="labinstitution",
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
            observations=set(["peh:urine_lab_this"]),
        )

        # urine_lab_dataset = Dataset(
        #     label="urine_lab",
        #     schema=urine_lab_schema,
        #     data=None,
        #     observations=set(["peh:urine_lab_this", "peh:urine_lab_other"]),
        # )

        analyticalinfo_dataset = Dataset(
            label="analyticalinfo",
            schema=analyticalinfo_schema,
            data=None,
            observations=set(["peh:analyticalinfo_obs"]),
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
        series.build_observation_index()

        return series, urine_lab_schema

    @pytest.fixture(scope="class")
    def cache_view(self) -> CacheContainerView:
        obs = [
            peh.Observation(
                id="peh:urine_lab_other",
                ui_label="urine_lab_other",
                observation_design=peh.ObservationDesign(
                    identifying_observable_property_id_list=["id_subject"],
                    required_observable_property_id_list=["crt", "crt_lod", "crt_loq", "sg"],
                ),
            ),
        ]
        observable_properties = [
            peh.ObservableProperty(
                id="id_subject",
                ui_label="id_subject",
                value_type="float",
            ),
            peh.ObservableProperty(
                id="crt",
                ui_label="crt",
                value_type="float",
            ),
            peh.ObservableProperty(
                id="crt_lod",
                ui_label="crt_lod",
                value_type="float",
            ),
            peh.ObservableProperty(
                id="crt_loq",
                ui_label="crt_loq",
                value_type="float",
            ),
            peh.ObservableProperty(
                id="sg",
                ui_label="sg",
                value_type="float",
            ),
        ]

        container = CacheContainerFactory.new()
        for entity_list in (obs, observable_properties):
            for entity in entity_list:
                container.add(entity)
        return CacheContainerView(container)

    def test_add_observation(self, dataset_series_input, cache_view):
        obs = cache_view.get("peh:urine_lab_other", "Observation")
        assert isinstance(obs, peh.Observation)
        source_dataset_series, expected_schema = dataset_series_input
        assert isinstance(source_dataset_series, DatasetSeries)
        source_dataset_series.add_observation(
            dataset_label="partial_urine_lab",
            observation=obs,
            cache_view=cache_view,
        )

        assert source_dataset_series["partial_urine_lab"].schema == expected_schema
