# Plan: Session Tabular Export API (split into two PRs)

## TL;DR
**PR 1 — refactor + export-config scaffolding.** Extract the body of `DatasetSeries.from_peh_data_import_config` into a new shared classmethod `from_peh_data_config(data_config: peh.DataImportConfig | peh.DataExportConfig, ...)`; `from_peh_data_import_config` becomes a one-line delegate. Add a `from_peh_data_export_config` stub that raises `NotImplementedError` so the public surface for PR 2 is already in place. Includes a parity unit test plus a stub-raises test. No dep bump.

**PR 2 — new feature.** Wire `from_peh_data_export_config` to actually delegate to `from_peh_data_config` (drop the `NotImplementedError`), add `DataOpsInterface.extract_from_source`, and `Session.export_tabular_dataset_series` (default `file_format="xlsx"`). Verify peh-model bump to `>=0.6.2,<0.7.0`. Add construction + extract + end-to-end tests.

## PR 1 — Refactor + export-config scaffolding

### Steps
1. **Extract shared constructor** in `src/pypeh/core/models/internal_data_layout.py`:
   ```python
   @classmethod
   def from_peh_data_config(
       cls,
       data_config: peh.DataImportConfig | peh.DataExportConfig,
       cache_view: CacheContainerView,
       identifier_provider: IdentifierProvider | None = None,
   ) -> DatasetSeries:
       ...
   ```
   Move the entire current body of `from_peh_data_import_config` (L808–930) into this new method verbatim. Rename the local `data_import_config` reference inside the body to `data_config`. Keep all `assert isinstance(...)` checks that are not specific to the import-vs-export distinction. The internal `assert isinstance(section_mapping, peh.DataImportSectionMapping)` already covers both config types because `peh.DataExportConfig.section_mapping` is also a `DataImportSectionMapping` (confirmed in peh-model 0.6.2).

2. **Reduce `from_peh_data_import_config` to a delegate.**
   ```python
   @classmethod
   def from_peh_data_import_config(
       cls,
       data_import_config: peh.DataImportConfig,
       cache_view: CacheContainerView,
       identifier_provider: IdentifierProvider | None = None,
   ) -> DatasetSeries:
       assert isinstance(data_import_config, peh.DataImportConfig)
       return cls.from_peh_data_config(
           data_config=data_import_config,
           cache_view=cache_view,
           identifier_provider=identifier_provider,
       )
   ```
   Public signature unchanged → all existing callers keep working without modification.

3. **Add `from_peh_data_export_config` placeholder** that raises `NotImplementedError` (pending PR 2). This locks in the public surface and prevents accidental calls before the full extract pipeline lands:
   ```python
   @classmethod
   def from_peh_data_export_config(
       cls,
       data_export_config: peh.DataExportConfig,
       cache_view: CacheContainerView,
       identifier_provider: IdentifierProvider | None = None,
   ) -> DatasetSeries:
       raise NotImplementedError(
           "DatasetSeries.from_peh_data_export_config is not implemented yet; "
           "full export support arrives in a follow-up PR."
       )
   ```

4. **Tests** in `tests/core/models/test_internal_datalayout.py`:
   - `test_from_peh_data_config_matches_import_config` — parity check that resolves the existing `peh:IMPORT_CONFIG_CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA` from cache, calls both `from_peh_data_import_config` and `from_peh_data_config`, and asserts equal `parts`, `observation_ids`, schema element labels, `_context_index`, and `_obs_index`.
   - `test_from_peh_data_export_config_not_implemented_yet` — constructs a minimal `peh.DataExportConfig` and asserts `pytest.raises(NotImplementedError, match="not implemented yet")`.

5. **No other changes.** Do not touch `pyproject.toml`, `dataops.py`, `session.py`, `from_peh_datalayout`.

### Relevant files (PR 1)
- `src/pypeh/core/models/internal_data_layout.py` — refactor + stub.
- `tests/core/models/test_internal_datalayout.py` — parity + stub-raises tests.

