# Dataset Series Alignment

`concatenate_tabular_dataset_series` can concatenate already-loaded
`DatasetSeries` objects. Without an explicit alignment plan, pypeh uses strict
matching: every source series must have the same dataset labels and the same
observable property identifiers within each paired dataset.

Use a PEH `ObservationAlignment` when source series use different observation
or observable property identifiers, or when one target observation should be
assembled from more than one source observation.

When `alignment_plan` references `ObservationGroup`s by id (via
`ObservationAssembly.source_observation_groups`), register those groups in the
session cache (`session.cache.add(...)`) before calling
`concatenate_tabular_dataset_series`; they are resolved from the cache
automatically.

## Strict Concatenation

If all source `DatasetSeries` already use matching dataset labels and matching
observable property identifiers, no alignment plan is needed.

```python
combined = session.concatenate_tabular_dataset_series(
    [series_a, series_b],
    output_label="combined_lab",
)
```

## Align Different Observations And Properties

When source studies use different identifiers for semantically corresponding
observations or observable properties, provide an `ObservationAlignment`.

```python
from peh_model.peh import (
    ObservablePropertyMapping,
    ObservationAlignment,
    ObservationAssembly,
    ObservationGroup,
)

observation_groups = (
    ObservationGroup(
        id="peh:og_study_a_lab",
        observation_id_list=["study_a:obs_lab"],
    ),
    ObservationGroup(
        id="peh:og_study_b_lab",
        observation_id_list=["study_b:obs_lab"],
    ),
)
for group in observation_groups:
    session.cache.add(group)

alignment_plan = ObservationAlignment(
    id="peh:alignment_lab",
    observation_assemblies=[
        ObservationAssembly(
            target_observation_id="peh:obs_lab",
            source_observation_groups=[
                "peh:og_study_a_lab",
                "peh:og_study_b_lab",
            ],
            observable_property_mappings=[
                ObservablePropertyMapping(
                    target_observable_property_id="peh:prop_id_sample",
                    source_observable_property_ids=[
                        "study_a:sample_id",
                        "study_b:sample_id",
                    ],
                ),
                ObservablePropertyMapping(
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

combined = session.concatenate_tabular_dataset_series(
    [series_a, series_b],
    alignment_plan=alignment_plan,
    output_label="aligned_lab",
)
```

The order of each source group and property list is positional. In the example above,
`study_a:obs_lab`, `study_a:sample_id`, and `study_a:chol` are resolved against
`series_a`; the corresponding `study_b:*` identifiers are resolved against
`series_b`.

## Assemble One Target Observation From Several Source Observations

A source series can contribute multiple observations to one target observation.
This is useful when one source study splits fields across observation concepts
that another source study represents as a single observation.

```python
observation_groups = (
    ObservationGroup(
        id="peh:og_study_a_sample_lab",
        observation_id_list=["study_a:obs_sample", "study_a:obs_lab"],
    ),
    ObservationGroup(
        id="peh:og_study_b_subject",
        observation_id_list=["study_b:obs_subject"],
    ),
)
for group in observation_groups:
    session.cache.add(group)

alignment_plan = ObservationAlignment(
    id="peh:alignment_assembled_lab",
    observation_assemblies=[
        ObservationAssembly(
            target_observation_id="peh:obs_lab",
            source_observation_groups=[
                "peh:og_study_a_sample_lab",
                "peh:og_study_b_subject",
            ],
            observable_property_mappings=[
                ObservablePropertyMapping(
                    target_observable_property_id="peh:prop_id_sample",
                    source_observable_property_ids=[
                        "study_a:sample_id",
                        "study_b:subject_id",
                    ],
                ),
                ObservablePropertyMapping(
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

combined = session.concatenate_tabular_dataset_series(
    [series_a, series_b],
    alignment_plan=alignment_plan,
    output_label="assembled_lab",
)
```

For each mapped observable property, pypeh searches the source observations in
that source group. The property must resolve to exactly one concrete source
field. Multiple matches are accepted only when they point to the same concrete
dataset element, which covers shared identifying fields registered for more
than one observation.

## Infer Shared Observable Properties

If an `ObservationAssembly` does not provide `observable_property_mappings`,
pypeh infers identity mappings for observable property identifiers shared by
all source observation groups.

```python
observation_groups = (
    ObservationGroup(
        id="peh:og_sample_lab",
        observation_id_list=["peh:obs_sample", "peh:obs_lab"],
    ),
    ObservationGroup(
        id="peh:og_lab",
        observation_id_list=["peh:obs_lab"],
    ),
)
for group in observation_groups:
    session.cache.add(group)

alignment_plan = ObservationAlignment(
    id="peh:alignment_inferred_lab",
    observation_assemblies=[
        ObservationAssembly(
            target_observation_id="peh:obs_lab",
            source_observation_groups=["peh:og_sample_lab", "peh:og_lab"],
        ),
    ],
)

combined = session.concatenate_tabular_dataset_series(
    [series_a, series_b],
    alignment_plan=alignment_plan,
    output_label="inferred_lab",
)
```

Inference is identity-based. It only maps observable properties with the same
identifier in every source group. If source studies use different identifiers
for corresponding properties, provide explicit `ObservablePropertyMapping`
objects.

## Current Restrictions

Direct concatenation currently assumes:

- each source `ObservationGroup` position corresponds to the `DatasetSeries` at
  the same position in the list passed to `concatenate_tabular_dataset_series`;
- each explicit `ObservablePropertyMapping.source_observable_property_ids`
  list has one entry per source `DatasetSeries`;
- each scoped property resolves to one source field per series;
- aligned fields have compatible value types;
- one output dataset is not assembled from multiple source datasets within the
  same source series.

Transformations, derivations, unit conversion, and cross-dataset assembly within
one source series are not represented by this direct alignment model yet.

## Filtering And Reshaping Before Concatenation

`create_tabular_extract` combines reshaping, per-section filtering, and
concatenation in one call. For each source `DatasetSeries`, it reshapes the
series with `export_tabular_dataset_series` using `data_export_config`, then
applies each resulting `DataLayoutSection`'s `data_filter` (falling back to
that same source series to resolve filter predicate columns that reshaping
projected away). The per-source extracts are then concatenated exactly like
`concatenate_tabular_dataset_series`, including `alignment_plan` handling and
cache-based `ObservationGroup` resolution.

```python
extract = session.create_tabular_extract(
    [series_a, series_b],
    data_export_config,
    alignment_plan=alignment_plan,
    output_label="filtered_lab",
)
```

When only one source series is given, concatenation is skipped and the single
reshaped/filtered series is returned directly (`alignment_plan` is ignored in
that case).
