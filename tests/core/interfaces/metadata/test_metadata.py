import pytest
import peh_model.peh as peh

from pypeh import Session
from pypeh.core.cache.containers import CacheContainerView
from pypeh.core.interfaces.metadata import MetadataInterface
from pypeh.core.models.constants import ObservablePropertyValueType
from pypeh.core.models.internal_data_layout import DatasetSeries
from pypeh.core.models.metadata_dto import StudyMetadataConfig

pytestmark = [pytest.mark.dataframe, pytest.mark.interface]


@pytest.fixture
def metadata_adapter() -> MetadataInterface:
    return MetadataInterface.get_default_adapter_class()()


def _populate_metadata_cache(session: Session) -> peh.DataImportConfig:
    session.cache.add(
        peh.ObservableProperty(
            id="peh:prop_id_sample",
            short_name="id_sample",
            value_type="string",
            required=True,
        )
    )
    session.cache.add(
        peh.ObservableProperty(
            id="peh:prop_chol",
            short_name="chol",
            value_type="decimal",
            unit="MicroGM-PER-L",
            observation_result_type="measurement",
            has_observable_property_type=["peh:indicator_chol"],
            grouping_id_list=["peh:group_lipids"],
        )
    )
    session.cache.add(
        peh.ObservableProperty(
            id="peh:prop_chol_lod",
            short_name="chol_lod",
            value_type="decimal",
            observation_result_type="control",
        )
    )
    session.cache.add(
        peh.ObservableProperty(
            id="peh:prop_chol_mean",
            short_name="chol_mean",
            value_type="decimal",
            observation_result_type="calculation",
        )
    )
    session.cache.add(peh.Grouping(id="peh:group_lipids", ui_label="Lipids"))
    session.cache.add(
        peh.IndicatorSubClass(
            id="peh:indicator_chol",
            ui_label="Total cholesterol",
            description="Cholesterol in all lipoproteins.",
            quantity_kind="http://qudt.org/vocab/quantitykind/Mass",
            matrix="peh:matrix_blood",
            biochementity="peh:bce_chol",
            constraints=[peh.IAdoptConstraint(constraint_id="plausible")],
        )
    )
    session.cache.add(
        peh.MatrixSubClass(
            id="peh:matrix_blood",
            ui_label="Blood",
            description="Whole blood.",
        )
    )
    session.cache.add(
        peh.BioChemEntitySubClass(
            id="peh:bce_chol",
            ui_label="Cholesterol",
            exact_matches=["CHEBI:16288"],
            aliases=["total cholesterol"],
            molweight_grampermol=386.65,
            group_labels=["sterol"],
        )
    )
    session.cache.add(
        peh.ObservationDesign(
            id="peh:od_lab",
            observable_property_specifications=[
                peh.ObservablePropertySpecification(
                    observable_property="peh:prop_id_sample"
                ),
                peh.ObservablePropertySpecification(
                    observable_property="peh:prop_chol"
                ),
                peh.ObservablePropertySpecification(
                    observable_property="peh:prop_chol_lod"
                ),
            ],
        )
    )
    session.cache.add(
        peh.ObservationDesign(
            id="peh:od_summary",
            observable_property_specifications=[
                peh.ObservablePropertySpecification(
                    observable_property="peh:prop_chol_mean",
                    calculation_design=peh.CalculationDesign(
                        calculation_name="mean_chol",
                        calculation_implementation=peh.CalculationImplementation(
                            function_name="statistics_mean",
                            function_kwargs=[
                                peh.CalculationKeywordArgument(
                                    contextual_field_reference=peh.ContextualFieldReference(
                                        dataset_label="peh:obs_lab",
                                        field_label="peh:prop_chol",
                                    )
                                )
                            ],
                            function_results=[
                                peh.CalculationResult(mapping_name="chol_mean")
                            ],
                        ),
                    ),
                ),
            ],
        )
    )
    session.cache.add(
        peh.Observation(id="peh:obs_lab", observation_design="peh:od_lab")
    )
    session.cache.add(
        peh.DerivedObservation(
            id="peh:obs_summary",
            observation_design="peh:od_summary",
            was_derived_from="peh:obs_lab",
        )
    )
    layout = peh.DataLayout(
        id="peh:layout_demo",
        ui_label="LAYOUT_DEMO",
        sections=[
            peh.DataLayoutSection(
                id="peh:section_lab",
                ui_label="LAB",
                elements=[
                    peh.DataLayoutElement(
                        label="id_sample",
                        observable_property="peh:prop_id_sample",
                    ),
                    peh.DataLayoutElement(
                        label="chol",
                        observable_property="peh:prop_chol",
                    ),
                    peh.DataLayoutElement(
                        label="chol_lod",
                        observable_property="peh:prop_chol_lod",
                    ),
                ],
            ),
        ],
    )
    session.cache.add(layout)
    import_config = peh.DataImportConfig(
        id="peh:import_demo",
        layout="peh:layout_demo",
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
    return import_config


@pytest.fixture
def metadata_workflow():
    import polars as pl

    session = Session()
    import_config = _populate_metadata_cache(session)

    series = DatasetSeries(label="DEMO_STUDY")
    dataset = series.add_empty_dataset("LAB")
    dataset.add_observation_to_index("peh:obs_lab")
    series.add_observable_property(
        observation_id="peh:obs_lab",
        observable_property_id="peh:prop_id_sample",
        data_type=ObservablePropertyValueType.STRING,
        dataset_label="LAB",
        element_label="id_sample",
        is_primary_key=True,
    )
    series.add_observable_property(
        observation_id="peh:obs_lab",
        observable_property_id="peh:prop_chol",
        data_type=ObservablePropertyValueType.FLOAT,
        dataset_label="LAB",
        element_label="chol",
    )
    series.add_observable_property(
        observation_id="peh:obs_lab",
        observable_property_id="peh:prop_chol_lod",
        data_type=ObservablePropertyValueType.FLOAT,
        dataset_label="LAB",
        element_label="chol_lod",
    )
    dataset.data = pl.DataFrame(
        {
            "id_sample": ["a", "b", "b"],
            "chol": [1.2, None, 3.4],
            "chol_lod": [0.1, 0.1, 0.1],
        }
    )
    return session, import_config, series


def _build(
    metadata_adapter,
    workflow,
    metadata_config: StudyMetadataConfig | None = None,
):
    session, import_config, series = workflow
    return metadata_adapter.build_study_metadata(
        dataset_series=series,
        data_import_config=import_config,
        metadata_config=metadata_config or StudyMetadataConfig(),
        cache_view=CacheContainerView(session.cache),
    )


def test_default_adapter_is_dataframe_adapter():
    from pypeh.adapters.metadata.dataframe_adapter import (
        DataFrameMetadataAdapter,
    )

    assert MetadataInterface.get_default_adapter_class() is (
        DataFrameMetadataAdapter
    )


class TestMetadataScope:
    def test_builds_without_study_context(
        self, metadata_adapter, metadata_workflow, caplog
    ):
        with caplog.at_level(
            "WARNING", logger="pypeh.core.interfaces.metadata"
        ):
            tree = _build(metadata_adapter, metadata_workflow)
        assert set(tree) == {"observations", "datasets", "provenance"}
        assert [obs["id"] for obs in tree["observations"]] == [
            "peh:obs_lab",
            "peh:obs_summary",
        ]
        assert not any(
            "No Study could be resolved" in record.message
            for record in caplog.records
        )


class TestCatalogue:
    def test_control_variables_excluded_by_default(
        self, metadata_adapter, metadata_workflow
    ):
        tree = _build(metadata_adapter, metadata_workflow)
        property_ids = [
            prop["id"]
            for observation in tree["observations"]
            for prop in observation["observable_properties"]
        ]
        assert "peh:prop_chol_lod" not in property_ids

    def test_control_variables_included_when_enabled(
        self, metadata_adapter, metadata_workflow
    ):
        tree = _build(
            metadata_adapter,
            metadata_workflow,
            StudyMetadataConfig(exclude_control_variables=False),
        )
        property_ids = [
            prop["id"]
            for observation in tree["observations"]
            for prop in observation["observable_properties"]
        ]
        assert "peh:prop_chol_lod" in property_ids

    def test_indicator_semantics_resolved_from_cache(
        self, metadata_adapter, metadata_workflow
    ):
        tree = _build(metadata_adapter, metadata_workflow)
        chol = next(
            prop
            for observation in tree["observations"]
            for prop in observation["observable_properties"]
            if prop["id"] == "peh:prop_chol"
        )
        semantics = chol["semantics"]
        assert semantics["indicator"]["label"] == "Total cholesterol"
        assert semantics["matrix"]["label"] == "Blood"
        assert semantics["biochem_entity"]["exact_matches"] == ["CHEBI:16288"]
        assert (
            semantics["biochem_entity"]["molecular_weight_gram_per_mol"]
            == 386.65
        )
        assert semantics["constraints"] == ["plausible"]
        assert chol["groups"] == ["Lipids"]

    def test_calculation_tree_links_source_variable(
        self, metadata_adapter, metadata_workflow
    ):
        tree = _build(metadata_adapter, metadata_workflow)
        mean = next(
            prop
            for observation in tree["observations"]
            for prop in observation["observable_properties"]
            if prop["id"] == "peh:prop_chol_mean"
        )
        assert mean["kind"] == "calculation"
        assert mean["calculation"] == {
            "name": "mean_chol",
            "function": "statistics_mean",
            "inputs": [
                {
                    "argument": None,
                    "source_observation": "peh:obs_lab",
                    "source_variable": "peh:prop_chol",
                    "source_label": "chol",
                    "value": None,
                }
            ],
            "results": ["chol_mean"],
        }

    def test_shared_property_inputs_distinguish_observations(
        self, metadata_adapter, metadata_workflow
    ):
        # two calculations on different derived observations reference
        # the same property (peh:prop_chol) under their respective
        # base observations: without source_observation the inputs
        # would not show which dataset column (obs_lab or obs_mid)
        # each one reads from. Each contextual kwarg references the
        # base observation its calculation is derived from — the
        # constraint dataops enforces when such a calculation is
        # executed ("All CalculationKeywordArguments should refer to
        # specified source observation"). The intermediate observation
        # is metadata-only test data: its design carries a bare
        # measurement specification, which dataops would reject as an
        # enrich target.
        session = metadata_workflow[0]
        session.cache.add(
            peh.ObservableProperty(
                id="peh:prop_chol_mean_fu",
                short_name="chol_mean_fu",
                value_type="decimal",
                observation_result_type="calculation",
            )
        )
        session.cache.add(
            peh.ObservationDesign(
                id="peh:od_mid",
                observable_property_specifications=[
                    peh.ObservablePropertySpecification(
                        observable_property="peh:prop_chol"
                    )
                ],
            )
        )
        session.cache.add(
            peh.ObservationDesign(
                id="peh:od_followup",
                observable_property_specifications=[
                    peh.ObservablePropertySpecification(
                        observable_property="peh:prop_chol_mean_fu",
                        calculation_design=peh.CalculationDesign(
                            calculation_name="mean_chol_fu",
                            calculation_implementation=(
                                peh.CalculationImplementation(
                                    function_name="statistics_mean",
                                    function_kwargs=[
                                        peh.CalculationKeywordArgument(
                                            contextual_field_reference=(
                                                peh.ContextualFieldReference(
                                                    dataset_label=(
                                                        "peh:obs_mid"
                                                    ),
                                                    field_label=(
                                                        "peh:prop_chol"
                                                    ),
                                                )
                                            )
                                        )
                                    ],
                                )
                            ),
                        ),
                    )
                ],
            )
        )
        session.cache.add(
            peh.DerivedObservation(
                id="peh:obs_mid",
                observation_design="peh:od_mid",
                was_derived_from="peh:obs_lab",
            )
        )
        session.cache.add(
            peh.DerivedObservation(
                id="peh:obs_followup",
                observation_design="peh:od_followup",
                was_derived_from="peh:obs_mid",
            )
        )
        tree = _build(metadata_adapter, metadata_workflow)
        inputs_by_calculation = {
            prop["id"]: prop["calculation"]["inputs"]
            for observation in tree["observations"]
            for prop in observation["observable_properties"]
            if prop["kind"] == "calculation"
        }
        shared = (
            inputs_by_calculation["peh:prop_chol_mean"]
            + inputs_by_calculation["peh:prop_chol_mean_fu"]
        )
        assert [item["source_variable"] for item in shared] == [
            "peh:prop_chol",
            "peh:prop_chol",
        ]
        assert [item["source_observation"] for item in shared] == [
            "peh:obs_lab",
            "peh:obs_mid",
        ]

    def test_derived_observation_follows_base_in_lineage(
        self, metadata_adapter, metadata_workflow
    ):
        tree = _build(metadata_adapter, metadata_workflow)
        assert [obs["id"] for obs in tree["observations"]] == [
            "peh:obs_lab",
            "peh:obs_summary",
        ]

    def test_multi_level_derivation_in_dependency_order(
        self, metadata_adapter, metadata_workflow
    ):
        # the grandchild is cached before its parent: the order must
        # follow the derivation graph, not cache or set order.
        session = metadata_workflow[0]
        session.cache.add(
            peh.DerivedObservation(
                id="peh:obs_grandchild",
                observation_design="peh:od_summary",
                was_derived_from="peh:obs_child",
            )
        )
        session.cache.add(
            peh.DerivedObservation(
                id="peh:obs_child",
                observation_design="peh:od_summary",
                was_derived_from="peh:obs_summary",
            )
        )
        tree = _build(metadata_adapter, metadata_workflow)
        assert [obs["id"] for obs in tree["observations"]] == [
            "peh:obs_lab",
            "peh:obs_summary",
            "peh:obs_child",
            "peh:obs_grandchild",
        ]

    def test_missing_observation_design_warns_and_skips(
        self, metadata_adapter, metadata_workflow, caplog
    ):
        session = metadata_workflow[0]
        session.cache.pop("peh:od_summary", "ObservationDesign")
        with caplog.at_level(
            "WARNING", logger="pypeh.core.interfaces.metadata"
        ):
            tree = _build(metadata_adapter, metadata_workflow)
        assert [obs["id"] for obs in tree["observations"]] == ["peh:obs_lab"]
        assert any(
            "peh:od_summary" in record.message for record in caplog.records
        )

    def test_multiple_indicators_warn_and_emit_first(
        self, metadata_adapter, metadata_workflow, caplog
    ):
        session = metadata_workflow[0]
        session.cache.add(
            peh.IndicatorSubClass(id="peh:indicator_other", ui_label="Other")
        )
        chol = session.cache.get("peh:prop_chol", "ObservableProperty")
        chol.has_observable_property_type = [
            "peh:indicator_chol",
            "peh:indicator_other",
        ]
        with caplog.at_level(
            "WARNING", logger="pypeh.core.interfaces.metadata"
        ):
            tree = _build(metadata_adapter, metadata_workflow)
        chol_tree = next(
            prop
            for observation in tree["observations"]
            for prop in observation["observable_properties"]
            if prop["id"] == "peh:prop_chol"
        )
        assert chol_tree["semantics"]["indicator"]["id"] == (
            "peh:indicator_chol"
        )
        assert any(
            "2 indicators" in record.message for record in caplog.records
        )


class TestDatasets:
    def test_dataset_variables_and_dtypes(
        self, metadata_adapter, metadata_workflow
    ):
        tree = _build(metadata_adapter, metadata_workflow)
        (dataset,) = tree["datasets"]
        assert dataset["label"] == "LAB"
        assert dataset["observations"] == ["peh:obs_lab"]
        labels = [variable["label"] for variable in dataset["variables"]]
        assert labels == ["id_sample", "chol"]  # chol_lod excluded
        id_sample = dataset["variables"][0]
        assert id_sample["data_type"] == "STRING"
        assert id_sample["primary_key"] is True
        assert dataset["variables"][1]["data_type"] == "FLOAT"

    def test_no_profile_even_when_data_is_loaded(
        self, metadata_adapter, metadata_workflow
    ):
        # profiling is deliberately out of scope: per-column counts can
        # de-anonymize individuals in small cohorts; profile data will
        # later be produced by the aggregation service and passed in.
        tree = _build(metadata_adapter, metadata_workflow)
        for variable in tree["datasets"][0]["variables"]:
            assert "profile" not in variable

    def test_control_excluded_even_when_design_missing(
        self, metadata_adapter, metadata_workflow, caplog
    ):
        # the dataset keeps its chol_lod column but the design that
        # specifies it is gone: the design-driven control walk never
        # sees it, so the schema-driven pass must classify it.
        session = metadata_workflow[0]
        session.cache.pop("peh:od_lab", "ObservationDesign")
        with caplog.at_level(
            "WARNING", logger="pypeh.core.interfaces.metadata"
        ):
            tree = _build(metadata_adapter, metadata_workflow)
        (dataset,) = tree["datasets"]
        labels = [variable["label"] for variable in dataset["variables"]]
        assert labels == ["id_sample", "chol"]  # chol_lod still excluded
        assert any("peh:od_lab" in record.message for record in caplog.records)
        # the observation itself stays tolerated (skipped with warning)
        assert [obs["id"] for obs in tree["observations"]] == [
            "peh:obs_summary"
        ]

        opted_out = _build(
            metadata_adapter,
            metadata_workflow,
            StudyMetadataConfig(exclude_control_variables=False),
        )
        labels = [
            variable["label"]
            for variable in opted_out["datasets"][0]["variables"]
        ]
        assert "chol_lod" in labels


class TestProvenance:
    def test_provenance_sections_and_derivation_chain(
        self, metadata_adapter, metadata_workflow
    ):
        tree = _build(metadata_adapter, metadata_workflow)
        provenance = tree["provenance"]
        assert provenance["series_label"] == "DEMO_STUDY"
        assert provenance["data_import_config"] == "peh:import_demo"
        assert provenance["data_layout"] == "peh:layout_demo"
        assert provenance["sections"] == [
            {"dataset": "LAB", "described_by": None}
        ]
        assert provenance["derived_observations"] == [
            {
                "derived_observation": "peh:obs_summary",
                "was_derived_from": "peh:obs_lab",
            }
        ]
        assert provenance["validation_report"] is None

    def test_extra_provenance_merged(
        self, metadata_adapter, metadata_workflow
    ):
        tree = _build(
            metadata_adapter,
            metadata_workflow,
            StudyMetadataConfig(extra_provenance={"source_file": "demo.xlsx"}),
        )
        assert tree["provenance"]["source_file"] == "demo.xlsx"

    def test_extra_provenance_cannot_override_builtin_fields(
        self, metadata_adapter, metadata_workflow
    ):
        with pytest.raises(ValueError, match="pypeh_version"):
            _build(
                metadata_adapter,
                metadata_workflow,
                StudyMetadataConfig(
                    extra_provenance={"pypeh_version": "spoofed"}
                ),
            )

    def test_extra_provenance_rejects_non_json_values(
        self, metadata_adapter, metadata_workflow
    ):
        from pathlib import Path

        with pytest.raises(ValueError, match="source_file"):
            _build(
                metadata_adapter,
                metadata_workflow,
                StudyMetadataConfig(
                    extra_provenance={"source_file": Path("demo.xlsx")}
                ),
            )
        with pytest.raises(ValueError, match="source_file"):
            _build(
                metadata_adapter,
                metadata_workflow,
                StudyMetadataConfig(
                    extra_provenance={"source_file": {"tries": {1, 2}}}
                ),
            )
        with pytest.raises(ValueError, match="key of type int"):
            _build(
                metadata_adapter,
                metadata_workflow,
                StudyMetadataConfig(extra_provenance={1: "spoofed"}),
            )

    def test_extra_provenance_rejects_non_finite_and_circular(
        self, metadata_adapter, metadata_workflow
    ):
        for bad_float in (float("nan"), float("inf"), float("-inf")):
            with pytest.raises(ValueError, match="source_file"):
                _build(
                    metadata_adapter,
                    metadata_workflow,
                    StudyMetadataConfig(
                        extra_provenance={"source_file": bad_float}
                    ),
                )
        cyclic_list = ["demo"]
        cyclic_list.append(cyclic_list)
        with pytest.raises(ValueError, match="source_file"):
            _build(
                metadata_adapter,
                metadata_workflow,
                StudyMetadataConfig(
                    extra_provenance={"source_file": cyclic_list}
                ),
            )
        cyclic_dict = {}
        cyclic_dict["self"] = cyclic_dict
        with pytest.raises(ValueError, match="source_file"):
            _build(
                metadata_adapter,
                metadata_workflow,
                StudyMetadataConfig(
                    extra_provenance={"source_file": cyclic_dict}
                ),
            )

    def test_shared_references_are_not_circular(
        self, metadata_adapter, metadata_workflow
    ):
        # the same list appearing twice is not a cycle and serializes
        # fine, so it must not be flagged.
        shared = ["etl", "demo"]
        tree = _build(
            metadata_adapter,
            metadata_workflow,
            StudyMetadataConfig(
                extra_provenance={"tags": shared, "origin": shared}
            ),
        )
        assert tree["provenance"]["tags"] == ["etl", "demo"]
        assert tree["provenance"]["origin"] == ["etl", "demo"]

    def test_caller_provenance_serializes_to_json(
        self, metadata_adapter, metadata_workflow
    ):
        import json

        extra = {
            "source_file": "demo.xlsx",
            "attempt": 2,
            "tags": ["etl", "demo"],
            "origin": {"tool": "pypeh", "verified": True},
        }
        tree = _build(
            metadata_adapter,
            metadata_workflow,
            StudyMetadataConfig(extra_provenance=extra),
        )
        assert {key: tree["provenance"][key] for key in extra} == extra
        assert json.loads(json.dumps(tree)) == tree

    def test_missing_distribution_version_is_none(
        self, metadata_adapter, metadata_workflow, monkeypatch
    ):
        import importlib.metadata

        def _not_installed(distribution):
            raise importlib.metadata.PackageNotFoundError(distribution)

        monkeypatch.setattr(importlib.metadata, "version", _not_installed)
        provenance = _build(metadata_adapter, metadata_workflow)["provenance"]
        assert provenance["pypeh_version"] is None
        assert provenance["peh_model_version"] is None

    def test_validation_report_attached_not_run(
        self, metadata_adapter, metadata_workflow
    ):
        session, import_config, series = metadata_workflow
        from pypeh.core.models.validation_errors import (
            ValidationErrorReport,
            ValidationErrorReportCollection,
        )

        report = ValidationErrorReportCollection(
            {
                "peh:obs_lab": ValidationErrorReport.from_runtime_error(
                    ValueError("boom")
                )
            }
        )
        tree = metadata_adapter.build_study_metadata(
            dataset_series=series,
            data_import_config=import_config,
            metadata_config=StudyMetadataConfig(),
            cache_view=CacheContainerView(session.cache),
            validation_report=report,
        )
        attached = tree["provenance"]["validation_report"]
        assert attached == {
            "peh:obs_lab": report["peh:obs_lab"].model_dump(mode="json")
        }
        assert attached["peh:obs_lab"]["error_counts"]["FATAL"] == 1


class TestSeriesConfigConsistency:
    def test_series_observation_outside_config_raises(
        self, metadata_adapter, metadata_workflow
    ):
        series = metadata_workflow[2]
        series.parts["LAB"].add_observation_to_index("peh:obs_foreign")
        with pytest.raises(ValueError, match="peh:obs_foreign"):
            _build(metadata_adapter, metadata_workflow)

    def test_derived_observation_in_series_is_accepted(
        self, metadata_adapter, metadata_workflow
    ):
        series = metadata_workflow[2]
        series.parts["LAB"].add_observation_to_index("peh:obs_summary")
        tree = _build(metadata_adapter, metadata_workflow)
        assert tree["datasets"][0]["observations"] == [
            "peh:obs_lab",
            "peh:obs_summary",
        ]


class TestSerialization:
    @staticmethod
    def _assert_builtin_only(value, path="tree"):
        if isinstance(value, dict):
            for key, item in value.items():
                assert type(key) is str, f"{path}: key {key!r}"
                TestSerialization._assert_builtin_only(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                TestSerialization._assert_builtin_only(
                    item, f"{path}[{index}]"
                )
        else:
            assert type(value) in (str, int, float, bool, type(None)), (
                f"{path}: {type(value).__name__}"
            )

    def test_tree_holds_builtin_types_only(
        self, metadata_adapter, metadata_workflow
    ):
        tree = _build(metadata_adapter, metadata_workflow)
        self._assert_builtin_only(tree)

    def test_tree_serializes_without_aliases(
        self, metadata_adapter, metadata_workflow
    ):
        import json

        import yaml

        tree = _build(metadata_adapter, metadata_workflow)
        json.dumps(tree)
        dumped = yaml.safe_dump(tree, sort_keys=False)
        assert "&id" not in dumped
        assert "*id" not in dumped
        assert yaml.safe_load(dumped) == tree

    def test_catalogue_and_datasets_share_no_objects(
        self, metadata_adapter, metadata_workflow
    ):
        tree = _build(metadata_adapter, metadata_workflow)
        catalogue_chol = next(
            prop
            for observation in tree["observations"]
            for prop in observation["observable_properties"]
            if prop["id"] == "peh:prop_chol"
        )
        dataset_chol = next(
            variable["observable_property"]
            for variable in tree["datasets"][0]["variables"]
            if variable["label"] == "chol"
        )
        assert dataset_chol == catalogue_chol
        assert dataset_chol is not catalogue_chol


class TestSectionGating:
    @pytest.mark.parametrize(
        ("flag", "expected_absent"),
        [
            ("include_variable_catalogue", ["observations"]),
            ("include_datasets", ["datasets"]),
            ("include_provenance", ["provenance"]),
        ],
    )
    def test_disabled_sections_omitted(
        self, metadata_adapter, metadata_workflow, flag, expected_absent
    ):
        tree = _build(
            metadata_adapter,
            metadata_workflow,
            StudyMetadataConfig(**{flag: False}),
        )
        for key in expected_absent:
            assert key not in tree

    def test_datasets_without_catalogue_fall_back_to_ids(
        self, metadata_adapter, metadata_workflow
    ):
        tree = _build(
            metadata_adapter,
            metadata_workflow,
            StudyMetadataConfig(include_variable_catalogue=False),
        )
        variable = tree["datasets"][0]["variables"][0]
        assert variable["observable_property"] == {"id": "peh:prop_id_sample"}
