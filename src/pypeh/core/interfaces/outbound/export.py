"""
Interface classes providing data, schema and template export functionality.
"""

from __future__ import annotations

import logging

from abc import abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Optional 
    from peh_model.peh import ObservationDesign, ObservationResult, DataLayout, ObservableProperty

logger = logging.getLogger(__name__)


class ExportInterface:
    @abstractmethod
    def export_data_template(
        self,
        layout: DataLayout,
        destination: str,
        observable_property_dict: Optional[dict[str, ObservableProperty]] = None,
        studyinfo_header_list: Optional[list[str]] = None,
        codebook_metadata_dict: Optional[dict[str, str]] = None,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def export_data_dictionary(
        self,
        observation_design: ObservationDesign,
        layout: DataLayout,
        destination: str,
        observable_property_dict: Optional[dict[str, ObservableProperty]] = None,
        studyinfo_header_list: Optional[list[str]] = None,
        codebook_metadata_dict: Optional[dict[str, str]] = None,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def export_data(
        self,
        observation_result: ObservationResult,
        layout: DataLayout,
        destination: str,
        observable_property_dict: Optional[dict[str, ObservableProperty]] = None,
        studyinfo_header_list: Optional[list[str]] = None,
        codebook_metadata_dict: Optional[dict[str, str]] = None,
    ) -> bool:
        raise NotImplementedError
