from __future__ import annotations

import os
import importlib
import logging
import peh_model.peh as peh

from typing import (
    Any,
    TYPE_CHECKING,
    TypeVar,
    Sequence,
    Generic,
    Generator,
    Literal,
)

from pypeh.core.cache.containers import (
    CacheContainer,
    CacheContainerFactory,
    CacheContainerView,
)
from pypeh.core.models.proxy import TypedLazyProxy
from pypeh.core.models.settings import (
    LocalFileConfig,
    ImportConfig,
    ConnectionConfig,
    ValidatedImportConfig,
    DEFAULT_CONNECTION_LABEL,
)
from pypeh.core.models.typing import T_NamedThingLike, T_DataType
from pypeh.core.models.validation_dto import ValidationConfig
from pypeh.core.models.validation_errors import (
    DatasetSchemaError,
    ValidationErrorReport,
    ValidationErrorReportCollection,
    build_schema_error_report,
)
from pypeh.core.models.dataset_series_mapping import (
    DatasetSeriesAlignment,
    DatasetSeriesConcatenationPlan,
    ObservationAlignment,
)
from pypeh.core.models.internal_data_layout import DatasetSeries, Dataset
from pypeh.core.interfaces.dataops import (
    AggregationInterface,
    DataOpsInterface,
    DataEnrichmentInterface,
    DataExtractInterface,
    LabelCollisionStrategy,
    ValidationInterface,
)
from pypeh.adapters.persistence.dataset_parquet import (
    dump_dataset_series_to_parquet_filesystem,
    load_dataset_series_from_parquet_filesystem,
)
from pypeh.adapters.persistence.dataset_excel import (
    dump_dataset_series_to_excel_filesystem,
)
from pypeh.core.session.connections import ConnectionManager
from pypeh.core.utils.namespaces import NamespaceManager
from pypeh.core.utils.resolve_identifiers import is_url

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from polars import DataFrame
    from pydantic_settings import BaseSettings
    from typing import Sequence

T_AdapterType = TypeVar("T_AdapterType")


