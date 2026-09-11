import pytest
import importlib
import re

from pypeh.adapters.persistence.hosts import DirectoryIO
from pypeh.core.interfaces.dataops import (
    DataOpsInterface,
    ValidationInterface,
)
from pypeh.core.cache.containers import (
    CacheContainerFactory,
    CacheContainerView,
)
from pypeh.core.cache.utils import load_entities_from_tree
from pypeh.core.models.constants import ValidationErrorLevel
from pypeh.core.models.internal_data_layout import DatasetSeries
from pypeh.core.models.validation_dto import ValidationConfig

from pypeh.core.models.validation_errors import ValidationErrorReport
from tests.test_utils.dirutils import get_absolute_path


@pytest.mark.end_to_end
class TestBasicValidationConfig:
    @pytest.fixture(scope="function")
    def get_cache(self):
        source = get_absolute_path("input/validation_config")
        container = CacheContainerFactory.new()
        host = DirectoryIO()
        roots = host.load(source, format="yaml")
        for root in roots:
            for entity in load_entities_from_tree(root):
                container.add(entity)
        return CacheContainerView(container)

    def get_adapter(self) -> DataOpsInterface:
        dfops = importlib.import_module(
            "pypeh.adapters.validation.pandera_adapter.validation_adapter"
        )
        return dfops.DataFrameValidationAdapter()  # type: ignore

    def test_config_from_dataset(self, get_cache):
        dataops_adapter_class = ValidationInterface.get_default_adapter_class()
        validation_adapter = dataops_adapter_class()
        cache_view = get_cache
        layout_id = "peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA"
        layout = cache_view.get(layout_id, "DataLayoutLayout")
        all_sections = set()
        for section in layout.sections:
            section_id = section.id
            if section.id is not None:
                all_sections.add(section_id)
        dataset_series = DatasetSeries.from_peh_datalayout(
            layout,
            cache_view=cache_view,
            apply_context=True,
        )
        assert isinstance(dataset_series, DatasetSeries)
        # add fake data

        import polars as pl

        fake_dataset_series = {
            "SAMPLE": pl.DataFrame(
                {
                    "id_sample": ["SMP00123"],
                    "matrix": ["plasma"],
                }
            ),
            "SAMPLETIMEPOINT_BS": pl.DataFrame(
                {
                    "id_sample": [
                        "SMP00123",
                    ],
                    "adults_u_crt": [
                        1.87,
                    ],
                }
            ),
        }
        for dataset_label, fake_dataset in fake_dataset_series.items():
            data_labels = list(fake_dataset.columns)
            dataset_series.add_data(
                dataset_label,
                fake_dataset,
                data_labels=data_labels,
            )

        sample_dataset = dataset_series.parts.get("SAMPLE", None)
        sample_config = validation_adapter.build_validation_config(
            dataset=sample_dataset,
            dataset_series=dataset_series,
            cache_view=cache_view,
            allow_incomplete=True,
        )
        assert isinstance(sample_config, ValidationConfig)
        assert [c.unique_name for c in sample_config.columns] == [
            "id_sample",
            "matrix",
        ]
        assert (
            sample_config.columns[1].validations[0].name == "check_categorical"
        )
        assert (
            sample_config.columns[1].validations[0].expression.command
            == "is_in"
        )

        sample_tp_dataset = dataset_series.parts.get(
            "SAMPLETIMEPOINT_BS", None
        )
        sample_tp_config = validation_adapter.build_validation_config(
            dataset=sample_tp_dataset,
            dataset_series=dataset_series,
            cache_view=cache_view,
        )
        assert isinstance(sample_tp_config, ValidationConfig)
        assert [c.unique_name for c in sample_tp_config.columns] == [
            "id_sample",
            "adults_u_crt",
        ]
        assert sample_tp_config.columns[0].required
        assert not sample_tp_config.columns[0].nullable
        assert len(sample_tp_config.columns[1].validations) == 4
        assert sample_tp_config.columns[1].validations[1].name == "min"
        assert (
            sample_tp_config.columns[1].validations[1].expression.command
            == "is_greater_than_or_equal_to"
        )
        assert sample_tp_config.columns[1].validations[2].name == "max"
        assert (
            sample_tp_config.columns[1].validations[2].expression.command
            == "is_less_than_or_equal_to"
        )
        assert (
            sample_tp_config.columns[1].validations[3].name
            == "check_significant_decimals"
        )
        assert (
            sample_tp_config.columns[1].validations[3].expression.command
            == "decimals_precision"
        )
        assert sample_tp_config.columns[1].validations[
            3
        ].expression.arg_values == [6]

    def test_config_from_dataset_allow_incomplete(self, get_cache):
        dataops_adapter_class = ValidationInterface.get_default_adapter_class()
        validation_adapter = dataops_adapter_class()
        cache_view = get_cache
        layout_id = "peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA"
        layout = cache_view.get(layout_id, "DataLayoutLayout")
        all_sections = set()
        for section in layout.sections:
            section_id = section.id
            if section.id is not None:
                all_sections.add(section_id)
        dataset_series = DatasetSeries.from_peh_datalayout(
            layout,
            cache_view=cache_view,
            apply_context=True,
        )
        assert isinstance(dataset_series, DatasetSeries)
        # add fake data

        import polars as pl

        fake_dataset_series = {
            "SAMPLE": pl.DataFrame(
                {
                    "id_sample": ["SMP00123"],
                    "matrix": ["plasma"],
                }
            ),
            "SAMPLETIMEPOINT_BS": pl.DataFrame(
                {
                    "id_sample": [
                        "SMP00123",
                    ],
                    "adults_u_crt": [
                        1.87,
                    ],
                }
            ),
        }
        for dataset_label, fake_dataset in fake_dataset_series.items():
            data_labels = list(fake_dataset.columns)
            dataset_series.add_data(
                dataset_label,
                fake_dataset,
                data_labels=data_labels,
            )

        sample_tp_dataset = dataset_series.parts.get(
            "SAMPLETIMEPOINT_BS", None
        )
        sample_tp_config = validation_adapter.build_validation_config(
            dataset=sample_tp_dataset,
            dataset_series=dataset_series,
            cache_view=cache_view,
            allow_incomplete=True,
        )
        assert isinstance(sample_tp_config, ValidationConfig)
        assert [c.unique_name for c in sample_tp_config.columns] == [
            "id_sample",
            "adults_u_crt",
        ]
        assert not sample_tp_config.columns[0].required
        assert sample_tp_config.columns[0].nullable

    def test_config_from_dataset_with_empty_column(self, get_cache):
        dataops_adapter_class = ValidationInterface.get_default_adapter_class()
        validation_adapter = dataops_adapter_class()
        cache_view = get_cache
        layout_id = "peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA"
        layout = cache_view.get(layout_id, "DataLayoutLayout")
        all_sections = set()
        for section in layout.sections:
            section_id = section.id
            if section.id is not None:
                all_sections.add(section_id)
        dataset_series = DatasetSeries.from_peh_datalayout(
            layout,
            cache_view=cache_view,
            apply_context=True,
        )
        assert isinstance(dataset_series, DatasetSeries)
        # add fake data

        import polars as pl

        fake_dataset_series = {
            "SAMPLE": pl.DataFrame(
                {
                    "id_sample": ["SMP00123"],
                    "matrix": ["plasma"],
                }
            ),
            "SAMPLETIMEPOINT_BS": pl.DataFrame(
                {
                    "id_sample": [
                        "SMP00123",
                    ],
                    "adults_u_crt": [
                        None,
                    ],
                }
            ),
        }
        for dataset_label, fake_dataset in fake_dataset_series.items():
            data_labels = list(fake_dataset.columns)
            dataset_series.add_data(
                dataset_label,
                fake_dataset,
                data_labels=data_labels,
            )

        sample_tp_dataset = dataset_series["SAMPLETIMEPOINT_BS"]

        allow_incomplete = True
        sample_tp_config_incomplete = (
            validation_adapter.build_validation_config(
                dataset=sample_tp_dataset,
                dataset_series=dataset_series,
                cache_view=cache_view,
                allow_incomplete=allow_incomplete,
            )
        )
        assert isinstance(sample_tp_config_incomplete, ValidationConfig)
        assert [
            c.unique_name for c in sample_tp_config_incomplete.columns
        ] == ["id_sample", "adults_u_crt"]
        ret = validation_adapter.validate(
            dataset=sample_tp_dataset,
            dependent_dataset_series=dataset_series,
            cache_view=cache_view,
            allow_incomplete=allow_incomplete,
        )
        assert isinstance(ret, ValidationErrorReport)
        assert ret.error_counts[ValidationErrorLevel.ERROR] == 0

        allow_incomplete = False
        sample_tp_config_complete = validation_adapter.build_validation_config(
            dataset=sample_tp_dataset,
            dataset_series=dataset_series,
            cache_view=cache_view,
            allow_incomplete=allow_incomplete,
        )
        assert isinstance(sample_tp_config_complete, ValidationConfig)
        assert [c.unique_name for c in sample_tp_config_complete.columns] == [
            "id_sample",
            "adults_u_crt",
        ]

        ret = validation_adapter.validate(
            dataset=sample_tp_dataset,
            dependent_dataset_series=dataset_series,
            cache_view=cache_view,
            allow_incomplete=allow_incomplete,
        )
        assert isinstance(ret, ValidationErrorReport)
        assert ret.error_counts[ValidationErrorLevel.ERROR] == 1

    def test_allow_incomplete_with_mixed_column(self, get_cache):
        dataops_adapter_class = ValidationInterface.get_default_adapter_class()
        validation_adapter = dataops_adapter_class()
        cache_view = get_cache
        layout_id = "peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA"
        layout = cache_view.get(layout_id, "DataLayoutLayout")
        all_sections = set()
        for section in layout.sections:
            section_id = section.id
            if section.id is not None:
                all_sections.add(section_id)
        dataset_series = DatasetSeries.from_peh_datalayout(
            layout,
            cache_view=cache_view,
            apply_context=True,
        )
        assert isinstance(dataset_series, DatasetSeries)
        # add fake data

        import polars as pl

        fake_dataset_series = {
            "SAMPLE": pl.DataFrame(
                {
                    "id_sample": [
                        "SMP00123",
                        "SMP00124",
                    ],
                    "matrix": ["UM", "UM"],
                }
            ),
            "SAMPLETIMEPOINT_BS": pl.DataFrame(
                {
                    "id_sample": [
                        "SMP00123",
                        "SMP00124",
                    ],
                    "adults_u_crt": [
                        None,
                        -1.0,
                    ],
                }
            ),
        }
        for dataset_label, fake_dataset in fake_dataset_series.items():
            data_labels = list(fake_dataset.columns)
            dataset_series.add_data(
                dataset_label,
                fake_dataset,
                data_labels=data_labels,
            )

        sample_tp_dataset = dataset_series["SAMPLETIMEPOINT_BS"]

        allow_incomplete = True
        sample_tp_config_incomplete = (
            validation_adapter.build_validation_config(
                dataset=sample_tp_dataset,
                dataset_series=dataset_series,
                cache_view=cache_view,
                allow_incomplete=allow_incomplete,
            )
        )
        assert isinstance(sample_tp_config_incomplete, ValidationConfig)
        assert [
            c.unique_name for c in sample_tp_config_incomplete.columns
        ] == ["id_sample", "adults_u_crt"]
        assert len(sample_tp_config_incomplete.columns) == 2
        for column in sample_tp_config_incomplete.columns:
            if column.unique_name == "adults_u_crt":
                assert column.validations is not None
                assert len(column.validations) == 4
                assert column.validations[3].name == (
                    "check_significant_decimals"
                )
                assert (
                    column.validations[3].expression.command
                    == "decimals_precision"
                )
        ret = validation_adapter.validate(
            dataset=sample_tp_dataset,
            dependent_dataset_series=dataset_series,
            cache_view=cache_view,
            allow_incomplete=allow_incomplete,
        )
        assert isinstance(ret, ValidationErrorReport)
        # CUSTOM ERROR MESSAGE WAS ADDED
        # CHECK IF EACH VALIDATIONERROR HAS GOT A PROPER MESSAGE
        patterns = [
            r"IF matrix IS\s*\([^)]*\)",
            r"^The column\(s\) under validation",
        ]
        compiled = [re.compile(p) for p in patterns]
        groups = ret.groups
        for group in groups:
            for error in group.errors:
                message = error.message
                assert any(
                    p.search(message) for p in compiled
                ), f"Unexpected error message: {message}"
        assert ret.error_counts[ValidationErrorLevel.ERROR] == 2

    def test_allow_incomplete_reports_invalid_numeric_value(self, get_cache):
        dataops_adapter_class = ValidationInterface.get_default_adapter_class()
        validation_adapter = dataops_adapter_class()
        cache_view = get_cache
        layout_id = "peh:CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA"
        layout = cache_view.get(layout_id, "DataLayoutLayout")
        dataset_series = DatasetSeries.from_peh_datalayout(
            layout,
            cache_view=cache_view,
            apply_context=True,
        )
        assert isinstance(dataset_series, DatasetSeries)

        import polars as pl

        fake_dataset_series = {
            "SAMPLE": pl.DataFrame(
                {
                    "id_sample": [
                        "SMP00123",
                        "SMP00124",
                    ],
                    "matrix": ["UM", "UM"],
                }
            ),
            "SAMPLETIMEPOINT_BS": pl.DataFrame(
                {
                    "id_sample": [
                        "SMP00123",
                        "SMP00124",
                    ],
                    "adults_u_crt": [1.87, "oops"],
                },
                strict=False,
            ),
        }
        for dataset_label, fake_dataset in fake_dataset_series.items():
            data_labels = list(fake_dataset.columns)
            dataset_series.add_data(
                dataset_label,
                fake_dataset,
                data_labels=data_labels,
                allow_incomplete=True,
            )

        sample_tp_dataset = dataset_series["SAMPLETIMEPOINT_BS"]
        ret = validation_adapter.validate(
            dataset=sample_tp_dataset,
            dependent_dataset_series=dataset_series,
            cache_view=cache_view,
            allow_incomplete=True,
        )
        assert isinstance(ret, ValidationErrorReport)
        assert ret.total_errors == 1
        assert ret.error_counts[ValidationErrorLevel.FATAL] == 1
        assert len(ret.groups) == 1
        assert len(ret.groups[0].errors) == 1
        assert "f64" in ret.groups[0].errors[0].message
        assert "oops" in ret.groups[0].errors[0].message
