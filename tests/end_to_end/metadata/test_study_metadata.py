import json

from pathlib import Path

import peh_model.peh as peh
import pytest

from pypeh import LocalFileConfig, Session


pytestmark = [pytest.mark.end_to_end, pytest.mark.dataframe]

# Reuse the metadata integration fixture's persisted PEH config and workbook.
INPUT_DIR = Path(__file__).resolve().parents[2] / "integration/metadata/input"


def test_aggregation_result_has_dataset_and_calculation_metadata():
    session = Session(
        connection_config=[
            LocalFileConfig(
                label="local_file",
                config_dict={"root_folder": str(INPUT_DIR)},
            )
        ]
    )
    session.load_persisted_cache(
        "peh_demo.yaml", connection_label="local_file"
    )
    import_config = session.cache.require(
        "peh:IMPORT_DEMO", "DataImportConfig"
    )
    source_observation = session.cache.require(
        "peh:OBS_LAB_ASSAYS", "Observation"
    )
    assert isinstance(import_config, peh.DataImportConfig)
    assert isinstance(source_observation, peh.Observation)

    # Aggregate directly from a configured base observation so the test
    # needs no enrichment plugin or Study/Project context.
    session.cache.add(
        peh.ObservationDesign(
            id="peh:OD_LAB_MEAN",
            observable_property_specifications=[
                peh.ObservablePropertySpecification(
                    observable_property="chol_mean",
                    specification_category="derived",
                    calculation_design=peh.CalculationDesign(
                        calculation_name="mean_lab_cholesterol",
                        calculation_implementation=(
                            peh.CalculationImplementation(
                                function_name=(
                                    "pypeh.adapters.aggregation.polars_adapter."
                                    "statistics.statistics_mean"
                                ),
                                function_kwargs=[
                                    peh.CalculationKeywordArgument(
                                        contextual_field_reference=(
                                            peh.ContextualFieldReference(
                                                dataset_label=(
                                                    "peh:OBS_LAB_ASSAYS"
                                                ),
                                                field_label="chol",
                                            )
                                        )
                                    )
                                ],
                                function_results=[
                                    peh.CalculationResult(
                                        mapping_name="chol_mean"
                                    )
                                ],
                            )
                        ),
                    ),
                )
            ],
        )
    )
    target = peh.DerivedObservation(
        id="peh:OBS_LAB_MEAN",
        ui_label="LAB_MEAN",
        observation_design="peh:OD_LAB_MEAN",
        was_derived_from=source_observation.id,
    )
    session.cache.add(target)

    imported = session.import_tabular_dataset_series(
        source="peh_demo_data.xlsx",
        data_import_config=import_config,
        file_format="xlsx",
        connection_label="local_file",
        cast_error_policy="null",
    )
    lab = imported.parts["LAB_ASSAYS"]
    assert lab.data is not None

    aggregated = session.aggregate(
        source_dataset_series=imported,
        target_observations=[target],
        target_derived_from=[source_observation],
    )
    summary = aggregated.parts["LAB_MEAN"]
    assert summary.data is not None
    assert summary.data["chol_mean"].to_list() == pytest.approx(
        [lab.data["chol"].mean()]
    )

    tree = session.create_study_metadata(
        dataset_series=aggregated,
        data_import_config=import_config,
    )
    assert set(tree) == {"observations", "datasets", "provenance"}
    (dataset,) = tree["datasets"]
    assert dataset["label"] == "LAB_MEAN"
    assert dataset["observations"] == [target.id]
    (variable,) = dataset["variables"]
    assert variable["label"] == "chol_mean"
    assert variable["data_type"] == "FLOAT"

    observation = next(
        obs for obs in tree["observations"] if obs["id"] == target.id
    )
    (property_metadata,) = observation["observable_properties"]
    assert property_metadata["id"] == "chol_mean"
    assert variable["observable_property"] == property_metadata
    assert property_metadata["calculation"] == {
        "name": "mean_lab_cholesterol",
        "function": (
            "pypeh.adapters.aggregation.polars_adapter.statistics."
            "statistics_mean"
        ),
        "inputs": [
            {
                "argument": None,
                "source_observation": source_observation.id,
                "source_variable": "chol",
                "source_label": "chol",
                "value": None,
            }
        ],
        "results": ["chol_mean"],
    }
    assert {
        "derived_observation": target.id,
        "was_derived_from": source_observation.id,
    } in tree["provenance"]["derived_observations"]
    assert json.loads(json.dumps(tree)) == tree
