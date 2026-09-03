# Session Reference

## Constructor

```python
Session(
    *,
    connection_config: ConnectionConfig | Sequence[ConnectionConfig] | None = None,
    default_connection: str | ConnectionConfig | None = None,
    env_file: str | None = None,
    load_from_default_connection: str | None = None,
)
```

`connection_config` accepts one connection config or a sequence of configs.
When `default_connection` is a string, it must match one of those config
labels. When `default_connection` is a `ConnectionConfig`, it is registered as
the session's default persisted cache connection.

## Resource and Cache Methods

```python
load_persisted_cache(
    source: str | None = None,
    connection_label: str | None = None,
) -> None
```

Load YAML resources from a configured connection into the session cache. If
`connection_label` is omitted, the default persisted cache connection is used.

```python
dump_cache(
    output_path: str,
    file_format: str = "yaml",
    connection_label: str | None = None,
    cache: CacheContainer | CacheContainerView | None = None,
) -> None
```

Write a cache or cache view to a configured connection. Currently supported
formats are `ttl`, `turtle`, `trig`, and `yaml`.

```python
get_resource(
    resource_identifier: str,
    resource_type: str,
) -> NamedThing | None
```

Return a cached resource by identifier and PEH model type name.

```python
load_resource(
    resource_identifier: str,
    resource_type: str,
    resource_path: str | None = None,
    connection_label: str | None = None,
) -> NamedThing | None
```

Return a cached resource, or load resources from a configured connection before
trying again.

## Tabular Data Methods

```python
import_tabular_dataset_series(
    source: str,
    data_import_config: DataImportConfig,
    file_format: str | None = None,
    connection_label: str | None = None,
    allow_incomplete: bool = False,
    cast_error_policy: Literal["null", "raise", "report"] = "raise",
    schema_error_policy: Literal["raise", "report"] = "raise",
) -> DatasetSeries | ValidationErrorReportCollection
```

Import external tabular data, map it to a `DatasetSeries`, and check labels
against the schema implied by the `DataImportConfig`. Use this method when the
source data requires a PEH `DataImportConfig`.

```python
load_tabular_dataset_series(
    source: str,
    data_import_config: DataImportConfig,
    file_format: str | None = None,
    connection_label: str | None = None,
    allow_incomplete: bool = False,
    cast_error_policy: Literal["null", "raise", "report"] = "raise",
    schema_error_policy: Literal["raise", "report"] = "raise",
) -> DatasetSeries | ValidationErrorReportCollection
```

Deprecated compatibility alias for `import_tabular_dataset_series`. It accepts
the same arguments, logs a warning, and forwards to the import method.

```python
dump_tabular_dataset_series(
    dataset_series: DatasetSeries,
    output_path: str | None = None,
    file_format: Literal["parquet", "xlsx"] = "parquet",
    connection_label: str | None = None,
) -> list[str]
```

Persist or export a tabular `DatasetSeries` through the configured connection.

With `file_format="parquet"`, pypeh writes semantic parquet persistence files:
one parquet file per `Dataset`. The returned list contains all written parquet
paths.

With `file_format="xlsx"`, pypeh writes an export-only Excel workbook: one
workbook path is returned, and each `Dataset` becomes one worksheet containing
the Polars dataframe from `dataset.data`. URI-like dataset labels are shortened
to their final URI segment for worksheet names. XLSX export requires the
`xlsxwriter` dependency and cannot be read back as a semantic `DatasetSeries`.

```python
read_tabular_dataset_series(
    source_paths: Sequence[str],
    file_format: Literal["parquet"] = "parquet",
    connection_label: str | None = None,
    validate_foreign_keys: bool = True,
) -> DatasetSeries
```

Read pypeh semantic parquet files previously produced by
`dump_tabular_dataset_series`. `source_paths` must be a sequence of parquet file
paths, such as the list returned by `dump_tabular_dataset_series`.

This method currently supports parquet only. XLSX files produced by
`dump_tabular_dataset_series(..., file_format="xlsx")` are exports for
inspection or downstream spreadsheet workflows, not semantic persistence files.

```python
export_tabular_dataset_series(
    source_dataset_series: DatasetSeries,
    data_export_config: DataExportConfig,
    adapter_label: str = "dataops",
) -> DatasetSeries
```

Reshape a `DatasetSeries` according to a PEH `DataExportConfig` and return the
reshaped `DatasetSeries`. The `DataLayout` referenced by `data_export_config`
defines the requested export shape: `section_mapping_links` bind layout
sections to source Observations, and the adapter projects/joins the source
series into the requested datasets.

```python
concatenate_tabular_dataset_series(
    dataset_series: Sequence[DatasetSeries],
    output_label: str | None = None,
    alignment_plan: ObservationAlignment | None = None,
    adapter_label: str = "dataops",
) -> DatasetSeries
```

Concatenate already-loaded `DatasetSeries` objects. Without `alignment_plan`,
pypeh uses strict matching: every source series must have the same dataset
labels and the same observable property identifiers within each paired
dataset. With `alignment_plan`, source Observations and ObservableProperties
can be assembled into target Observations; any `ObservationGroup` referenced by
id in `alignment_plan` is resolved from the session cache automatically (add
groups with `session.cache.add(...)` before calling). See
[Dataset Series Alignment](dataset-series-alignment.md) for details.