class Session(Generic[T_AdapterType, T_DataType]):
    _adapter_mapping: dict[str, T_AdapterType] = dict()

    def __init__(
        self,
        *,
        connection_config: ConnectionConfig
        | Sequence[ConnectionConfig]
        | None = None,
        default_connection: str | ConnectionConfig | None = None,
        env_file: str | None = None,
        load_from_default_connection: str | None = None,
    ):
        """
        Initializes a new pypeh Session.

        Args:
            connection_config (ConnectionConfig | Sequence[ConnectionConfig] | None):
                A (list of) ConnectionConfig instance(s). Allows you to setup connection to local
                or remote repositories.
                Required if a string-based default_connection is used.
            default_connection (str | ConnectionConfig | None):
                Specifies the default storage for the session. Can either be:
                    - A string key referring to a connection in connection_config,
                    - A ConnectionConfig instance to directly generate BaseSettings.
            load_from_default_connection: (str | None = None):
                Optional. Source to load from default connection on init.
        """
        connection_map, default_connection = self._normalize_configs(
            connection_config, default_connection
        )
        self.connection_manager: ConnectionManager = ConnectionManager(
            ValidatedImportConfig()
        )
        validated_default_connection: BaseSettings | None = (
            self._init_default_connection(default_connection, env_file)
        )
        if connection_map is not None:
            import_config = ImportConfig(
                connection_map=connection_map
            ).to_validated_import_config(_env_file=env_file)
            self.connection_manager = ConnectionManager(import_config)

        if validated_default_connection is not None:
            self.connection_manager._register_connection_label(
                DEFAULT_CONNECTION_LABEL, validated_default_connection
            )
        self.cache: CacheContainer = CacheContainerFactory.new()
        if load_from_default_connection is not None:
            _ = self.load_persisted_cache(source=load_from_default_connection)
        self.namespace_manager: NamespaceManager | None = None

    def _normalize_configs(
        self,
        connection_config,
        default_connection,
    ) -> tuple[dict[str, ConnectionConfig], ConnectionConfig | None]:
        """Validates and normalizes configs before init proceeds."""
        connection_map = {}
        # Handle missing connection_config
        if connection_config is None:
            if default_connection is None:
                default_connection = self._env_default_connection()
            elif isinstance(default_connection, str):
                raise ValueError(
                    "String value for default_connection requires a connection_config"
                )
            elif not isinstance(default_connection, ConnectionConfig):
                logger.debug(
                    "All resources will be loaded as linked open data"
                )
        else:
            if isinstance(connection_config, ConnectionConfig):
                connection_map = {connection_config.label: connection_config}
            elif isinstance(connection_config, Sequence):
                for config in connection_config:
                    if not isinstance(config, ConnectionConfig):
                        raise ValueError(
                            "connection_config argument is of wrong type"
                        )
                    connection_map[config.label] = config
            else:
                raise ValueError("connection_config argument is of wrong type")

        # Validate string cache references
        validated_default_connection = None
        if isinstance(default_connection, str):
            if default_connection not in connection_map:
                raise ValueError(
                    "Default connection string must refer to a key in connection_config"
                )
            validated_default_connection = connection_map[default_connection]
        elif isinstance(default_connection, ConnectionConfig):
            if default_connection.namespaces is not None:
                logger.warning(
                    "default_connection has namespaces associated to it. These are ignored."
                    " Use the connection_config to achieve this"
                )
            validated_default_connection = default_connection

        return connection_map, validated_default_connection

    def _env_default_connection(self) -> ConnectionConfig | None:
        """Derives a default cache config from environment variables."""
        if (
            os.environ.get("DEFAULT_PERSISTED_CACHE_TYPE", "").upper()
            == "LOCALFILE"
        ):
            return LocalFileConfig(env_prefix="DEFAULT_PERSISTED_CACHE_")

    def _init_default_connection(
        self,
        default_connection: ConnectionConfig | None,
        env_file: str | None,
    ) -> BaseSettings | None:
        """Creates the BaseSettings instance for the default cache."""
        if isinstance(default_connection, ConnectionConfig):
            return default_connection.make_settings(_env_file=env_file)
        return None

    def _new_identifier_provider(self):
        if self.namespace_manager is None:
            return None
        return self.namespace_manager.get_identifier_provider(
            suffix_strategy=NamespaceManager.generate_ulid()
        )

    def _build_series_from_data_config(
        self,
        data_config: peh.DataImportConfig | peh.DataExportConfig,
    ) -> DatasetSeries:
        assert isinstance(
            data_config, (peh.DataImportConfig, peh.DataExportConfig)
        )
        return DatasetSeries.from_peh_data_config(
            data_config=data_config,
            cache_view=CacheContainerView(self.cache),
            identifier_provider=self._new_identifier_provider(),
        )

    def register_default_adapter(self, interface_functionality: str):
        adapter = None
        match interface_functionality:
            case "validation":
                adapter = ValidationInterface.get_default_adapter_class()
                self._adapter_mapping[interface_functionality] = adapter
            case "dataops":
                adapter = DataOpsInterface.get_default_adapter_class()
                self._adapter_mapping[interface_functionality] = adapter
            case "enrichment":
                adapter = DataEnrichmentInterface.get_default_adapter_class()
                self._adapter_mapping[interface_functionality] = adapter
            case "extract":
                adapter = DataExtractInterface.get_default_adapter_class()
                self._adapter_mapping[interface_functionality] = adapter
            case "aggregation":
                adapter = AggregationInterface.get_default_adapter_class()
                self._adapter_mapping[interface_functionality] = adapter
            case _:
                raise NotImplementedError(
                    "Session.register_default_adapter does not support "
                    f"interface_functionality={interface_functionality!r}."
                )

        return adapter

    def register_adapter(
        self, interface_functionality: str, adapter: T_AdapterType
    ):
        self._adapter_mapping[interface_functionality] = adapter

    def register_adapter_by_name(
        self,
        interface_functionality: str,
        adapter_module_name: str,
        adapter_class_name: str,
    ):
        try:
            adapter_module = importlib.import_module(adapter_module_name)
            adapter = getattr(adapter_module, adapter_class_name)
        except Exception as e:
            logger.error(
                f"Exception encountered while attempting to import the requested {interface_functionality} adapter: {adapter_module_name} - {adapter_class_name}"
            )
            raise e
        self.register_adapter(interface_functionality, adapter)

    def get_adapter(self, interface_functionality: str):
        adapter = self._adapter_mapping.get(interface_functionality)
        if adapter is None:
            adapter = self.register_default_adapter(interface_functionality)
        assert adapter is not None

        if isinstance(adapter, type):
            return adapter()
        else:
            return adapter

    def _source_to_cache(self, roots: list | peh.EntityList) -> bool:
        if isinstance(roots, list):
            for root in roots:
                ret = self.cache.unpack_entity_list(root)
                assert ret
        else:
            ret = self.cache.unpack_entity_list(roots)

        return True

    def load_persisted_cache(
        self, source: str | None = None, connection_label: str | None = None
    ):
        """Load all resources from either the default cache persistence location or from the provided
        connection into cache. The provided connection_label takes precedence over the default.
        Currently all resources should still be represented as yaml files.
        """
        # get host/connection
        # TODO: fix host calls with unified ConnectionManager
        if connection_label is None:
            logger.info(
                "Using DEFAULT_CONNECTION_LABEL in absence of connection_label"
            )
            connection_label = DEFAULT_CONNECTION_LABEL

        if source is None:
            # TEMP FIX: will only work with filesystems
            source = ""

        with self.connection_manager.get_connection(
            connection_label=connection_label
        ) as connection:
            roots = connection.load(source, format="yaml")

        ret = self._source_to_cache(roots)
        assert ret

    def dump_cache(
        self,
        output_path: str,
        file_format: str = "yaml",
        connection_label: str | None = None,
        cache: CacheContainer | CacheContainerView | None = None,
    ):
        supported_dump_formats = {
            "ttl",
            "turtle",
            "trig",
            "yaml",
        }  # TEMPORARY FIX
        assert (
            file_format in supported_dump_formats
        ), f"Format {file_format} currently not supported for `Session.dump_cache`"

        if cache is None:
            to_serialize = self.cache
        else:
            to_serialize = cache

        if isinstance(to_serialize, CacheContainer):
            pass
        elif isinstance(to_serialize, CacheContainerView):
            to_serialize = to_serialize._container
        else:
            raise ValueError("cache argument does not match expected type")

        if connection_label is None:
            logger.info(
                "Using DEFAULT_CONNECTION_LABEL in absence of connection_label"
            )
            connection_label = DEFAULT_CONNECTION_LABEL

        root = to_serialize.pack_entity_list()
        with self.connection_manager.get_connection(
            connection_label=connection_label
        ) as connection:
            _ = connection.dump(
                root, destination=output_path, format=file_format
            )

    def import_tabular_dataset_series(
        self,
        source: str,
        data_import_config: peh.DataImportConfig,
        file_format: str | None = None,
        connection_label: str | None = None,
        allow_incomplete: bool = False,
        cast_error_policy: Literal["null", "raise", "report"] = "raise",
        schema_error_policy: Literal["raise", "report"] = "raise",
        adapter_label: str = "dataops",
    ) -> DatasetSeries[DataFrame] | ValidationErrorReportCollection:
        dataset_series = self._build_series_from_data_config(
            data_import_config
        )
        data_schema = dataset_series.get_type_annotations()

        # Add data to DatasetSeries
        # TODO: fix host calls with unified ConnectionManager
        if is_url(source):
            raise NotImplementedError(
                "Session.import_tabular_dataset_series does not support URL "
                f"sources yet. source={source!r}, file_format={file_format!r}."
            )
        elif connection_label is not None:
            pass
        else:
            connection_label = DEFAULT_CONNECTION_LABEL

        with self.connection_manager.get_connection(
            connection_label=connection_label
        ) as connection:
            data_dict = connection.load(
                source,
                format=file_format,
                data_schema=data_schema,
                cast_error_policy=cast_error_policy,
            )

        assert isinstance(data_dict, dict)
        # IF cast_error_policy == "report" THEN cast_error_reports might not be empty
        cast_error_reports = ValidationErrorReportCollection(
            {
                dataset_label: raw_result
                for dataset_label, raw_result in data_dict.items()
                if isinstance(raw_result, ValidationErrorReport)
            }
        )
        if cast_error_reports:
            return cast_error_reports

        import_adapter = self.get_adapter(adapter_label)
        schema_error_reports = ValidationErrorReportCollection()
        for raw_dataset_label, raw_dataset in data_dict.items():
            assert isinstance(import_adapter, DataOpsInterface)
            data_labels = import_adapter.get_element_labels(raw_dataset)
            try:
                result = dataset_series.add_data(
                    dataset_label=raw_dataset_label,
                    data=raw_dataset,
                    data_labels=data_labels,
                    allow_incomplete=allow_incomplete,
                )
            except DatasetSchemaError as exc:
                if schema_error_policy != "report":
                    raise
                schema_error_reports[raw_dataset_label] = (
                    build_schema_error_report(
                        exc,
                        source="Session.import_tabular_dataset_series",
                    )
                )
                continue
            if result is not None:
                raise RuntimeError(f"{result.type}: {result.message}")

        if schema_error_reports:
            return schema_error_reports

        return dataset_series

    def load_tabular_dataset_series(
        self,
        source: str,
        data_import_config: peh.DataImportConfig,
        file_format: str | None = None,
        connection_label: str | None = None,
        allow_incomplete: bool = False,
        cast_error_policy: Literal["null", "raise", "report"] = "raise",
        schema_error_policy: Literal["raise", "report"] = "raise",
    ) -> DatasetSeries[DataFrame] | ValidationErrorReportCollection:
        logger.warning(
            "load_tabular_dataset_series will be deprecated in favor of import_tabular_dataset_series"
        )
        return self.import_tabular_dataset_series(
            source=source,
            data_import_config=data_import_config,
            file_format=file_format,
            connection_label=connection_label,
            allow_incomplete=allow_incomplete,
            cast_error_policy=cast_error_policy,
            schema_error_policy=schema_error_policy,
        )

    @staticmethod
    def _connection_path(connection, path: str) -> str:
        normalize_path = getattr(connection, "_normalize_path", None)
        if normalize_path is not None:
            return normalize_path(path)
        return path

    @staticmethod
    def _connection_file_system(connection) -> Any:
        file_system = getattr(connection, "file_system", None)
        if file_system is None:
            raise NotImplementedError(
                "DatasetSeries tabular persistence requires a filesystem-backed "
                "connection."
            )
        return file_system

    def dump_tabular_dataset_series(
        self,
        dataset_series: DatasetSeries[DataFrame],
        output_path: str | None = None,
        file_format: Literal["parquet", "xlsx"] = "parquet",
        connection_label: str | None = None,
    ) -> list[str]:
        """
        Dump a tabular DatasetSeries to a supported dataframe export format.

        Parquet is a pypeh semantic persistence format, written as one file per
        Dataset. XLSX is an export-only format, written as one workbook with one
        worksheet per Dataset.
        If output_path is omitted, files are written to the connection root.
        """
        if file_format not in {"parquet", "xlsx"}:
            raise NotImplementedError(
                "Session.dump_tabular_dataset_series currently supports "
                f"file_format='parquet' or 'xlsx'. Got {file_format!r}."
            )
        if output_path is None:
            output_path = "./"

        if connection_label is None:
            connection_label = DEFAULT_CONNECTION_LABEL

        with self.connection_manager.get_connection(
            connection_label=connection_label
        ) as connection:
            destination = self._connection_path(connection, output_path)
            file_system = self._connection_file_system(connection)
            if file_format == "xlsx":
                return dump_dataset_series_to_excel_filesystem(
                    dataset_series,
                    file_system,
                    destination,
                )
            return dump_dataset_series_to_parquet_filesystem(
                dataset_series,
                file_system,
                destination,
            )

    def export_tabular_dataset_series(
        self,
        source_dataset_series: DatasetSeries[DataFrame],
        data_export_config: peh.DataExportConfig,
        adapter_label: str = "dataops",
    ) -> DatasetSeries[DataFrame]:
        """
        Reshape a DatasetSeries according to a peh.DataExportConfig and return
        the reshaped DatasetSeries.

        The DataLayout referenced by data_export_config defines the requested
        export shape: section_mapping_links bind layout sections to source
        Observations, and the dataops adapter then projects/joins the source
        DatasetSeries into the requested datasets.
        """
        target = self._build_series_from_data_config(data_export_config)

        adapter = self.get_adapter(adapter_label)
        assert isinstance(adapter, DataOpsInterface)

        exported = adapter.extract_from_source(
            source=source_dataset_series,
            target=target,
        )

        return exported

    def _resolve_observation_groups(
        self,
        alignment_plan: ObservationAlignment,
    ) -> tuple[peh.ObservationGroup, ...]:
        """
        Resolve the ObservationGroups referenced by id in `alignment_plan`
        (via `ObservationAssembly.source_observation_groups`) from the session
        cache, the same way `data_export_config` resources are resolved from
        cache by id.
        """
        resolved: dict[str, peh.ObservationGroup] = {}
        if observation_assemblies := alignment_plan.observation_assemblies:
            if isinstance(observation_assemblies, peh.ObservationAssembly):
                observation_assemblies = [observation_assemblies]
        else:
            return ()

        for assembly in observation_assemblies:
            if observation_groups := assembly.source_observation_groups:
                if isinstance(observation_groups, str):
                    observation_groups = (observation_groups,)

                for group_id in observation_groups:
                    group_id = str(group_id)
                    if group_id in resolved:
                        continue
                    cached = self.cache.get(group_id, "ObservationGroup")
                    if cached is not None:
                        assert isinstance(cached, peh.ObservationGroup)
                        resolved[group_id] = cached

        return tuple(resolved.values())

    def concatenate_tabular_dataset_series(
        self,
        dataset_series: Sequence[DatasetSeries[DataFrame]],
        *,
        output_label: str | None = None,
        alignment_plan: ObservationAlignment | None = None,
        adapter_label: str = "dataops",
    ) -> DatasetSeries[DataFrame]:
        """
        Concatenate already-tabular DatasetSeries.

        Without an explicit alignment, every input series must contain the same
        dataset labels and the same observable property ids within each paired
        Dataset. With an alignment plan, source Observations and
        ObservableProperties can be assembled into target Observations.

        ObservationGroups referenced by id in `alignment_plan` are resolved
        from the session cache automatically; register any referenced
        ObservationGroup in the cache (`session.cache.add(...)`) before calling.
        """
        adapter = self.get_adapter(adapter_label)
        assert isinstance(adapter, DataOpsInterface)
        if alignment_plan is None:
            plan = DatasetSeriesConcatenationPlan.from_strict_dataset_series(
                dataset_series,
                output_label=output_label,
            )
        else:
            plan = DatasetSeriesConcatenationPlan.from_alignment(
                dataset_series=dataset_series,
                alignment=DatasetSeriesAlignment(
                    alignment_plan=alignment_plan,
                    observation_groups=self._resolve_observation_groups(
                        alignment_plan
                    ),
                    output_label=output_label,
                ),
            )
        return adapter.concatenate_dataset_series(
            dataset_series=dataset_series,
            plan=plan,
        )

    def create_tabular_extract(
        self,
        dataset_series: Sequence[DatasetSeries[DataFrame]],
        data_export_config: peh.DataExportConfig,
        *,
        alignment_plan: ObservationAlignment | None = None,
        output_label: str | None = None,
        adapter_label: str = "extract",
    ) -> DatasetSeries[DataFrame]:
        """
        Build a single tabular extract from a sequence of source DatasetSeries.

        For each source series in `dataset_series`, this reshapes it according
        to `data_export_config` and then applies each resulting section's
        `data_filter` (falling back to that same source series for filter
        dependencies that reshaping projected away). The per-source extracts
        are then concatenated into a single DatasetSeries.
        """
        adapter = self.get_adapter(adapter_label)
        assert isinstance(adapter, DataExtractInterface)
        cache_view = CacheContainerView(self.cache)

        per_source_extracts: list[DatasetSeries[DataFrame]] = []
        for source in dataset_series:
            reshaped = self.export_tabular_dataset_series(
                source,
                data_export_config,
                adapter_label=adapter_label,
            )
            for dataset_label, dataset in list(reshaped.parts.items()):
                section_id = dataset.described_by
                if section_id is None:
                    continue
                layout_section = cache_view.require(
                    section_id, "DataLayoutSection"
                )
                assert isinstance(layout_section, peh.DataLayoutSection)
                data_filter = layout_section.data_filter
                if data_filter is None:
                    continue
                assert isinstance(data_filter, peh.DataFilter)
                reshaped = adapter.apply_filter(
                    reshaped,
                    data_filter.filter_expression,
                    dataset_label,
                    source_dataset_series=source,
                )
            per_source_extracts.append(reshaped)

        if len(per_source_extracts) == 1:
            extract = per_source_extracts[0]
            if output_label is not None:
                extract.label = output_label
            return extract

        concatenated = self.concatenate_tabular_dataset_series(
            per_source_extracts,
            output_label=output_label,
            alignment_plan=alignment_plan,
            adapter_label=adapter_label,
        )
        return self._propagate_described_by(
            concatenated, per_source_extracts[0]
        )

    @staticmethod
    def _propagate_described_by(
        concatenated: DatasetSeries[DataFrame],
        reference: DatasetSeries[DataFrame],
    ) -> DatasetSeries[DataFrame]:
        """
        Copy `described_by` provenance (the originating DataLayout/
        DataLayoutSection ids) from a per-source reshaped extract onto the
        concatenated result.

        `concatenate_dataset_series` builds a brand new DatasetSeries and new
        Datasets that only carry `source_dataset_series`/`source_datasets`
        metadata, not `described_by`. Without this, downstream validation
        config lookups (`ValidationInterface.collect_column_validations`,
        `build_dataset_level_validations`) silently skip the configured
        `DataLayoutSection` rules because `dataset.described_by` is None,
        making `create_tabular_extract` behave inconsistently depending on
        whether one or several source series were concatenated. All
        per-source extracts share the same `data_export_config`, so their
        `described_by` ids apply unchanged to the concatenated series/datasets.
        """
        if (
            concatenated.described_by is None
            and reference.described_by is not None
        ):
            concatenated.add_metadata("described_by", reference.described_by)
        for dataset_label, dataset in concatenated.parts.items():
            if dataset.described_by is not None:
                continue
            reference_dataset = reference[dataset_label]
            if reference_dataset is None:
                continue
            section_id = reference_dataset.described_by
            if section_id is not None:
                dataset.add_metadata("described_by", section_id)
        return concatenated

    def read_tabular_dataset_series(
        self,
        source_paths: Sequence[str],
        file_format: Literal["parquet"] = "parquet",
        connection_label: str | None = None,
        validate_foreign_keys: bool = True,
    ) -> DatasetSeries[DataFrame]:
        """
        Read a persisted DatasetSeries from files previously written by pypeh.
        """
        if file_format != "parquet":
            raise NotImplementedError(
                "Session.read_tabular_dataset_series currently only supports "
                f"file_format='parquet'. Got {file_format!r}."
            )

        if isinstance(source_paths, str):
            raise TypeError(
                "Session.read_tabular_dataset_series expects source_paths to "
                "be a sequence of parquet file paths, not a single path."
            )

        if connection_label is None:
            connection_label = DEFAULT_CONNECTION_LABEL

        with self.connection_manager.get_connection(
            connection_label=connection_label
        ) as connection:
            normalized_source_paths: list[str] = [
                self._connection_path(connection, source_path)
                for source_path in source_paths
            ]
            file_system = self._connection_file_system(connection)
            return load_dataset_series_from_parquet_filesystem(
                file_system,
                normalized_source_paths,
                validate_foreign_keys=validate_foreign_keys,
            )

    def get_resource(
        self, resource_identifier: str, resource_type: str
    ) -> T_NamedThingLike | None:
        """Get resource from cache"""
        ret = self.cache.get(resource_identifier, resource_type)
        if ret is None:
            logger.debug(
                f"No resource found with identifier {resource_identifier}"
            )

        return ret

    def resolve_typed_lazy_proxy(
        self, proxy: TypedLazyProxy
    ) -> peh.NamedThing:
        raise NotImplementedError(
            "Session.resolve_typed_lazy_proxy is not implemented yet. "
            f"proxy={proxy!r}."
        )

    def load_resource(
        self,
        resource_identifier: str,
        resource_type: str,
        resource_path: str | None = None,
        connection_label: str | None = None,
    ) -> T_NamedThingLike | None:
        """Load resource into cache. First checks the cache,
        then configured persisted cache, and finally the `ImportConfig`"""
        # cache
        ret = self.get_resource(resource_identifier, resource_type)
        if ret is not None:
            return ret

        if connection_label is not None:
            with self.connection_manager.get_connection(
                connection_label=connection_label
            ) as connection:
                # assuming connection points to a file-based system
                # loading entire directory
                logger.debug(
                    f"Loading .yaml files recursively from {connection_label} root directory"
                )
                if resource_path is None:
                    resource_path = ""
                    roots = connection.load(resource_path, format="yaml")
                else:
                    roots = connection.load(resource_path)
                ret = self._source_to_cache(roots)
                assert ret

            # resource should have been loaded into cache
            ret = self.cache.require(resource_identifier, resource_type)
            type_to_cast = getattr(peh, resource_type)
            assert isinstance(ret, type_to_cast)
        else:
            # TODO: use linked data approach
            raise NotImplementedError(
                "Session.load_resource without connection_label is not "
                "implemented yet (linked data fallback). "
                f"resource_identifier={resource_identifier!r}, "
                f"resource_type={resource_type!r}."
            )

        return ret

    def dump_resource(
        self, resource_identifier: str, resource_type: str, version: str | None
    ) -> bool:
        return True

    def validate_tabular_dataset(
        self,
        data: Dataset[DataFrame],
        dependent_data: DatasetSeries[DataFrame] | None = None,
        allow_incomplete: bool = False,
        adapter_label: str = "validation",
    ) -> ValidationErrorReport:
        assert data.data is not None, f"No data associated with {data.label}"
        cache_view = CacheContainerView(self.cache)
        validation_adapter = self.get_adapter(adapter_label)
        assert isinstance(validation_adapter, ValidationInterface)
        return validation_adapter.validate(
            dataset=data,
            dependent_dataset_series=dependent_data,
            cache_view=cache_view,
            allow_incomplete=allow_incomplete,
        )

    def validate_tabular_dataset_series(
        self,
        dataset_series: DatasetSeries[DataFrame],
        allow_incomplete: bool = False,
    ) -> ValidationErrorReportCollection:
        validation_result_dict = ValidationErrorReportCollection()
        for dataset_label in dataset_series:
            dataset = dataset_series[dataset_label]
            assert dataset is not None
            if dataset.data is None:
                continue
            validation_result = self.validate_tabular_dataset(
                data=dataset,
                dependent_data=dataset_series,
                allow_incomplete=allow_incomplete,
            )
            assert isinstance(
                validation_result, ValidationErrorReport
            ), "validation_result in `Session.validate_tabular_dataset_series` should be a`ValidationErrorReport`"
            validation_result_dict[dataset_label] = validation_result

        # Catch no data in dataset_series case
        assert (
            len(validation_result_dict) > 0
        ), f"DatasetSeries with label {dataset_series.label} contains no data"

        return validation_result_dict

    def build_validation_config(
        self,
        data_layout: peh.DataLayout,
        sections_to_validate: list[str] | None = None,
        allow_incomplete: bool = False,
    ) -> dict[str, ValidationConfig]:
        ret: dict[str, ValidationConfig] = {}
        cache_view = CacheContainerView(self.cache)
        dataset_series = DatasetSeries.from_peh_datalayout(
            data_layout=data_layout,
            cache_view=cache_view,
            apply_context=False,
        )
        validation_interface = ValidationInterface()

        iterator = dataset_series
        if sections_to_validate is not None:
            iterator = sections_to_validate

        for dataset_label in iterator:
            dataset = dataset_series[dataset_label]
            assert dataset is not None
            config = validation_interface.build_validation_config(
                dataset=dataset,
                dataset_series=dataset_series,
                cache_view=cache_view,
                allow_incomplete=allow_incomplete,
            )
            ret[dataset_label] = config

        return ret

    def unpack_derived_observation_group(
        self,
        observation_group_id: str,
    ) -> Generator[tuple[peh.DerivedObservation, peh.Observation], None, None]:
        observation_group = self.cache.require(
            observation_group_id, "ObservationGroup"
        )
        assert isinstance(observation_group, peh.ObservationGroup)
        assert observation_group.observation_id_list is not None
        for observation_id in observation_group.observation_id_list:
            target_observation = self.cache.get(
                observation_id, "DerivedObservation"
            )
            if isinstance(target_observation, peh.DerivedObservation):
                source_observation_id = target_observation.was_derived_from
                assert isinstance(source_observation_id, str)
                source_observation = self.cache.require(
                    source_observation_id, "Observation"
                )
                assert isinstance(source_observation, peh.Observation)

                yield (target_observation, source_observation)

    def split_dataset_series_by_observation(
        self,
        source_dataset_series: DatasetSeries[T_DataType],
        new_dataset_series_label: str | None = None,
        label_collision_strategy: LabelCollisionStrategy = (
            "prefix_source_dataset"
        ),
        adapter_label: str = "dataops",
    ) -> DatasetSeries[T_DataType]:
        """Split a DatasetSeries into observation-specific datasets."""
        adapter = self.get_adapter(adapter_label)
        cache_view = CacheContainerView(self.cache)
        assert isinstance(adapter, DataOpsInterface)
        ret = adapter.split_by_observation(
            dataset_series=source_dataset_series,
            new_label=new_dataset_series_label,
            cache_view=cache_view,
            label_collision_strategy=label_collision_strategy,
        )
        assert isinstance(ret, DatasetSeries)
        return ret

    def enrich(
        self,
        source_dataset_series: DatasetSeries,
        target_observations: list[peh.Observation],
        target_derived_from: list[peh.Observation],
        target_dataset_labels: list[str] | None = None,
        target_label_collision_strategy: LabelCollisionStrategy = "error",
        adapter_label: str = "enrichment",
    ) -> DatasetSeries:
        """
        target_label_collision_strategy is used for the eventuality of having two new observable properties
        that are labeled with the same short_name and ui_label.
        """
        num_targets = len(target_observations)
        assert num_targets == len(target_derived_from)
        if target_dataset_labels is not None:
            assert num_targets == len(target_dataset_labels)

        adapter = self.get_adapter(adapter_label)
        assert isinstance(adapter, DataEnrichmentInterface)
        # TODO: apply target_dataset_labels when splitting
        # DatasetSeries into Observations
        return adapter.enrich(
            source_dataset_series=source_dataset_series,
            target_observations=target_observations,
            target_derived_from=target_derived_from,
            target_label_collision_strategy=target_label_collision_strategy,
            cache_view=CacheContainerView(self.cache),
        )

    def aggregate(
        self,
        source_dataset_series: DatasetSeries,
        target_observations: list[peh.Observation],
        target_derived_from: list[peh.Observation],
        target_dataset_labels: list[str] | None = None,
        target_label_collision_strategy: LabelCollisionStrategy = "error",
        adapter_label: str = "aggregation",
    ) -> DatasetSeries:
        num_targets = len(target_observations)
        assert num_targets == len(target_derived_from)
        if target_dataset_labels is not None:
            assert num_targets == len(target_dataset_labels)

        adapter = self.get_adapter(adapter_label)
        assert isinstance(adapter, AggregationInterface)
        # TODO: apply target_dataset_labels when splitting
        # DatasetSeries into Observations
        return adapter.summarize(
            source_dataset_series=source_dataset_series,
            target_observations=target_observations,
            target_derived_from=target_derived_from,
            target_label_collision_strategy=target_label_collision_strategy,
            cache_view=CacheContainerView(self.cache),
        )

    def bind_namespace_manager(self, namespace_manager: NamespaceManager):
        self.namespace_manager = namespace_manager

    def mint_and_cache(
        self,
        resource_cls: type[T_NamedThingLike],
        namespace_key: str | None = None,
        identifiying_field: str = "id",
        **resource_kwargs,
    ):
        data = dict(resource_kwargs)
        assert (
            self.namespace_manager is not None
        ), "No NameSpaceManager is bound to Session"
        identifier = self.namespace_manager.mint(
            resource_class=resource_cls,
            namespace_key=namespace_key,
            identifying_field=identifiying_field,
        )
        data[identifiying_field] = identifier
        resource = resource_cls(**data)
        assert isinstance(resource, peh.NamedThing)
        self.cache.add(resource)
        return resource
