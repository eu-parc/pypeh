import json

from pathlib import Path

import pytest
import yaml

from pypeh import LocalFileConfig, Session
from pypeh.core.models.metadata_dto import StudyMetadataConfig

pytestmark = [
    pytest.mark.integration,
    pytest.mark.dataframe,
]

INPUT_DIR = Path(__file__).with_name("input")
CONNECTION_LABEL = "local_file"
DEMO_CACHE_FILE = "peh_demo.yaml"
DEMO_XLSX_FILE = "peh_demo_data.xlsx"

# Expected study-metadata tree for the peh_demo fixture
# (peh_demo.yaml + peh_demo_data.xlsx), built with
# extra_provenance={"source_file": "peh_demo_data.xlsx"}.
#
# The expected data is embedded in this (already tracked) test
# module instead of living in a separate input file, so a fresh
# checkout always has it.
# Derived observations follow the observation they were derived
# from. The pypeh / peh_model versions are omitted: they depend
# on the installed environment and are checked separately by
# the test.
EXPECTED_TREE_YAML = """
observations:
- id: peh:OBS_SAMPLE_METADATA
  label: SAMPLE_METADATA
  observable_properties:
  - id: id_sample
    label: id_sample
    name: demo|sample|id_sample
    kind: measurement
    value_type: string
    unit: null
    categorical: null
    multivalued: null
    required: true
    value_options: []
    groups: []
  - id: sex
    label: sex
    name: demo|person|sex
    kind: measurement
    value_type: string
    unit: null
    categorical: true
    multivalued: false
    required: true
    value_options:
    - '1'
    - '2'
    - '9'
    groups: []
  - id: age_birth_m
    label: age_birth_m
    name: demo|person|age_birth_m
    kind: measurement
    value_type: integer
    unit: Month
    categorical: null
    multivalued: null
    required: null
    value_options: []
    groups: []
- id: peh:OBS_LAB_ASSAYS
  label: LAB_ASSAYS
  observable_properties:
  - id: chol
    label: chol
    name: demo|bloodwholeblood|chol
    kind: measurement
    value_type: decimal
    unit: MicroGM-PER-L
    categorical: null
    multivalued: null
    required: null
    value_options: []
    groups:
    - Lipid panel
    semantics:
      indicator:
        id: peh:IND_TOTAL_CHOLESTEROL
        label: Total cholesterol
        definition: Sum of cholesterol contained in all lipoproteins of the sample.
        indicator_type: observation
        quantity_kind: http://qudt.org/vocab/quantitykind/Mass
        exact_matches: []
        relevant_observable_entity_types:
        - sample
        suggester: https://orcid.org/0000-0002-1825-0097
      matrix:
        id: peh:MATRIX_BLOOD_WHOLE_BLOOD
        label: Blood (whole blood)
        definition: Whole blood matrix, the substrate for the lab assays.
        exact_matches: []
      biochem_entity:
        id: peh:BCE_CHOLESTEROL
        label: Cholesterol
        definition: A sterol lipid and a component of the cell membrane of every animal
          cell; also a precursor of steroid hormones and bile acids.
        exact_matches:
        - CHEBI:16288
        aliases:
        - total cholesterol
        molecular_weight_gram_per_mol: 386.65
        groups:
        - sterol
        - lipid
        is_metabolite_of: []
      quantity_kind: http://qudt.org/vocab/quantitykind/Mass
      constraints:
      - minimum_plausible_concentration
  - id: hdl
    label: hdl
    name: null
    kind: measurement
    value_type: decimal
    unit: MicroGM-PER-L
    categorical: null
    multivalued: null
    required: null
    value_options: []
    groups:
    - Lipid panel
    semantics:
      indicator:
        id: peh:IND_HDL_CHOLESTEROL
        label: HDL cholesterol
        definition: null
        indicator_type: observation
        quantity_kind: http://qudt.org/vocab/quantitykind/Mass
        exact_matches: []
        relevant_observable_entity_types:
        - sample
        suggester: null
      matrix:
        id: peh:MATRIX_SERUM
        label: Serum
        definition: The cell-free fraction of coagulated blood.
        exact_matches: []
      biochem_entity:
        id: peh:BCE_HDL_CHOLESTEROL
        label: HDL cholesterol
        definition: The cholesterol content of the high density lipoprotein fraction.
        exact_matches:
        - CHEBI:16289
        aliases: []
        molecular_weight_gram_per_mol: 386.65
        groups:
        - lipoprotein
        is_metabolite_of: []
      quantity_kind: http://qudt.org/vocab/quantitykind/Mass
      constraints: []
  - id: trigl
    label: trigl
    name: null
    kind: measurement
    value_type: decimal
    unit: MicroGM-PER-L
    categorical: null
    multivalued: null
    required: null
    value_options: []
    groups: []
    semantics:
      indicator:
        id: peh:IND_TRIGLYCERIDES
        label: Triglycerides
        definition: null
        indicator_type: observation
        quantity_kind: http://qudt.org/vocab/quantitykind/Mass
        exact_matches: []
        relevant_observable_entity_types:
        - sample
        suggester: null
      matrix:
        id: peh:MATRIX_SERUM
        label: Serum
        definition: The cell-free fraction of coagulated blood.
        exact_matches: []
      biochem_entity:
        id: peh:BCE_TRIGLYCERIDE
        label: Triglyceride
        definition: Any triester of glycerol with three fatty acids.
        exact_matches:
        - CHEBI:18059
        aliases: []
        molecular_weight_gram_per_mol: 885.4
        groups:
        - glycerolipid
        is_metabolite_of:
        - peh:BCE_CHOLESTEROL
      quantity_kind: http://qudt.org/vocab/quantitykind/Mass
      constraints: []
- id: peh:OBS_LAB_ENRICHED
  label: LAB_ASSAYS_ENRICHED
  observable_properties:
  - id: chol_imputed
    label: chol_imputed
    name: null
    kind: calculation
    value_type: decimal
    unit: MicroGM-PER-L
    categorical: null
    multivalued: null
    required: null
    value_options: []
    groups: []
    calculation:
      name: abs_corrected_cholesterol
      function: compehndly.entrypoints.medium_bound_imputation
      inputs:
      - argument: measurement
        source_observation: peh:OBS_LAB_ASSAYS
        source_variable: chol
        source_label: chol
        value: null
      - argument: loq
        source_observation: peh:OBS_LAB_ASSAYS
        source_variable: chol_loq
        source_label: chol_loq
        value: null
      - argument: lod
        source_observation: peh:OBS_LAB_ASSAYS
        source_variable: chol_lod
        source_label: chol_lod
        value: null
      results:
      - chol_imputed
- id: peh:OBS_SUMMARY
  label: SUMMARY
  observable_properties:
  - id: chol_mean
    label: chol_mean
    name: null
    kind: calculation
    value_type: decimal
    unit: MicroGM-PER-L
    categorical: null
    multivalued: null
    required: null
    value_options: []
    groups: []
    calculation:
      name: mean_corrected_cholesterol
      function: pypeh.adapters.aggregation.polars_adapter.statistics.statistics_mean
      inputs:
      - argument: null
        source_observation: peh:OBS_LAB_ENRICHED
        source_variable: chol_imputed
        source_label: chol_imputed
        value: null
      results:
      - chol_mean
datasets:
- label: SAMPLE_METADATA
  described_by: peh:SECTION_SAMPLE_METADATA
  observations:
  - peh:OBS_SAMPLE_METADATA
  variables:
  - label: id_sample
    observable_property:
      id: id_sample
      label: id_sample
      name: demo|sample|id_sample
      kind: measurement
      value_type: string
      unit: null
      categorical: null
      multivalued: null
      required: true
      value_options: []
      groups: []
    data_type: STRING
    primary_key: true
  - label: sex
    observable_property:
      id: sex
      label: sex
      name: demo|person|sex
      kind: measurement
      value_type: string
      unit: null
      categorical: true
      multivalued: false
      required: true
      value_options:
      - '1'
      - '2'
      - '9'
      groups: []
    data_type: STRING
    primary_key: false
  - label: age_birth_m
    observable_property:
      id: age_birth_m
      label: age_birth_m
      name: demo|person|age_birth_m
      kind: measurement
      value_type: integer
      unit: Month
      categorical: null
      multivalued: null
      required: null
      value_options: []
      groups: []
    data_type: INTEGER
    primary_key: false
- label: LAB_ASSAYS
  described_by: peh:SECTION_LAB_ASSAYS
  observations:
  - peh:OBS_LAB_ASSAYS
  variables:
  - label: id_sample
    observable_property:
      id: id_sample
      label: id_sample
      name: demo|sample|id_sample
      kind: measurement
      value_type: string
      unit: null
      categorical: null
      multivalued: null
      required: true
      value_options: []
      groups: []
    data_type: STRING
    primary_key: true
  - label: chol
    observable_property:
      id: chol
      label: chol
      name: demo|bloodwholeblood|chol
      kind: measurement
      value_type: decimal
      unit: MicroGM-PER-L
      categorical: null
      multivalued: null
      required: null
      value_options: []
      groups:
      - Lipid panel
      semantics:
        indicator:
          id: peh:IND_TOTAL_CHOLESTEROL
          label: Total cholesterol
          definition: Sum of cholesterol contained in all lipoproteins of the sample.
          indicator_type: observation
          quantity_kind: http://qudt.org/vocab/quantitykind/Mass
          exact_matches: []
          relevant_observable_entity_types:
          - sample
          suggester: https://orcid.org/0000-0002-1825-0097
        matrix:
          id: peh:MATRIX_BLOOD_WHOLE_BLOOD
          label: Blood (whole blood)
          definition: Whole blood matrix, the substrate for the lab assays.
          exact_matches: []
        biochem_entity:
          id: peh:BCE_CHOLESTEROL
          label: Cholesterol
          definition: A sterol lipid and a component of the cell membrane of every
            animal cell; also a precursor of steroid hormones and bile acids.
          exact_matches:
          - CHEBI:16288
          aliases:
          - total cholesterol
          molecular_weight_gram_per_mol: 386.65
          groups:
          - sterol
          - lipid
          is_metabolite_of: []
        quantity_kind: http://qudt.org/vocab/quantitykind/Mass
        constraints:
        - minimum_plausible_concentration
    data_type: FLOAT
    primary_key: false
  - label: hdl
    observable_property:
      id: hdl
      label: hdl
      name: null
      kind: measurement
      value_type: decimal
      unit: MicroGM-PER-L
      categorical: null
      multivalued: null
      required: null
      value_options: []
      groups:
      - Lipid panel
      semantics:
        indicator:
          id: peh:IND_HDL_CHOLESTEROL
          label: HDL cholesterol
          definition: null
          indicator_type: observation
          quantity_kind: http://qudt.org/vocab/quantitykind/Mass
          exact_matches: []
          relevant_observable_entity_types:
          - sample
          suggester: null
        matrix:
          id: peh:MATRIX_SERUM
          label: Serum
          definition: The cell-free fraction of coagulated blood.
          exact_matches: []
        biochem_entity:
          id: peh:BCE_HDL_CHOLESTEROL
          label: HDL cholesterol
          definition: The cholesterol content of the high density lipoprotein fraction.
          exact_matches:
          - CHEBI:16289
          aliases: []
          molecular_weight_gram_per_mol: 386.65
          groups:
          - lipoprotein
          is_metabolite_of: []
        quantity_kind: http://qudt.org/vocab/quantitykind/Mass
        constraints: []
    data_type: FLOAT
    primary_key: false
  - label: trigl
    observable_property:
      id: trigl
      label: trigl
      name: null
      kind: measurement
      value_type: decimal
      unit: MicroGM-PER-L
      categorical: null
      multivalued: null
      required: null
      value_options: []
      groups: []
      semantics:
        indicator:
          id: peh:IND_TRIGLYCERIDES
          label: Triglycerides
          definition: null
          indicator_type: observation
          quantity_kind: http://qudt.org/vocab/quantitykind/Mass
          exact_matches: []
          relevant_observable_entity_types:
          - sample
          suggester: null
        matrix:
          id: peh:MATRIX_SERUM
          label: Serum
          definition: The cell-free fraction of coagulated blood.
          exact_matches: []
        biochem_entity:
          id: peh:BCE_TRIGLYCERIDE
          label: Triglyceride
          definition: Any triester of glycerol with three fatty acids.
          exact_matches:
          - CHEBI:18059
          aliases: []
          molecular_weight_gram_per_mol: 885.4
          groups:
          - glycerolipid
          is_metabolite_of:
          - peh:BCE_CHOLESTEROL
        quantity_kind: http://qudt.org/vocab/quantitykind/Mass
        constraints: []
    data_type: FLOAT
    primary_key: false
provenance:
  series_label: DEMO_STUDY
  source_file: peh_demo_data.xlsx
  data_import_config: peh:IMPORT_DEMO
  data_layout: peh:LAYOUT_DEMO
  sections:
  - dataset: SAMPLE_METADATA
    described_by: peh:SECTION_SAMPLE_METADATA
  - dataset: LAB_ASSAYS
    described_by: peh:SECTION_LAB_ASSAYS
  derived_observations:
  - derived_observation: peh:OBS_LAB_ENRICHED
    was_derived_from: peh:OBS_LAB_ASSAYS
  - derived_observation: peh:OBS_SUMMARY
    was_derived_from: peh:OBS_LAB_ENRICHED
  validation_report: null
"""


