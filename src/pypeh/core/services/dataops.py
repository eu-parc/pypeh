from __future__ import annotations
import importlib
import os

import logging

from typing import TYPE_CHECKING, TypeVar
from peh_model.peh import Observation, ObservableProperty

from pypeh.core.interfaces.inbound.dataops import InDataOpsInterface
from pypeh.core.interfaces.outbound.dataops import OutDataOpsInterface, ValidationInterface
from pypeh.core.interfaces.outbound.persistence import PersistenceInterface
from pypeh.core.models.settings import AdapterConfig, SettingsConfig
from pypeh.core.cache.containers import CacheContainer, CacheContainerFactory


if TYPE_CHECKING:
    from typing import Sequence, List
    from pypeh.core.models.validation_errors import ValidationErrorReportCollection

T_DataType = TypeVar("T_DataType")

logger = logging.getLogger(__name__)


class DataOpsService:
    def __init__(
        self,
        inbound_adapter: InDataOpsInterface | None,
        processing_adapter: OutDataOpsInterface,
        cache: CacheContainer = CacheContainerFactory.new(),
    ):
        self.inbound_adapter = inbound_adapter
        self.processing_adapter = processing_adapter
        self.cache = cache


class ValidationService:
    adapter: ValidationInterface = None

    def __init__(
        self,
        adapter: PersistenceInterface | None = None,
    ):
        if adapter:
            self.adapter = adapter
        elif os.environ.get("VALIDATION_ADAPTER_MODULE_IMPORT_NAME"):
            adapter_import_prefix = "VALIDATION_ADAPTER_"
            adapter_config = AdapterConfig(env_prefix=adapter_import_prefix)
            adapter_settings = adapter_config.make_settings()

            adapter_module = importlib.import_module(adapter_settings.module_import_name)
            adapter_class = getattr(adapter_module, adapter_settings.class_import_name)
            self.adapter = adapter_class()

    def register_adapter(self, adapter: ValidationInterface):
        self.adapter = adapter

    def validate(
        self,
        data: dict[str, Sequence] | T_DataType,
        observation: Observation,
        observable_properties: List[ObservableProperty],
    ) -> ValidationErrorReportCollection:
        return self.adapter.validate(data, observation, observable_properties)


class DataImportService(DataOpsService):
    def __init__(
        self,
        outbound_adapter: PersistenceInterface,
        inbound_adapter: InDataOpsInterface | None = None,
        cache: CacheContainer = CacheContainerFactory.new(),
    ):
        super().__init__(inbound_adapter, outbound_adapter, cache)
        self.outbound_adapter: PersistenceInterface = outbound_adapter

    def import_data(
        self, source: str, config: SettingsConfig, data_layout: str, layout_config: SettingsConfig | None = None
    ):
        # validate config
        settings = config.make_settings()
        if layout_config is not None:
            layout_settings = layout_config.make_settings()
        else:
            layout_settings = settings

        # import layout and extract info
        layout_object = self.outbound_adapter.import_data_layout(
            data_layout,
            layout_settings,
        )
        # import data
        # verify data with layout
        data = self.outbound_adapter.load(source, validation_layout=layout_object)
        return data
