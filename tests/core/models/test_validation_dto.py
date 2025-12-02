import pytest

from pypeh.adapters.outbound.persistence.hosts import DirectoryIO
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

    def test_config(self, get_cache):
        cache_view = get_cache
        observation_list = list(cache_view.get_all("Observation"))
        observation_design_list = [getattr(observation, "observation_design", None) for observation in observation_list]
        if len([od for od in observation_design_list if od is not None]) == 0:
            raise AttributeError
        observable_properties = list(cache_view.get_all("ObservableProperty"))

        # code below is copied from validationservice: IMPROVE
        found = False
        for observation in observation_list:
            validation_config = ValidationConfig.from_observation(
                observation,
                observable_properties,
                cache_view=cache_view,
            )
            for column_dict in validation_config.columns:
                if column_dict.unique_name == "peh:adults_u_sg":
                    found = True

        assert found

    def test_config_from_dataset(self, get_cache):
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

        for dataset_label, dataset in dataset_series.parts.items():
            config = ValidationConfig.from_dataset(
                dataset=dataset,
                cache_view=cache_view,
            )
            assert isinstance(config, ValidationConfig)
