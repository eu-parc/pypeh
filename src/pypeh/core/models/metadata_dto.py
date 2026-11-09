"""
DTOs for the study-metadata service.

`StudyMetadataConfig` selects which sections of the study-metadata tree
are emitted and how, analogously to what `DataLayout` / `DataLayoutSection`
do for the extract service. It is a plain pypeh-internal config for now;
a future peh_model `MetadataLayout` resource can be mapped onto it via
`StudyMetadataConfig.from_metadata_layout`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(kw_only=True)
class StudyMetadataConfig:
    """
    Configuration for `Session.create_study_metadata`.

    Each `include_*` flag gates one top-level section of the emitted
    metadata tree. Disabled sections are omitted from the tree entirely
    (rather than emitted empty), so consumers can rely on key presence
    meaning "this section was requested".
    """

    include_variable_catalogue: bool = True
    """observations[].observable_properties catalogue section."""

    include_datasets: bool = True
    """datasets section (variables, dtypes, primary keys)."""

    include_provenance: bool = True
    """provenance section (config/layout ids, derivation chain, versions)."""

    exclude_control_variables: bool = True
    """Exclude LOD/LOQ `control` observable properties (assay QC, not
    catalogue variables) from the catalogue and datasets sections."""

    extra_provenance: dict = field(default_factory=dict)
    """Caller-provided provenance fields appended to the provenance
    section (e.g. `source_file`). Keys may not collide with built-in
    provenance fields; a collision raises ValueError. Values must be
    JSON-serializable (finite str / int / float / bool / None /
    list / str-keyed dict); any other type, a non-finite float
    (NaN / Infinity) or a self-referencing container raises
    ValueError naming the offending key."""

    @classmethod
    def from_metadata_layout(cls, layout) -> "StudyMetadataConfig":
        """
        Build a config from a peh_model `MetadataLayout` resource.

        Not implemented yet: `MetadataLayout` does not exist in the
        peh_model schema. Reserved so the DTO can be populated from a
        cached PEH resource once the model supports it (mirrors
        `DatasetSeriesConcatenationPlan.from_alignment`).
        """
        raise NotImplementedError(
            "StudyMetadataConfig.from_metadata_layout is not implemented "
            "yet: the peh_model schema has no `MetadataLayout` resource. "
            f"layout={layout!r}."
        )
