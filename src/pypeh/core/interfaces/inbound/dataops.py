"""
Services that provide Validation features use this interface for external users to access.
"""

from abc import abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class InDataOpsInterface:
    @abstractmethod
    def validate(self, project_name: str, config_path: str, data_layout: str, data_path: str): # type: ignore[no-untyped-def]
        raise NotImplementedError

    @abstractmethod
    def load(self, project_name: str, config_path: str, data_layout: str, data_path: str): # type: ignore[no-untyped-def]
        raise NotImplementedError

    @abstractmethod
    def extract(self, project_name: str, config_path: str, data_layout: str, data_extract: str, target_path: str): # type: ignore[no-untyped-def]
        raise NotImplementedError
