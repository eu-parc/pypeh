import pytest
import peh_model.peh as peh
import logging

from pypeh.core.cache.containers import CacheContainerView
from pypeh.core.interfaces.outbound.dataops import DataEnrichmentInterface
from tests.test_utils.dirutils import get_absolute_path

from pypeh import Session
from pypeh.core.models.internal_data_layout import DatasetSeries


logger = logging.getLogger(__name__)


@pytest.mark.compehndly
class TestDataFrameEnrichment:
    def test_end_to_end_basic(self, monkeypatch):
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_TYPE", "LocalFile")
        monkeypatch.setenv("DEFAULT_PERSISTED_CACHE_ROOT_FOLDER", get_absolute_path("./input/test_04"))

        session = Session()
        session.load_persisted_cache(source="config")

        data_import_config = session.cache.get(
            "peh:IMPORT_CONFIG_CODEBOOK_v2.4_LAYOUT_SAMPLE_METADATA", "DataImportConfig"
        )
        assert isinstance(data_import_config, peh.DataImportConfig)

        excel_path = "test_04_data.xlsx"
        dataset_series = session.load_tabular_dataset_series(
            source=excel_path,
            data_import_config=data_import_config,
            cast_error_policy="null",
        )
        assert isinstance(dataset_series, DatasetSeries)
        cache_view = CacheContainerView(session.cache)

        adapter_cls = DataEnrichmentInterface.get_default_adapter_class()
        adapter = adapter_cls()
        assert isinstance(adapter, DataEnrichmentInterface)
        target_observations = []
        derived_from_observations = []
        for target_id, derived_from_id in [
            ("peh:VALIDATION_TEST_SAMPLE_SAMPLETIMEPOINT_BWB_IMPUTED", "peh:VALIDATION_TEST_SAMPLE_SAMPLETIMEPOINT_BWB")
        ]:
            target = cache_view.get(target_id, "Observation")
            target_observations.append(target)
            derived_from = cache_view.get(derived_from_id, "Observation")
            derived_from_observations.append(derived_from)

        ret = adapter.enrich(
            source_dataset_series=dataset_series,
            target_observations=target_observations,
            target_derived_from=derived_from_observations,
            cache_view=cache_view,
        )
        # this is the original updated dataset_series
        assert isinstance(ret, DatasetSeries)
