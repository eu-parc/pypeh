"""
Interface classes providing data, schema and template export functionality.
"""

from __future__ import annotations

import logging

from abc import abstractmethod

logger = logging.getLogger(__name__)

class ExportInterface:
    @abstractmethod
    def export_data_template(self, layout, destination: str, observable_property_dict: dict = None, studyinfo_header_list: list = None, codebook_metadata_dict: dict = None) -> bool:
        raise NotImplementedError

    @abstractmethod
    def export_data_dictionary(self, observation_design, layout, destination: str, observable_property_dict: dict = None, studyinfo_header_list: list = None, codebook_metadata_dict: dict = None) -> bool:
        raise NotImplementedError

    @abstractmethod
    def export_data(self, observation_result, layout, destination: str, observable_property_dict: dict = None, studyinfo_header_list: list = None, codebook_metadata_dict: dict = None) -> bool:
        raise NotImplementedError

