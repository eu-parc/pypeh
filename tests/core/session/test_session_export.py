import importlib

import pytest
import peh_model.peh as peh

from pypeh import LocalFileConfig, Session
from pypeh.adapters.persistence.serializations import ExcelIO
from pypeh.core.models.constants import ObservablePropertyValueType
from pypeh.core.models.internal_data_layout import Dataset, DatasetSeries


def _observation_group(
    observation_ids: tuple[str, ...],
) -> peh.ObservationGroup:
    return peh.ObservationGroup(
        id="peh:og_"
        + "_".join(
            observation_id.replace(":", "_")
            for observation_id in observation_ids
        ),
        observation_id_list=list(observation_ids),
    )


@pytest.fixture
def export_session(tmp_path):
    return Session(
        connection_config=[
            LocalFileConfig(
                label="local_file",
                config_dict={"root_folder": str(tmp_path)},
            )
        ],
        default_connection=None,
    )


def _build_source_dataset_series(
    sample_ids: list[str], chol_values: list[float]
) -> DatasetSeries:
    pl = importlib.import_module("polars")

    series = DatasetSeries(label="session_series")
    sample = series.add_empty_dataset("SAMPLE")
    sample.add_observation_to_index("peh:obs_sample")
    series.add_observable_property(
        observation_id="peh:obs_sample",
        observable_property_id="peh:prop_id_sample",
        data_type=ObservablePropertyValueType.STRING,
        dataset_label="SAMPLE",
        element_label="id_sample",
        is_primary_key=True,
    )
    sample.data = pl.DataFrame({"id_sample": sample_ids})

    lab = series.add_empty_dataset("LAB")
    lab.add_observation_to_index("peh:obs_lab")
    series.add_observable_property(
        observation_id="peh:obs_lab",
        observable_property_id="peh:prop_id_sample",
        data_type=ObservablePropertyValueType.STRING,
        dataset_label="LAB",
        element_label="id_sample",
    )
    series.add_observable_property(
        observation_id="peh:obs_lab",
        observable_property_id="peh:prop_chol",
        data_type=ObservablePropertyValueType.FLOAT,
        dataset_label="LAB",
        element_label="chol",
    )
    lab.schema.add_foreign_key_link(
        element_label="id_sample",
        foreign_key_dataset_label="SAMPLE",
        foreign_key_element_label="id_sample",
    )
    lab.data = pl.DataFrame({"id_sample": sample_ids, "chol": chol_values})

    return series


@pytest.fixture
def source_dataset_series():
    return _build_source_dataset_series(["sample-a", "sample-b"], [1.2, 3.4])


def _populate_export_cache(
    session: Session,
    data_filter: peh.DataFilter | None = None,
) -> peh.DataExportConfig:
    session.cache.add(
        peh.ObservableProperty(id="peh:prop_id_sample", value_type="string")
    )
    session.cache.add(
        peh.ObservableProperty(id="peh:prop_chol", value_type="float")
    )
    session.cache.add(
        peh.ObservationDesign(
            id="peh:obs_lab_design",
            observable_property_specifications=[
                peh.ObservablePropertySpecification(
                    observable_property="peh:prop_id_sample",
                    specification_category=peh.ObservablePropertySpecificationCategory.identifying,
                ),
                peh.ObservablePropertySpecification(
                    observable_property="peh:prop_chol",
                    specification_category=peh.ObservablePropertySpecificationCategory.required,
                ),
            ],
        )
    )
    session.cache.add(
        peh.Observation(
            id="peh:obs_lab",
            observation_design="peh:obs_lab_design",
        )
    )

    export_section = peh.DataLayoutSection(
        id="peh:LAB_EXPORT_SECTION",
        ui_label="LAB_EXPORT",
        elements=[
            peh.DataLayoutElement(
                label="sample_id",
                observable_property="peh:prop_id_sample",
            ),
            peh.DataLayoutElement(
                label="cholesterol_mg_dl",
                observable_property="peh:prop_chol",
            ),
        ],
        data_filter=data_filter,
    )
    session.cache.add(export_section)
    session.cache.add(
        peh.DataLayout(
            id="peh:LAB_EXPORT_LAYOUT",
            ui_label="LAB_EXPORT_LAYOUT",
            sections=[export_section],
        )
    )

    data_export_config = peh.DataExportConfig(
        id="peh:LAB_EXPORT_CONFIG",
        layout="peh:LAB_EXPORT_LAYOUT",
        section_mapping=peh.DataSectionMapping(
            section_mapping_links=[
                peh.DataSectionMappingLink(
                    section="peh:LAB_EXPORT_SECTION",
                    observation_id_list=["peh:obs_lab"],
                )
            ]
        ),
    )
    session.cache.add(data_export_config)
    return data_export_config


