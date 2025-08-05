"""
Interface classes providing data, schema and template export functionality.
"""

from __future__ import annotations

import logging

from abc import abstractmethod
from peh_model.peh import DataLayout, EntityList
from typing import TYPE_CHECKING, TypeVar, Generic, cast, List

if TYPE_CHECKING:
    from typing import Sequence
    from pypeh.core.models.validation_errors import ValidationErrorReport

logger = logging.getLogger(__name__)

class ExportInterface:
    @abstractmethod
    def export_data(self, data: dict[str, Sequence]) -> bool:
        raise NotImplementedError

    @abstractmethod
    def export_data_dictionary(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def export_data_template(self) -> bool:
        raise NotImplementedError