### Verification (PR 1)
1. `pytest tests/core/models/test_internal_datalayout.py` — DatasetSeries unit tests + the two new tests pass.
2. `pytest tests/core/interfaces/dataops/test_dataops.py` — covers `TestEnrichment.raw_dataset_series` which calls `from_peh_data_import_config` directly.
3. `pytest tests/end_to_end/validation/` — exercises `from_peh_data_import_config` via `Session.import_tabular_dataset_series`.
4. `pytest tests/core/session/test_session_dataset_parquet.py` — sanity for the rest of the session API.
5. `make test-all` — full marker-driven suite green.

### Out of scope for PR 1
- Implementing `from_peh_data_export_config` (just the stub for now).
- Adding `extract_from_source`, `export_tabular_dataset_series`.
- Bumping `peh-model` (already handled on main; PR 2 just verifies it).

---

## PR 2 — New export feature (built on PR 1)

### Phase A — Wire the export-config delegate
File: `src/pypeh/core/models/internal_data_layout.py`

A1. Replace the `NotImplementedError` body of `from_peh_data_export_config` with: `assert isinstance(data_export_config, peh.DataExportConfig)` then `return cls.from_peh_data_config(data_config=data_export_config, cache_view=cache_view, identifier_provider=identifier_provider)`. Does **not** call `from_peh_datalayout` (which mints generic Observation IDs).

A2. The `from_peh_data_config` parameter type is already broadened to the union in PR 1; no signature change required.

### Phase B — `DataOpsInterface.extract_from_source`
File: `src/pypeh/core/interfaces/dataops.py`

B1. Add `extract_from_source(self, source: DatasetSeries[T_DataType], target: DatasetSeries[T_DataType]) -> DatasetSeries[T_DataType]` next to `split_by_observation` (~L664). For each `(target_dataset_label, target_dataset)` in `target.parts`:
   - Walk `target._context_index` for entries whose value's `dataset_label` equals `target_dataset_label`. Build `target_label_for: dict[(src_label, src_field), target_element_label]` by calling `source.context_lookup(obs_id, prop_id)` for each. Collision → `ValueError` naming the conflicting target labels.
   - `required_fields_by_dataset` from `target_label_for.keys()`; `source_dataset_labels = sorted(...)`.
   - `base_dataset_label = self._pick_base_dataset_label(...)`.
   - `raw_join_specs, _ = self._resolve_join_specs(source, observation_id=f"<export target dataset {target_dataset_label}>", source_dataset_labels, base_dataset_label, required_fields_by_dataset)` — mutates `required_fields_by_dataset` to add join keys.
   - Build `field_label_mapping`: prefer target labels; synthetic labels via `self._build_unique_label(...)` for join-key fields not in `target_label_for`.
   - `datasets_for_join = self._prepare_datasets_for_join(...)`; if `raw_join_specs`, `joined_data = self.execute_join_plan(...)` with `self._build_adjusted_join_plan(...)`; else `joined_data = base_data`.
   - `final_data = self.subset(joined_data, element_group=sorted(target_label_for.values()))` — drops synthetic join-key columns.
   - `target.parts[target_dataset_label].data = final_data`.
   - Return `target`.

B2. Base-class implementation only; composes existing primitives, so no per-adapter override required.

### Phase C — `Session.export_tabular_dataset_series`
File: `src/pypeh/core/session/session.py`

C1. Add method after `dump_tabular_dataset_series` (~L491):
   ```python
   def export_tabular_dataset_series(
       self,
       source_dataset_series: DatasetSeries[DataFrame],
       data_export_config: peh.DataExportConfig,
       output_path: str | None = None,
       file_format: Literal["parquet", "xlsx"] = "xlsx",
       connection_label: str | None = None,
       adapter_label: str = "dataops",
   ) -> list[str]:
   ```
   Body matches the spec's session-flow snippet exactly: `CacheContainerView(self.cache)` → `DatasetSeries.from_peh_data_export_config(...)` (with identifier-provider handling copied from `import_tabular_dataset_series` L322–410) → `adapter = self.get_adapter(adapter_label); assert isinstance(adapter, DataOpsInterface)` → `exported = adapter.extract_from_source(...)` → `return self.dump_tabular_dataset_series(...)`. Default `file_format="xlsx"` per spec.