def _retag_lab_export(
    series: DatasetSeries,
    *,
    observation_id: str,
    sample_property_id: str,
    cholesterol_property_id: str,
):
    dataset = series.parts["LAB_EXPORT"]
    dataset.observation_ids = {observation_id}
    series._obs_index.clear()
    series._context_index.clear()

    sample_element = dataset.schema.elements["sample_id"]
    sample_element.observable_property_id = sample_property_id
    cholesterol_element = dataset.schema.elements["cholesterol_mg_dl"]
    cholesterol_element.observable_property_id = cholesterol_property_id
    dataset.schema._elements_by_observable_property = (
        dataset.schema.build_observable_property_index()
    )

    series._register_observation(observation_id, "LAB_EXPORT")
    series._register_observable_property(
        observable_property_id=sample_property_id,
        observation_id=observation_id,
        dataset_label="LAB_EXPORT",
        element_label="sample_id",
    )
    series._register_observable_property(
        observable_property_id=cholesterol_property_id,
        observation_id=observation_id,
        dataset_label="LAB_EXPORT",
        element_label="cholesterol_mg_dl",
    )


def _retag_lab_export_with_two_observations(
    series: DatasetSeries,
    *,
    first_observation_id: str,
    second_observation_id: str,
    sample_property_id: str,
    cholesterol_property_id: str,
):
    dataset = series.parts["LAB_EXPORT"]
    dataset.observation_ids = {first_observation_id, second_observation_id}
    series._obs_index.clear()
    series._context_index.clear()

    dataset.schema.elements[
        "sample_id"
    ].observable_property_id = sample_property_id
    dataset.schema.elements[
        "cholesterol_mg_dl"
    ].observable_property_id = cholesterol_property_id
    dataset.schema._elements_by_observable_property = (
        dataset.schema.build_observable_property_index()
    )

    for observation_id in (first_observation_id, second_observation_id):
        series._register_observation(observation_id, "LAB_EXPORT")
        series._register_observable_property(
            observable_property_id=sample_property_id,
            observation_id=observation_id,
            dataset_label="LAB_EXPORT",
            element_label="sample_id",
        )
        series._register_observable_property(
            observable_property_id=cholesterol_property_id,
            observation_id=observation_id,
            dataset_label="LAB_EXPORT",
            element_label="cholesterol_mg_dl",
        )