@pytest.fixture
def demo_workflow():
    connection = LocalFileConfig(
        label=CONNECTION_LABEL,
        config_dict={"root_folder": str(INPUT_DIR)},
    )
    session = Session(connection_config=[connection], default_connection=None)
    session.load_persisted_cache(
        DEMO_CACHE_FILE, connection_label=CONNECTION_LABEL
    )
    import_config = next(iter(session.cache.get_all("DataImportConfig")))
    series = session.import_tabular_dataset_series(
        source=DEMO_XLSX_FILE,
        data_import_config=import_config,
        file_format="xlsx",
        connection_label=CONNECTION_LABEL,
        cast_error_policy="null",
    )
    return session, import_config, series


def test_study_metadata_matches_expected_tree(demo_workflow):
    """
    The peh_demo workflow's metadata tree must match the expected
    tree embedded in this module (EXPECTED_TREE_YAML), including the
    dependency order of the derived observations.
    """
    session, import_config, series = demo_workflow
    tree = session.create_study_metadata(
        dataset_series=series,
        data_import_config=import_config,
        metadata_config=StudyMetadataConfig(
            extra_provenance={"source_file": DEMO_XLSX_FILE},
        ),
    )
    expected = yaml.safe_load(EXPECTED_TREE_YAML)

    # the installed versions depend on the environment: check their
    # shape, then compare the rest of the tree verbatim.
    provenance = tree["provenance"]
    assert isinstance(provenance.pop("pypeh_version"), str)
    assert isinstance(provenance.pop("peh_model_version"), str)
    assert tree == expected
    assert yaml.safe_load(yaml.safe_dump(tree, sort_keys=False)) == tree