### Phase D — Dependency verification
D1. Confirm `pyproject.toml` is at `peh-model>=0.6.2,<0.7.0`. If main does not yet have it, bump here. Already correct on main.

### Phase E — Tests
E1. `tests/core/models/test_internal_datalayout.py`: new `DataExportConfig` construction test. Build a minimal cache with a `DataLayout` (two sections) + two `Observation`s with matching `ObservationDesign`s; construct `peh.DataExportConfig(layout=..., section_mapping=peh.DataImportSectionMapping(section_mapping_links=[...]))`; call `DatasetSeries.from_peh_data_export_config(...)`. Assert `parts` keys match section `ui_label`s, each `Dataset.observation_ids` contains the config-supplied IDs (no minted IDs), schema element labels match `DataLayoutElement.label`s, `context_lookup(obs_id, prop_id)` resolves correctly.

E2. `tests/core/interfaces/dataops/test_dataops.py` (~L946): three `extract_from_source` tests near `test_split_by_observation_*`:
   - **Single source + relabel**: one-source-dataset target with renamed element labels. Assert target dataset `.data` columns equal target labels and values match source.
   - **Multi-source join via source FK**: two source datasets joined through a source FK; target requests fields from both. Assert join succeeds and result is subset to target labels (no leftover synthetic join-key columns).
   - **Collision raises**: two target outputs resolving to same `(src_dataset, src_field)` raise `ValueError`; assert message names the conflicting target labels.

E3. New `tests/core/session/test_session_export.py` (or extend `test_session_dataset_parquet.py`): end-to-end `Session.export_tabular_dataset_series`:
   - Reuse the existing `dataset_series` fixture pattern for the source.
   - Build a cache with `DataLayout` + `DataExportConfig`.
   - Call with `file_format="xlsx"` (also test default when arg omitted); assert returned paths exist and workbook has expected sheets/columns.
   - Repeat with `file_format="parquet"`; assert files persist with correct schema metadata.

E4. Re-run PR 1's verification list — no regressions.

### Relevant files (PR 2)
- `src/pypeh/core/models/internal_data_layout.py` — broaden parser type; add `from_peh_data_export_config`.
- `src/pypeh/core/interfaces/dataops.py` — add `extract_from_source` (reuses `_pick_base_dataset_label` L392, `_resolve_join_specs` L408, `_build_unique_label`, `_prepare_datasets_for_join` L468, `_build_adjusted_join_plan` L507, `execute_join_plan` L139, `subset`).
- `src/pypeh/core/session/session.py` — add `export_tabular_dataset_series`.
- `pyproject.toml` — verify (or bump) `peh-model`.
- New/extended tests as listed in Phase E.

### Verification (PR 2)
1. `pytest tests/core/models/test_internal_datalayout.py -k "import_config or export_config"`.
2. `pytest tests/core/interfaces/dataops/test_dataops.py -k "extract_from_source or split_by_observation"`.
3. `pytest tests/core/session/` — end-to-end export + existing dump/read roundtrips.
4. `pytest tests/end_to_end/validation/`.
5. Full suite (`tox` or `pytest`) — green.
6. Manual smoke: REPL run of the spec snippet on a small fixture.

