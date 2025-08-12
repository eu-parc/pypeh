from __future__ import annotations

import logging

from typing import TYPE_CHECKING

from pypeh.core.interfaces.inbound.dataops import InDataOpsInterface
from pypeh.core.interfaces.outbound.dataops import OutDataOpsInterface, ValidationInterface
from pypeh.core.cache.containers import CacheContainer, CacheContainerFactory


if TYPE_CHECKING:
    pass

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