def test_control_variables_excluded(demo_workflow):
    session, import_config, series = demo_workflow
    tree = session.create_study_metadata(
        dataset_series=series,
        data_import_config=import_config,
    )
    property_ids = [
        prop["id"]
        for observation in tree["observations"]
        for prop in observation["observable_properties"]
    ]
    assert "chol_lod" not in property_ids
    assert "chol_loq" not in property_ids

    lab_assays = next(
        dataset
        for dataset in tree["datasets"]
        if dataset["label"] == "LAB_ASSAYS"
    )
    labels = [variable["label"] for variable in lab_assays["variables"]]
    assert "chol_lod" not in labels
    chol = next(
        variable
        for variable in lab_assays["variables"]
        if variable["label"] == "chol"
    )
    assert chol["data_type"] == "FLOAT"


def test_derivation_chain_without_study_links(demo_workflow):
    session, import_config, series = demo_workflow
    tree = session.create_study_metadata(
        dataset_series=series,
        data_import_config=import_config,
    )
    assert set(tree) == {"observations", "datasets", "provenance"}
    assert tree["provenance"]["derived_observations"] == [
        {
            "derived_observation": "peh:OBS_LAB_ENRICHED",
            "was_derived_from": "peh:OBS_LAB_ASSAYS",
        },
        {
            "derived_observation": "peh:OBS_SUMMARY",
            "was_derived_from": "peh:OBS_LAB_ENRICHED",
        },
    ]


@pytest.mark.parametrize("file_format", ["yaml", "json"])
def test_generated_metadata_roundtrips_through_dump(
    demo_workflow, tmp_path, file_format
):
    session, import_config, series = demo_workflow
    tree = session.create_study_metadata(
        dataset_series=series,
        data_import_config=import_config,
    )
    assert "schema_version" not in tree
    output_path = tmp_path / f"metadata.{file_format}"
    written = session.dump_study_metadata(
        tree,
        str(output_path),
        file_format=file_format,
        connection_label=CONNECTION_LABEL,
    )
    assert written == str(output_path)
    payload = output_path.read_text(encoding="utf-8")
    loaded = (
        yaml.safe_load(payload)
        if file_format == "yaml"
        else json.loads(payload)
    )
    assert loaded == tree
    assert loaded["provenance"]["pypeh_version"]
    assert loaded["provenance"]["peh_model_version"]