```python
create_tabular_extract(
    dataset_series: Sequence[DatasetSeries],
    data_export_config: DataExportConfig,
    alignment_plan: ObservationAlignment | None = None,
    output_label: str | None = None,
    adapter_label: str = "extract",
) -> DatasetSeries
```

Build a single tabular extract from a sequence of source `DatasetSeries`. For
each source series, reshapes it with `export_tabular_dataset_series` using
`data_export_config`, then applies each resulting `DataLayoutSection`'s
`data_filter` (falling back to that same source series to resolve filter
predicate columns that reshaping projected away). The per-source extracts are
then concatenated with `concatenate_tabular_dataset_series` (same
`alignment_plan`/cache-based `ObservationGroup` resolution). When only one
source series is given, concatenation is skipped and the single
reshaped/filtered series is returned directly.

```python
split_dataset_series_by_observation(
    source_dataset_series: DatasetSeries,
    new_dataset_series_label: str | None = None,
    label_collision_strategy: Literal[
        "error",
        "prefix_observable_property_id",
        "prefix_source_dataset",
    ] = "prefix_source_dataset",
    adapter_label: str = "dataops",
) -> DatasetSeries
```

Return a new `DatasetSeries` whose datasets are organized by observation. The
method delegates to the registered data-operations adapter. When
`new_dataset_series_label` is omitted, the adapter derives a label from the
source series label.

`label_collision_strategy` controls output column labels when fields from
multiple source datasets would share one label in the split observation
dataset. `"prefix_source_dataset"` keeps existing behavior by prefixing
collisions with the source dataset label, `"prefix_observable_property_id"`
uses the observable-property ID tail, and `"error"` rejects the collision.

```python
validate_tabular_dataset(
    data: Dataset,
    dependent_data: DatasetSeries | None = None,
    allow_incomplete: bool = False,
) -> ValidationErrorReport
```

Validate a single dataset with the registered validation adapter.

```python
validate_tabular_dataset_series(
    dataset_series: DatasetSeries,
    allow_incomplete: bool = False,
) -> ValidationErrorReportCollection
```

Validate all datasets with data in a `DatasetSeries`.

```python
build_validation_config(
    data_layout: DataLayout,
    sections_to_validate: list[str] | None = None,
    allow_incomplete: bool = False,
) -> dict[str, ValidationConfig]
```

Build validation configuration objects for sections in a PEH `DataLayout`.

## Adapter Methods

```python
register_default_adapter(interface_functionality: str)
```

Register and return the default adapter class for `validation`, `dataops`,
`enrichment`, or supported aggregation functionality.

```python
register_adapter(interface_functionality: str, adapter) -> None
```

Register an adapter instance or class for a workflow key.

```python
register_adapter_by_name(
    interface_functionality: str,
    adapter_module_name: str,
    adapter_class_name: str,
) -> None
```

Import and register an adapter class by module and class name.

```python
get_adapter(interface_functionality: str)
```

Return the registered adapter. If a class was registered, it is instantiated.

## Enrichment and Aggregation

```python
unpack_derived_observation_group(
    observation_group_id: str,
) -> Generator[tuple[DerivedObservation, Observation], None, None]
```

Resolve an `ObservationGroup` from the session cache and yield
`(target_observation, source_observation)` pairs. Each target must be a
`DerivedObservation`, and its source is resolved from `was_derived_from`.

```python
enrich(
    source_dataset_series: DatasetSeries,
    target_observations: list[Observation],
    target_derived_from: list[Observation],
    target_dataset_labels: list[str] | None = None,
    target_label_collision_strategy: Literal[
        "error",
        "prefix_observable_property_id",
        "prefix_source_dataset",
    ] = "error",
) -> DatasetSeries
```

Delegate enrichment to the registered enrichment adapter.

`target_label_collision_strategy` controls duplicate labels among the target
derived observable properties. `"error"` rejects duplicates,
`"prefix_observable_property_id"` prefixes a unique observable-property ID
tail, and `"prefix_source_dataset"` prefixes the source dataset that feeds the
calculation. When the source was produced by
`split_dataset_series_by_observation`, source provenance recorded during split
is used.

```python
aggregate(
    source_dataset_series: DatasetSeries,
    target_observations: list[Observation],
    target_derived_from: list[Observation],
    target_dataset_labels: list[str] | None = None,
    target_label_collision_strategy: Literal[
        "error",
        "prefix_observable_property_id",
        "prefix_source_dataset",
    ] = "error",
) -> DatasetSeries
```

Delegate summarization to the registered aggregation adapter.

`target_label_collision_strategy` has the same meaning as on `enrich`.
Aggregation also uses the resolved target schema label as the dataframe result
alias, so resolved target labels stay aligned with computed columns.

## Namespace Methods

```python
bind_namespace_manager(namespace_manager: NamespaceManager) -> None
```

Bind a namespace manager for minted identifiers.

```python
mint_and_cache(
    resource_cls: type[NamedThing],
    namespace_key: str | None = None,
    identifiying_field: str = "id",
    **resource_kwargs,
) -> NamedThing
```

Mint an identifier, create a PEH model resource, add it to the cache, and return
the resource.
