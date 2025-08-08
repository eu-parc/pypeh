from __future__ import annotations

import logging

from abc import abstractmethod
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from typing import Union
    from pydantic import BaseModel
    from peh_model.peh import YAMLRoot, DataLayout

logger = logging.getLogger(__name__)


class PersistenceInterface:
    @abstractmethod
    def load(self, source: str, validation_layout: DataLayout = None, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def dump(self, destination: str, entity: Union[str, BaseModel, YAMLRoot], **kwargs) -> None:
        raise NotImplementedError


class RepositoryInterface(PersistenceInterface):
    def __init__(self):
        self.engine = None
