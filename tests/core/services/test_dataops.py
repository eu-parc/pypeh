import pytest

from pypeh.core.interfaces.inbound.dataops import InDataOpsInterface
from pypeh.core.interfaces.outbound.dataops import ValidationInterface

from typing import Sequence

from pypeh.core.models.validation_errors import ValidationErrorReport
from pypeh.core.services.dataops import ValidationService

from peh_model import peh


class InboundTestAdapter(InDataOpsInterface):
    def validate(self, project_name: str, config_path: str, data_layout: str, data_path: str):
        pass


class OutboundTestAdapter(ValidationInterface):
    def validate(
        self,
        data: dict[str, Sequence],
        observation: peh.Observation,
        observable_properties: Sequence[peh.ObservableProperty],
    ) -> ValidationErrorReport:
        return ValidationErrorReport(
            timestamp="test",
            total_errors=0,
        )


@pytest.mark.core
class TestValidationService:
    adapter: None

    @pytest.fixture(scope="class")
    def mockdata(self):
        return {"test": list(range(10))}

    def test_validate_data(self, mockdata):
        service = ValidationService(adapter=OutboundTestAdapter())
        result_dict = service.validate(mockdata, observation=None, observable_properties=[])
        assert result_dict is not None
