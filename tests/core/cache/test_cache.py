import pytest

from peh_model.peh import ObservableProperty, Observation

from pypeh.core.cache.containers import CacheContainerFactory
from pypeh.core.cache.utils import load_entities_from_tree
from pypeh.adapters.outbound.persistence.hosts import DirectoryIO

from tests.test_utils.dirutils import get_absolute_path


@pytest.mark.core
class TestRootStream:
    # TODO: extent test if more CacheContainer implementations become available
    def test_filter_cache(self):
        source = get_absolute_path("../../input/roundtrip")
        container = CacheContainerFactory.new()
        host = DirectoryIO()
        roots = host.load(source, format="yaml")
        for root in roots:
            for entity in load_entities_from_tree(root):
                container.add(entity)

        assert all(isinstance(i, (ObservableProperty, Observation)) for i in container.get_all())

        filter = list(container.get_all(entity_type="Observation"))
        assert len(filter) > 1