@pytest.mark.dataframe
class TestSessionExport:
    def test_export_tabular_dataset_series_returns_reshaped_series(
        self, export_session, source_dataset_series
    ):
        data_export_config = _populate_export_cache(export_session)

        exported = export_session.export_tabular_dataset_series(
            source_dataset_series=source_dataset_series,
            data_export_config=data_export_config,
        )

        assert isinstance(exported, DatasetSeries)
        assert set(exported.parts) == {"LAB_EXPORT"}
        export_dataset = exported.parts["LAB_EXPORT"]
        assert isinstance(export_dataset, Dataset)
        assert export_dataset.data is not None
        assert export_dataset.data.shape == (2, 2)
        assert set(export_dataset.data.columns) == {
            "sample_id",
            "cholesterol_mg_dl",
        }
        assert export_dataset.data.get_column("sample_id").to_list() == [
            "sample-a",
            "sample-b",
        ]
        assert export_dataset.data.get_column(
            "cholesterol_mg_dl"
        ).to_list() == [1.2, 3.4]
        assert exported.context_lookup("peh:obs_lab", "peh:prop_chol") == (
            "LAB_EXPORT",
            "cholesterol_mg_dl",
        )

    def test_export_then_dump_parquet_roundtrip(
        self, export_session, source_dataset_series
    ):
        data_export_config = _populate_export_cache(export_session)

        exported = export_session.export_tabular_dataset_series(
            source_dataset_series=source_dataset_series,
            data_export_config=data_export_config,
        )
        source_paths = export_session.dump_tabular_dataset_series(
            dataset_series=exported,
            output_path="export",
            file_format="parquet",
            connection_label="local_file",
        )

        assert len(source_paths) == 1

        loaded = export_session.read_tabular_dataset_series(
            source_paths,
            file_format="parquet",
            connection_label="local_file",
        )

        assert set(loaded.parts) == {"LAB_EXPORT"}
        lab_export = loaded["LAB_EXPORT"]
        assert isinstance(lab_export, Dataset)
        assert lab_export.data is not None
        assert lab_export.data.shape == (2, 2)
        assert set(lab_export.data.columns) == {
            "sample_id",
            "cholesterol_mg_dl",
        }
        assert loaded.context_lookup("peh:obs_lab", "peh:prop_chol") == (
            "LAB_EXPORT",
            "cholesterol_mg_dl",
        )

    def test_reading_two_exported_dataset_series_together_raises(
        self, export_session, source_dataset_series
    ):
        data_export_config = _populate_export_cache(export_session)

        first_export = export_session.export_tabular_dataset_series(
            source_dataset_series=source_dataset_series,
            data_export_config=data_export_config,
        )
        second_export = export_session.export_tabular_dataset_series(
            source_dataset_series=source_dataset_series,
            data_export_config=data_export_config,
        )

        assert first_export.label == second_export.label
        assert first_export.identifier != second_export.identifier

        first_paths = export_session.dump_tabular_dataset_series(
            dataset_series=first_export,
            output_path="first_export",
            file_format="parquet",
            connection_label="local_file",
        )
        second_paths = export_session.dump_tabular_dataset_series(
            dataset_series=second_export,
            output_path="second_export",
            file_format="parquet",
            connection_label="local_file",
        )

        with pytest.raises(
            ValueError,
            match="Parquet files do not belong to the same DatasetSeries",
        ):
            export_session.read_tabular_dataset_series(
                [*first_paths, *second_paths],
                file_format="parquet",
                connection_label="local_file",
            )

    def test_concatenate_exported_dataset_series(
        self, export_session, source_dataset_series
    ):
        data_export_config = _populate_export_cache(export_session)

        first_export = export_session.export_tabular_dataset_series(
            source_dataset_series=source_dataset_series,
            data_export_config=data_export_config,
        )
        second_export = export_session.export_tabular_dataset_series(
            source_dataset_series=source_dataset_series,
            data_export_config=data_export_config,
        )

        concatenated = export_session.concatenate_tabular_dataset_series(
            [first_export, second_export],
            output_label="combined_lab_export",
        )

        assert concatenated.label == "combined_lab_export"
        assert set(concatenated.parts) == {"LAB_EXPORT"}
        combined_dataset = concatenated.parts["LAB_EXPORT"]
        assert combined_dataset.data is not None
        assert combined_dataset.data.shape == (4, 2)
        assert combined_dataset.data.columns == [
            "sample_id",
            "cholesterol_mg_dl",
        ]
        assert combined_dataset.data.get_column("sample_id").to_list() == [
            "sample-a",
            "sample-b",
            "sample-a",
            "sample-b",
        ]
        assert combined_dataset.data.get_column(
            "cholesterol_mg_dl"
        ).to_list() == [1.2, 3.4, 1.2, 3.4]
        assert concatenated.context_lookup("peh:obs_lab", "peh:prop_chol") == (
            "LAB_EXPORT",
            "cholesterol_mg_dl",
        )

    def test_concatenate_aligns_by_observable_property_id(
        self, export_session, source_dataset_series
    ):
        data_export_config = _populate_export_cache(export_session)

        first_export = export_session.export_tabular_dataset_series(
            source_dataset_series=source_dataset_series,
            data_export_config=data_export_config,
        )
        second_export = export_session.export_tabular_dataset_series(
            source_dataset_series=source_dataset_series,
            data_export_config=data_export_config,
        )
        second_dataset = second_export.parts["LAB_EXPORT"]
        second_dataset.data = second_dataset.data.rename(
            {"cholesterol_mg_dl": "chol_value"}
        )
        chol_element = second_dataset.schema.elements.pop("cholesterol_mg_dl")
        chol_element.label = "chol_value"
        second_dataset.schema.elements["chol_value"] = chol_element
        second_dataset.schema._elements_by_observable_property[
            "peh:prop_chol"
        ] = {"chol_value"}
        second_export._context_index[("peh:obs_lab", "peh:prop_chol")] = (
            "LAB_EXPORT",
            "chol_value",
        )

        concatenated = export_session.concatenate_tabular_dataset_series(
            [first_export, second_export]
        )

        combined_dataset = concatenated.parts["LAB_EXPORT"]
        assert combined_dataset.data is not None
        assert combined_dataset.data.columns == [
            "sample_id",
            "cholesterol_mg_dl",
        ]
        assert combined_dataset.data.get_column(
            "cholesterol_mg_dl"
        ).to_list() == [1.2, 3.4, 1.2, 3.4]

    def test_concatenate_uses_semantic_alignment(
        self, export_session, source_dataset_series
    ):
        data_export_config = _populate_export_cache(export_session)

        first_export = export_session.export_tabular_dataset_series(
            source_dataset_series=source_dataset_series,
            data_export_config=data_export_config,
        )
        second_export = export_session.export_tabular_dataset_series(
            source_dataset_series=source_dataset_series,
            data_export_config=data_export_config,
        )
        _retag_lab_export(
            second_export,
            observation_id="study_b:obs_lab",
            sample_property_id="study_b:sample_id",
            cholesterol_property_id="study_b:total_cholesterol",
        )

        observation_groups = (
            _observation_group(("peh:obs_lab",)),
            _observation_group(("study_b:obs_lab",)),
        )
        # register the ObservationGroups in the session cache, like any other
        # peh resource; `concatenate_tabular_dataset_series` resolves them by
        # id from `alignment_plan.observation_assemblies[].source_observation_groups`
        for observation_group in observation_groups:
            export_session.cache.add(observation_group)

        alignment_plan = peh.ObservationAlignment(
            id="peh:alignment_lab_export",
            observation_assemblies=[
                peh.ObservationAssembly(
                    target_observation_id="peh:obs_lab",
                    source_observation_groups=[
                        observation_group.id
                        for observation_group in observation_groups
                    ],
                    observable_property_mappings=[
                        peh.ObservablePropertyMapping(
                            target_observable_property_id=(
                                "peh:prop_id_sample"
                            ),
                            source_observable_property_ids=[
                                "peh:prop_id_sample",
                                "study_b:sample_id",
                            ],
                        ),
                        peh.ObservablePropertyMapping(
                            target_observable_property_id="peh:prop_chol",
                            source_observable_property_ids=[
                                "peh:prop_chol",
                                "study_b:total_cholesterol",
                            ],
                        ),
                    ],
                ),
            ],
        )

        concatenated = export_session.concatenate_tabular_dataset_series(
            [first_export, second_export],
            alignment_plan=alignment_plan,
            output_label="aligned_lab_export",
        )

        assert concatenated.label == "aligned_lab_export"
        combined_dataset = concatenated.parts["LAB_EXPORT"]
        assert combined_dataset.data is not None
        assert combined_dataset.data.shape == (4, 2)
        assert combined_dataset.data.columns == [
            "sample_id",
            "cholesterol_mg_dl",
        ]
        assert combined_dataset.observation_ids == {"peh:obs_lab"}
        assert concatenated.context_lookup("peh:obs_lab", "peh:prop_chol") == (
            "LAB_EXPORT",
            "cholesterol_mg_dl",
        )
        assert (
            combined_dataset.schema.elements[
                "cholesterol_mg_dl"
            ].observable_property_id
            == "peh:prop_chol"
        )

    def test_concatenate_alignment_allows_multiple_target_observations(
        self, export_session, source_dataset_series
    ):
        data_export_config = _populate_export_cache(export_session)

        first_export = export_session.export_tabular_dataset_series(
            source_dataset_series=source_dataset_series,
            data_export_config=data_export_config,
        )
        second_export = export_session.export_tabular_dataset_series(
            source_dataset_series=source_dataset_series,
            data_export_config=data_export_config,
        )
        _retag_lab_export_with_two_observations(
            first_export,
            first_observation_id="study_a:baseline_lab",
            second_observation_id="study_a:followup_lab",
            sample_property_id="study_a:sample_id",
            cholesterol_property_id="study_a:chol",
        )
        _retag_lab_export_with_two_observations(
            second_export,
            first_observation_id="study_b:t0_lab",
            second_observation_id="study_b:t1_lab",
            sample_property_id="study_b:sample_id",
            cholesterol_property_id="study_b:total_cholesterol",
        )

        baseline_groups = (
            _observation_group(("study_a:baseline_lab",)),
            _observation_group(("study_b:t0_lab",)),
        )
        followup_groups = (
            _observation_group(("study_a:followup_lab",)),
            _observation_group(("study_b:t1_lab",)),
        )
        observation_groups = (*baseline_groups, *followup_groups)
        for observation_group in observation_groups:
            export_session.cache.add(observation_group)
        alignment_plan = peh.ObservationAlignment(
            id="peh:alignment_longitudinal_lab",
            observation_assemblies=[
                peh.ObservationAssembly(
                    target_observation_id="peh:obs_lab_baseline",
                    source_observation_groups=[
                        observation_group.id
                        for observation_group in baseline_groups
                    ],
                    observable_property_mappings=[
                        peh.ObservablePropertyMapping(
                            target_observable_property_id=(
                                "peh:prop_id_sample"
                            ),
                            source_observable_property_ids=[
                                "study_a:sample_id",
                                "study_b:sample_id",
                            ],
                        ),
                        peh.ObservablePropertyMapping(
                            target_observable_property_id="peh:prop_chol",
                            source_observable_property_ids=[
                                "study_a:chol",
                                "study_b:total_cholesterol",
                            ],
                        ),
                    ],
                ),
                peh.ObservationAssembly(
                    target_observation_id="peh:obs_lab_followup",
                    source_observation_groups=[
                        observation_group.id
                        for observation_group in followup_groups
                    ],
                    observable_property_mappings=[
                        peh.ObservablePropertyMapping(
                            target_observable_property_id=(
                                "peh:prop_id_sample"
                            ),
                            source_observable_property_ids=[
                                "study_a:sample_id",
                                "study_b:sample_id",
                            ],
                        ),
                        peh.ObservablePropertyMapping(
                            target_observable_property_id="peh:prop_chol",
                            source_observable_property_ids=[
                                "study_a:chol",
                                "study_b:total_cholesterol",
                            ],
                        ),
                    ],
                ),
            ],
        )

        concatenated = export_session.concatenate_tabular_dataset_series(
            [first_export, second_export],
            alignment_plan=alignment_plan,
            output_label="aligned_longitudinal_lab",
        )

        combined_dataset = concatenated.parts["LAB_EXPORT"]
        assert concatenated.label == "aligned_longitudinal_lab"
        assert combined_dataset.data is not None
        assert combined_dataset.data.shape == (4, 2)
        assert combined_dataset.observation_ids == {
            "peh:obs_lab_baseline",
            "peh:obs_lab_followup",
        }
        assert concatenated.context_lookup(
            "peh:obs_lab_baseline", "peh:prop_chol"
        ) == ("LAB_EXPORT", "cholesterol_mg_dl")
        assert concatenated.context_lookup(
            "peh:obs_lab_followup", "peh:prop_chol"
        ) == ("LAB_EXPORT", "cholesterol_mg_dl")

    def test_concatenate_alignment_allows_contributing_observations(
        self, export_session, source_dataset_series
    ):
        data_export_config = _populate_export_cache(export_session)

        first_export = export_session.export_tabular_dataset_series(
            source_dataset_series=source_dataset_series,
            data_export_config=data_export_config,
        )
        second_export = export_session.export_tabular_dataset_series(
            source_dataset_series=source_dataset_series,
            data_export_config=data_export_config,
        )
        first_dataset = first_export.parts["LAB_EXPORT"]
        first_dataset.observation_ids = {"study_a:sample", "study_a:lab"}
        first_export._obs_index.clear()
        first_export._context_index.clear()
        for observation_id in ("study_a:sample", "study_a:lab"):
            first_export._register_observation(observation_id, "LAB_EXPORT")
            first_export._register_observable_property(
                observable_property_id="study_a:sample_id",
                observation_id=observation_id,
                dataset_label="LAB_EXPORT",
                element_label="sample_id",
            )
        first_export._register_observable_property(
            observable_property_id="study_a:chol",
            observation_id="study_a:lab",
            dataset_label="LAB_EXPORT",
            element_label="cholesterol_mg_dl",
        )
        first_dataset.schema.elements[
            "sample_id"
        ].observable_property_id = "study_a:sample_id"
        first_dataset.schema.elements[
            "cholesterol_mg_dl"
        ].observable_property_id = "study_a:chol"
        first_dataset.schema._elements_by_observable_property = (
            first_dataset.schema.build_observable_property_index()
        )

        _retag_lab_export(
            second_export,
            observation_id="study_b:subject",
            sample_property_id="study_b:subject_id",
            cholesterol_property_id="study_b:total_cholesterol",
        )

        observation_groups = (
            _observation_group(("study_a:sample", "study_a:lab")),
            _observation_group(("study_b:subject",)),
        )
        for observation_group in observation_groups:
            export_session.cache.add(observation_group)
        alignment_plan = peh.ObservationAlignment(
            id="peh:alignment_contributed_lab",
            observation_assemblies=[
                peh.ObservationAssembly(
                    target_observation_id="peh:obs_lab",
                    source_observation_groups=[
                        observation_group.id
                        for observation_group in observation_groups
                    ],
                    observable_property_mappings=[
                        peh.ObservablePropertyMapping(
                            target_observable_property_id=(
                                "peh:prop_id_sample"
                            ),
                            source_observable_property_ids=[
                                "study_a:sample_id",
                                "study_b:subject_id",
                            ],
                        ),
                        peh.ObservablePropertyMapping(
                            target_observable_property_id="peh:prop_chol",
                            source_observable_property_ids=[
                                "study_a:chol",
                                "study_b:total_cholesterol",
                            ],
                        ),
                    ],
                ),
            ],
        )

        concatenated = export_session.concatenate_tabular_dataset_series(
            [first_export, second_export],
            alignment_plan=alignment_plan,
            output_label="contributed_lab_export",
        )

        combined_dataset = concatenated.parts["LAB_EXPORT"]
        assert concatenated.label == "contributed_lab_export"
        assert combined_dataset.observation_ids == {"peh:obs_lab"}
        assert combined_dataset.data is not None
        assert combined_dataset.data.shape == (4, 2)
        assert combined_dataset.data.columns == [
            "sample_id",
            "cholesterol_mg_dl",
        ]
        assert concatenated.context_lookup("peh:obs_lab", "peh:prop_chol") == (
            "LAB_EXPORT",
            "cholesterol_mg_dl",
        )

    def test_concatenate_alignment_infers_shared_properties(
        self, export_session, source_dataset_series
    ):
        data_export_config = _populate_export_cache(export_session)

        first_export = export_session.export_tabular_dataset_series(
            source_dataset_series=source_dataset_series,
            data_export_config=data_export_config,
        )
        second_export = export_session.export_tabular_dataset_series(
            source_dataset_series=source_dataset_series,
            data_export_config=data_export_config,
        )
        first_dataset = first_export.parts["LAB_EXPORT"]
        first_dataset.observation_ids = {"peh:obs_sample", "peh:obs_lab"}
        first_export._obs_index.clear()
        first_export._context_index.clear()
        for observation_id in ("peh:obs_sample", "peh:obs_lab"):
            first_export._register_observation(observation_id, "LAB_EXPORT")
            first_export._register_observable_property(
                observable_property_id="peh:prop_id_sample",
                observation_id=observation_id,
                dataset_label="LAB_EXPORT",
                element_label="sample_id",
            )
        first_export._register_observable_property(
            observable_property_id="peh:prop_chol",
            observation_id="peh:obs_lab",
            dataset_label="LAB_EXPORT",
            element_label="cholesterol_mg_dl",
        )

        observation_groups = (
            _observation_group(("peh:obs_sample", "peh:obs_lab")),
            _observation_group(("peh:obs_lab",)),
        )
        for observation_group in observation_groups:
            export_session.cache.add(observation_group)
        alignment_plan = peh.ObservationAlignment(
            id="peh:alignment_inferred_lab",
            observation_assemblies=[
                peh.ObservationAssembly(
                    target_observation_id="peh:obs_lab",
                    source_observation_groups=[
                        observation_group.id
                        for observation_group in observation_groups
                    ],
                    observable_property_mappings=[],
                ),
            ],
        )

        concatenated = export_session.concatenate_tabular_dataset_series(
            [first_export, second_export],
            alignment_plan=alignment_plan,
            output_label="inferred_lab_export",
        )

        combined_dataset = concatenated.parts["LAB_EXPORT"]
        assert concatenated.label == "inferred_lab_export"
        assert combined_dataset.data is not None
        assert combined_dataset.data.columns == [
            "sample_id",
            "cholesterol_mg_dl",
        ]
        assert concatenated.context_lookup("peh:obs_lab", "peh:prop_chol") == (
            "LAB_EXPORT",
            "cholesterol_mg_dl",
        )

    def test_concatenate_rejects_mismatched_observable_properties(
        self, export_session, source_dataset_series
    ):
        data_export_config = _populate_export_cache(export_session)

        first_export = export_session.export_tabular_dataset_series(
            source_dataset_series=source_dataset_series,
            data_export_config=data_export_config,
        )
        second_export = export_session.export_tabular_dataset_series(
            source_dataset_series=source_dataset_series,
            data_export_config=data_export_config,
        )
        second_dataset = second_export.parts["LAB_EXPORT"]
        second_dataset.schema.elements.pop("cholesterol_mg_dl")
        second_dataset.schema._elements_by_observable_property.pop(
            "peh:prop_chol"
        )
        second_dataset.data = second_dataset.data.drop("cholesterol_mg_dl")

        with pytest.raises(
            ValueError,
            match="identical observable property ids",
        ):
            export_session.concatenate_tabular_dataset_series(
                [first_export, second_export]
            )


