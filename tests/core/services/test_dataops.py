import pytest

from pypeh.adapters.outbound.persistence.hosts import DirectoryIO
from pypeh.core.cache.containers import CacheContainerFactory
from pypeh.core.cache.utils import load_entities_from_tree
from pypeh.core.interfaces.inbound.dataops import InDataOpsInterface
from pypeh.core.interfaces.outbound.dataops import ValidationInterface

from typing import Sequence

from pypeh.core.models.validation_dto import ValidationConfig
from pypeh.core.models.validation_errors import ValidationErrorReport
from pypeh.core.services.dataops import ValidationService
from tests.test_utils.dirutils import get_absolute_path


class InboundTestAdapter(InDataOpsInterface):
    def validate(self, project_name: str, config_path: str, data_layout: str, data_path: str):
        pass


class OutboundTestAdapter(ValidationInterface):
    def validate(self, data: dict[str, Sequence], config: ValidationConfig) -> ValidationErrorReport:
        return ValidationErrorReport(
            timestamp="test",
            total_errors=0,
        )


@pytest.mark.core
class TestValidationService:
    outbound_adapter: None
    inbound_adapter: None

    @pytest.fixture(scope="class")
    def mockdata(self):
        return {"test": list(range(10))}

    def test_validate_data(self, mockdata):
        service = ValidationService(outbound_adapter=OutboundTestAdapter())
        # populate cache
        source = get_absolute_path("../../input/roundtrip")
        container = CacheContainerFactory.new()
        host = DirectoryIO()
        roots = host.load(source, format="yaml")
        container = service.cache
        for root in roots:
            for entity in load_entities_from_tree(root):
                container.add(entity)
        observation_id = "OBSERVATION_ADULTS_CONSIDERATIONS"
        observable_property_id_list = [
            "adults_id_subject",
            "adults_id_household",
            "adults_con_cst_ipchem",
            "adults_con_parc_300",
        ]
        result_dict = service.validate_data(
            mockdata, observation_id_list=[observation_id], observable_property_id_list=observable_property_id_list
        )
        assert result_dict is not None
