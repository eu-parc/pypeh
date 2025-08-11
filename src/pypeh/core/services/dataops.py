from __future__ import annotations

import logging

from typing import TYPE_CHECKING, Sequence
from peh_model import peh

from pypeh.core.interfaces.inbound.dataops import InDataOpsInterface
from pypeh.core.interfaces.outbound.dataops import OutDataOpsInterface, ValidationInterface
from pypeh.core.interfaces.outbound.persistence import PersistenceInterface
from pypeh.core.models.settings import SettingsConfig
from pypeh.core.cache.containers import CacheContainer, CacheContainerFactory
from pypeh.core.models.validation_dto import ValidationConfig


if TYPE_CHECKING:
    from polars import DataFrame

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


class ValidationService(DataOpsService):
    def __init__(
        self,
        outbound_adapter: ValidationInterface,
        inbound_adapter: InDataOpsInterface | None = None,
        cache: CacheContainer = CacheContainerFactory.new(),
    ):
        super().__init__(inbound_adapter, outbound_adapter, cache)
        self.outbound_adapter: ValidationInterface = outbound_adapter

    def _validate_data(
        self,
        data: dict[str, Sequence] | DataFrame,
        observation: peh.Observation,
        observable_property_dict: dict[str, peh.ObservableProperty],
    ) -> dict:
        result_dict = {}
        for oep_set_name, validation_config in ValidationConfig.from_observation(
            observation,
            observable_property_dict,
        ):
            result_dict[oep_set_name] = self.outbound_adapter.validate(data, validation_config)

        return result_dict

    def validate_data(
        self,
        data: dict[str, Sequence] | DataFrame,
        observation_id: str,
        observable_property_id_list: list[str],
    ) -> dict:
        observation_entity = self.cache.get(observation_id, "Observation")
        if not isinstance(observation_entity, peh.Observation):
            me = f"Provided observation_id {observation_id} does not point to an Observation"
            logger.error(me)
            raise TypeError(me)
        observable_property_dict = {}

        for _id in observable_property_id_list:
            entity = self.cache.get(_id, "ObservableProperty")
            if not isinstance(entity, peh.ObservableProperty):
                me = f"Provided observable_property_id {_id} does not point to an ObservableProperty"
                logger.error(me)
                raise TypeError(me)
            observable_property_dict[_id] = entity

        return self._validate_data(
            data,
            observation_entity,
            observable_property_dict,
        )


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