@pytest.mark.dataframe
class TestSessionCreateTabularExtract:
    @staticmethod
    def _cholesterol_filter() -> peh.DataFilter:
        return peh.DataFilter(
            filter_expression=peh.FilterExpression(
                filter_command="is_greater_than_or_equal_to",
                filter_subject_contextual_field_references=[
                    peh.ContextualFieldReference(
                        field_label="cholesterol_mg_dl",
                        dataset_label="LAB_EXPORT",
                    )
                ],
                filter_arg_values=[2.0],
            )
        )

    def test_single_source_skips_concatenation(
        self, export_session, source_dataset_series
    ):
        data_export_config = _populate_export_cache(
            export_session, data_filter=self._cholesterol_filter()
        )

        extract = export_session.create_tabular_extract(
            [source_dataset_series],
            data_export_config,
        )

        assert isinstance(extract, DatasetSeries)
        # a single source is returned as-is (no "..._concatenated" label
        # suffix), proving `concatenate_tabular_dataset_series` was skipped
        assert extract.label == "LAB_EXPORT_LAYOUT"
        result_dataset = extract.parts["LAB_EXPORT"]
        assert result_dataset.data.get_column("sample_id").to_list() == [
            "sample-b"
        ]
        assert result_dataset.data.get_column(
            "cholesterol_mg_dl"
        ).to_list() == [3.4]

    def test_single_source_applies_output_label(
        self, export_session, source_dataset_series
    ):
        data_export_config = _populate_export_cache(export_session)

        extract = export_session.create_tabular_extract(
            [source_dataset_series],
            data_export_config,
            output_label="my_extract",
        )

        assert extract.label == "my_extract"

    def test_multiple_sources_are_filtered_before_concatenating(
        self, export_session
    ):
        data_export_config = _populate_export_cache(
            export_session, data_filter=self._cholesterol_filter()
        )
        first_source = _build_source_dataset_series(
            ["sample-a", "sample-b"], [1.2, 3.4]
        )
        second_source = _build_source_dataset_series(
            ["sample-c", "sample-d"], [0.5, 6.0]
        )

        extract = export_session.create_tabular_extract(
            [first_source, second_source],
            data_export_config,
            output_label="combined_filtered_extract",
        )

        assert extract.label == "combined_filtered_extract"
        result_dataset = extract.parts["LAB_EXPORT"]
        # each source is filtered independently (dropping sample-a and
        # sample-c) before the two single-row extracts are concatenated
        assert result_dataset.data.get_column("sample_id").to_list() == [
            "sample-b",
            "sample-d",
        ]
        assert result_dataset.data.get_column(
            "cholesterol_mg_dl"
        ).to_list() == [3.4, 6.0]

    def test_without_data_filter_behaves_like_plain_export_and_concatenate(
        self, export_session
    ):
        data_export_config = _populate_export_cache(export_session)
        first_source = _build_source_dataset_series(
            ["sample-a", "sample-b"], [1.2, 3.4]
        )
        second_source = _build_source_dataset_series(
            ["sample-c", "sample-d"], [0.5, 6.0]
        )

        extract = export_session.create_tabular_extract(
            [first_source, second_source],
            data_export_config,
        )

        result_dataset = extract.parts["LAB_EXPORT"]
        assert result_dataset.data.get_column("sample_id").to_list() == [
            "sample-a",
            "sample-b",
            "sample-c",
            "sample-d",
        ]
        assert result_dataset.data.get_column(
            "cholesterol_mg_dl"
        ).to_list() == [1.2, 3.4, 0.5, 6.0]

    def test_multiple_sources_preserve_described_by_provenance(
        self, export_session
    ):
        data_export_config = _populate_export_cache(export_session)
        first_source = _build_source_dataset_series(
            ["sample-a", "sample-b"], [1.2, 3.4]
        )
        second_source = _build_source_dataset_series(
            ["sample-c", "sample-d"], [0.5, 6.0]
        )

        extract = export_session.create_tabular_extract(
            [first_source, second_source],
            data_export_config,
        )

        # `concatenate_dataset_series` builds a brand new DatasetSeries/Dataset
        # that would otherwise drop the `described_by` provenance carried by
        # each per-source reshaped extract - verify it survives concatenation
        # so validation config lookups can still resolve the DataLayoutSection.
        assert extract.described_by == "peh:LAB_EXPORT_LAYOUT"
        assert (
            extract.parts["LAB_EXPORT"].described_by
            == "peh:LAB_EXPORT_SECTION"
        )


@pytest.mark.xlsx
class TestSessionExportXlsx:
    def test_export_then_dump_xlsx(
        self, export_session, source_dataset_series
    ):
        importlib.import_module("xlsxwriter")

        data_export_config = _populate_export_cache(export_session)

        exported = export_session.export_tabular_dataset_series(
            source_dataset_series=source_dataset_series,
            data_export_config=data_export_config,
        )
        source_paths = export_session.dump_tabular_dataset_series(
            dataset_series=exported,
            output_path="export.xlsx",
            file_format="xlsx",
            connection_label="local_file",
        )

        assert len(source_paths) == 1
        workbook = ExcelIO().load(source_paths[0])
        assert set(workbook) == {"LAB_EXPORT"}
        export_sheet = workbook["LAB_EXPORT"]
        assert export_sheet.shape == (2, 2)
        assert set(export_sheet.columns) == {
            "sample_id",
            "cholesterol_mg_dl",
        }
        assert export_sheet.get_column("sample_id").to_list() == [
            "sample-a",
            "sample-b",
        ]
        assert export_sheet.get_column("cholesterol_mg_dl").to_list() == [
            1.2,
            3.4,
        ]
