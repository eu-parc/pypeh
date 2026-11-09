import json
import yaml
import pytest
import peh_model.peh as peh

from pypeh import LocalFileConfig, Session
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


@pytest.fixture
def local_metadata_session(tmp_path):
    return Session(
        connection_config=[
            LocalFileConfig(
                label="local_file",
                config_dict={"root_folder": str(tmp_path)},
            )
        ],
        default_connection=None,
    )


@pytest.fixture
def metadata_tree():
    return {
        "observations": [],
        "datasets": [{"label": "LAB", "described_by": None, "variables": []}],
        "provenance": {
            "pypeh_version": "0.9.1",
            "peh_model_version": "1.2.3",
            "validation_report": None,
        },
    }


@pytest.mark.core
class TestDumpStudyMetadata:
    @pytest.mark.parametrize("file_format", ["yaml", "json"])
    def test_local_roundtrip_preserves_empty_lists_and_nulls(
        self, local_metadata_session, metadata_tree, tmp_path, file_format
    ):
        output_path = f"nested/study.{file_format}"
        written = local_metadata_session.dump_study_metadata(
            metadata_tree,
            output_path,
            file_format=file_format,
            connection_label="local_file",
        )

        assert written == str(tmp_path / output_path)
        payload = (tmp_path / output_path).read_text(encoding="utf-8")
        loaded = (
            yaml.safe_load(payload)
            if file_format == "yaml"
            else json.loads(payload)
        )
        assert loaded == metadata_tree
        assert list(loaded) == list(metadata_tree)

    def test_explicit_format_is_not_inferred_from_extension(
        self, local_metadata_session, metadata_tree, tmp_path
    ):
        written = local_metadata_session.dump_study_metadata(
            metadata_tree,
            "study.yaml",
            file_format="json",
            connection_label="local_file",
        )
        assert json.loads((tmp_path / "study.yaml").read_text()) == (
            metadata_tree
        )
        assert written == str(tmp_path / "study.yaml")

    def test_missing_format_is_required(
        self, local_metadata_session, metadata_tree
    ):
        with pytest.raises(TypeError, match="file_format"):
            local_metadata_session.dump_study_metadata(
                metadata_tree, "study.yaml", connection_label="local_file"
            )

    def test_unsupported_format_does_not_write(
        self, local_metadata_session, metadata_tree, tmp_path
    ):
        with pytest.raises(NotImplementedError, match="csv"):
            local_metadata_session.dump_study_metadata(
                metadata_tree,
                "study.csv",
                file_format="csv",
                connection_label="local_file",
            )
        assert not (tmp_path / "study.csv").exists()

    @pytest.mark.parametrize(
        "invalid",
        [
            {"values": {1, 2}},
            {"values": [float("nan")]},
            {"values": [float("inf")]},
            {"values": {1: "not a string key"}},
        ],
    )
    def test_invalid_metadata_does_not_write(
        self, local_metadata_session, invalid, tmp_path
    ):
        with pytest.raises(ValueError, match="Study metadata"):
            local_metadata_session.dump_study_metadata(
                invalid,
                "study.yaml",
                file_format="yaml",
                connection_label="local_file",
            )
        assert not (tmp_path / "study.yaml").exists()

    def test_circular_metadata_does_not_write(
        self, local_metadata_session, tmp_path
    ):
        metadata = {"observations": []}
        metadata["observations"].append(metadata)
        with pytest.raises(ValueError, match="cycle"):
            local_metadata_session.dump_study_metadata(
                metadata,
                "study.json",
                file_format="json",
                connection_label="local_file",
            )
        assert not (tmp_path / "study.json").exists()

    @pytest.mark.parametrize(
        "output_path",
        [
            "",
            "   ",
            ".",
            "..",
            "nested/",
            "nested/.",
            "nested/..",
            "bad\x00name",
            None,
            12,
        ],
    )
    def test_bad_output_path_does_not_create_files_or_directories(
        self, local_metadata_session, metadata_tree, tmp_path, output_path
    ):
        with pytest.raises(ValueError, match="output_path must name a file"):
            local_metadata_session.dump_study_metadata(
                metadata_tree,
                output_path,
                file_format="json",
                connection_label="local_file",
            )
        assert list(tmp_path.iterdir()) == []

    def test_existing_directory_is_not_a_file(
        self, local_metadata_session, metadata_tree, tmp_path
    ):
        directory = tmp_path / "existing"
        directory.mkdir()
        with pytest.raises(ValueError, match="not a directory"):
            local_metadata_session.dump_study_metadata(
                metadata_tree,
                str(directory),
                file_format="yaml",
                connection_label="local_file",
            )
        assert list(directory.iterdir()) == []

    def test_parent_file_is_rejected_before_writing(
        self, local_metadata_session, metadata_tree, tmp_path
    ):
        parent = tmp_path / "already-a-file"
        parent.write_text("original", encoding="utf-8")
        with pytest.raises(ValueError, match="file as its parent"):
            local_metadata_session.dump_study_metadata(
                metadata_tree,
                "already-a-file/study.json",
                file_format="json",
                connection_label="local_file",
            )
        assert parent.read_text(encoding="utf-8") == "original"