## Decisions
- **Two-PR split**: PR 1 is a zero-behavior-change refactor provable by the existing test suite alone; no new tests required for review/merge.
- **PR 1 keeps the parameter type as `peh.DataImportConfig`** (not yet a union) — pure code motion, no coupling to peh-model 0.6.2.
- **PR 2 broadens to `peh.DataImportConfig | peh.DataExportConfig`** — both classes have the same `layout` + `section_mapping` slots in peh-model 0.6.2 (confirmed via PyPI + linkml schema).
- **Observation IDs preserved** via the import-config code path (`add_observation` with config-supplied IDs), not `from_peh_datalayout` (which mints generic IDs).
- **Per-target-dataset loop in `extract_from_source`** (not per-observation), per spec.
- **Join-key handling**: synthetic labels via `_build_unique_label` for join-key fields not requested by the target; dropped by a final `subset`.
- **Collision policy**: `ValueError` for the first implementation, per spec.
- **Default `file_format="xlsx"`** for export (vs `"parquet"` for `dump_tabular_dataset_series`) — export is the human-facing path.
- **`extract_from_source` on base `DataOpsInterface`** — composes existing primitives; no adapter override.
- **`from_peh_datalayout` untouched** in both PRs.

## Out of Scope (both PRs)
- Modifying `from_peh_datalayout`.
- Supporting the same source field projected to multiple target labels (collision raises).
- New file formats beyond xlsx/parquet.
- URL-sourced exports.
- Re-validation of exported data against the export layout.
- A public `Session.extract_dataset_series(...)` wrapper.

## Further Considerations
1. Exposing `Session.extract_dataset_series(...)` later — defer until a caller asks.
2. Relaxing the collision rule to allow column duplication — defer per spec.
3. Export layouts that omit foreign keys but share identifying observable properties: handled by the existing `identifying` branch in `add_observation`; no special-casing required.

---

## PR 1 implementation status (merged)
- [x] Plan persisted to repo root.
- [x] Refactor applied to `src/pypeh/core/models/internal_data_layout.py` (extracted `from_peh_data_config`, delegated `from_peh_data_import_config`).
- [x] `from_peh_data_config` parameter type broadened to `peh.DataImportConfig | peh.DataExportConfig`.
- [x] `from_peh_data_export_config` stub added (raises `NotImplementedError`).
- [x] Parity test added in `tests/core/models/test_internal_datalayout.py`.
- [x] `make test-all` verified green.
- [x] Committed as `ab721c1` ("add from peh_data_config class method").

## PR 2 implementation status (ready for review, not committed)
- [x] Phase D — `pyproject.toml` floor bumped to `peh-model>=0.6.2,<0.7.0`.
- [x] Phase A — `DatasetSeries.from_peh_data_export_config` no longer raises; delegates to `from_peh_data_config`.
- [x] Phase B — `DataOpsInterface.extract_from_source(source, target)` added on the base class. Reuses `_pick_base_dataset_label`, `_resolve_join_specs`, `_build_unique_label`, `_prepare_datasets_for_join`, `_build_adjusted_join_plan`, `execute_join_plan`, `subset`. Raises `ValueError` when two target outputs in the same dataset resolve to the same source field with different target labels.
- [x] Phase C — `Session.export_tabular_dataset_series(...)` added with default `file_format="xlsx"`; body mirrors the spec's session-flow snippet exactly and reuses identifier-provider handling from `import_tabular_dataset_series`.
- [x] E1 — `test_from_peh_data_export_config_construction` added in `tests/core/models/test_internal_datalayout.py`; verifies dataset labels, observation IDs preserved, schema labels, and context lookup.
- [x] E2 — three `extract_from_source` tests added in `tests/core/interfaces/dataops/test_dataops.py` inside `TestDatasetSeriesMods` (runs via `TestDataFrameDataOps`): single source + relabel, multi-source join via source FK, collision raises `ValueError`.
- [x] E3 — `tests/core/session/test_session_export.py` created with three end-to-end tests: xlsx default, xlsx explicit, parquet roundtrip.
- [x] `make test-all` green — 339 passed, 4 skipped, 0 failed (up from 332).
- [ ] User review + commit.
