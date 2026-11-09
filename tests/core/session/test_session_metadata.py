import pytest
import peh_model.peh as peh

from pypeh import Session
from pypeh.core.models.metadata_dto import StudyMetadataConfig


@pytest.fixture
def session_with_demo_workflow():
    """
    Minimal in-cache workflow with one observation, without study-level
    resources, to exercise the Session facade without dataframe I/O.
    """
    session = Session()
    session.cache.add(
        peh.ObservableProperty(id="peh:prop_id_sample", short_name="id_sample")
    )
    session.cache.add(
        peh.ObservationDesign(
            id="peh:od_lab",
            observable_property_specifications=[
                peh.ObservablePropertySpecification(
                    observable_property="peh:prop_id_sample"
                )
            ],
        )
    )
    session.cache.add(
        peh.Observation(id="peh:obs_lab", observation_design="peh:od_lab")
    )
    session.cache.add(
        peh.DataLayout(
            id="peh:layout",
            ui_label="LAYOUT",
            sections=[
                peh.DataLayoutSection(
                    id="peh:section_lab",
                    ui_label="LAB",
                    elements=[
                        peh.DataLayoutElement(
                            label="id_sample",
                            observable_property="peh:prop_id_sample",
                        )
                    ],
                )
            ],
        )
    )
    import_config = peh.DataImportConfig(
        id="peh:import",
        layout="peh:layout",
        section_mapping=peh.DataSectionMapping(
            section_mapping_links=[
                peh.DataSectionMappingLink(
                    section="peh:section_lab",
                    observation_id_list=["peh:obs_lab"],
                )
            ]
        ),
    )
    session.cache.add(import_config)

    from pypeh.core.models.constants import ObservablePropertyValueType
    from pypeh.core.models.internal_data_layout import DatasetSeries

    series = DatasetSeries(label="DEMO_STUDY")
    dataset = series.add_empty_dataset("LAB")
    dataset.add_observation_to_index("peh:obs_lab")
    series.add_observable_property(
        observation_id="peh:obs_lab",
        observable_property_id="peh:prop_id_sample",
        data_type=ObservablePropertyValueType.STRING,
        dataset_label="LAB",
        element_label="id_sample",
    )
    return session, import_config, series


@pytest.mark.session
class TestCreateStudyMetadata:
    def test_uses_registered_metadata_adapter(
        self, session_with_demo_workflow
    ):
        from pypeh.core.interfaces.metadata import MetadataInterface

        session, import_config, series = session_with_demo_workflow

        class RecordingAdapter(MetadataInterface):
            def __init__(self):
                self.called = False

            def build_study_metadata(self, **kwargs):
                self.called = True
                self.kwargs = kwargs
                return {"observations": []}

        adapter = RecordingAdapter()
        session.register_adapter("metadata", adapter)
        result = session.create_study_metadata(
            dataset_series=series,
            data_import_config=import_config,
        )
        assert adapter.called
        assert result == {"observations": []}

    def test_non_metadata_adapter_raises(self, session_with_demo_workflow):
        session, import_config, series = session_with_demo_workflow
        session.register_adapter("metadata", object())
        with pytest.raises(AssertionError):
            session.create_study_metadata(
                dataset_series=series,
                data_import_config=import_config,
            )


@pytest.mark.dataframe
class TestCreateStudyMetadataWithDataAdapter:
    def test_default_config_produces_full_tree(
        self, session_with_demo_workflow
    ):
        session, import_config, series = session_with_demo_workflow
        tree = session.create_study_metadata(
            dataset_series=series,
            data_import_config=import_config,
        )
        assert set(tree) == {
            "observations",
            "datasets",
            "provenance",
        }
        assert tree["observations"][0]["id"] == "peh:obs_lab"
        assert tree["provenance"]["data_import_config"] == "peh:import"

    def test_metadata_config_forwarded(self, session_with_demo_workflow):
        session, import_config, series = session_with_demo_workflow
        tree = session.create_study_metadata(
            dataset_series=series,
            data_import_config=import_config,
            metadata_config=StudyMetadataConfig(include_provenance=False),
        )
        assert set(tree) == {"observations", "datasets"}
