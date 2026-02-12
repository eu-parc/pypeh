import pytest

from pypeh.adapters.outbound.persistence.hosts import DirectoryIO
from pypeh.core.interfaces.outbound.dataops import ValidationInterface
from pypeh.core.cache.containers import CacheContainerFactory, CacheContainerView
from pypeh.core.cache.utils import load_entities_from_tree
from pypeh.core.models.internal_data_layout import DatasetSeries
from pypeh.core.models.validation_dto import ValidationConfig

from tests.test_utils.dirutils import get_absolute_path


@pytest.mark.core
class TestBasicValidationConfig:
    @pytest.fixture(scope="function")
    def get_cache(self):
        source = get_absolute_path("input")
        container = CacheContainerFactory.new()
        host = DirectoryIO()
        roots = host.load(source, format="yaml")
        for root in roots:
            for entity in load_entities_from_tree(root):
                container.add(entity)
        return CacheContainerView(container)

    def test_config_from_dataset(self, get_cache):
        validation_interface = ValidationInterface()
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
        )
        assert isinstance(dataset_series, DatasetSeries)
        # add fake data
        fake_dataset_series = {
            "SAMPLE": {
                "id_sample": [
                    "SMP00123",
                ],
                "matrix": [
                    "plasma",
                ],
            },
            "SAMPLETIMEPOINT_BS": {
                "id_sample": [
                    "SMP00123",
                ],
                "adults_u_crt": [
                    1.87,
                ],
            },
        }
        for dataset_label, fake_dataset in fake_dataset_series.items():
            dataset_series.add_data(dataset_label, fake_dataset, non_empty_dataset_elements=list(fake_dataset.keys()))

        sample_dataset = dataset_series.parts.get("SAMPLE", None)
        sample_config = validation_interface.build_validation_config(
            dataset=sample_dataset,
            dataset_series=dataset_series,
            cache_view=cache_view,
        )
        assert isinstance(sample_config, ValidationConfig)
        assert [c.unique_name for c in sample_config.columns] == ["id_sample", "matrix"]
        assert sample_config.columns[1].validations[0].name == "check_categorical"
        assert sample_config.columns[1].validations[0].expression.command == "is_in"

        sample_tp_dataset = dataset_series.parts.get("SAMPLETIMEPOINT_BS", None)
        sample_tp_config = validation_interface.build_validation_config(
            dataset=sample_tp_dataset,
            dataset_series=dataset_series,
            cache_view=cache_view,
        )
        assert isinstance(sample_tp_config, ValidationConfig)
        assert [c.unique_name for c in sample_tp_config.columns] == ["id_sample", "adults_u_crt"]
        assert sample_tp_config.columns[1].validations[1].name == "min"
        assert sample_tp_config.columns[1].validations[1].expression.command == "is_greater_than_or_equal_to"
        assert sample_tp_config.columns[1].validations[2].name == "max"
        assert sample_tp_config.columns[1].validations[2].expression.command == "is_less_than_or_equal_to"
