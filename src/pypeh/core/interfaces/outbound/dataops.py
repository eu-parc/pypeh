"""
Each of these Interface subclasses provides a protocol on how
the corresponding Adapter subclass should be implemented.

Usage: TODO: add usage info

"""

from __future__ import annotations
import importlib

import logging

from abc import abstractmethod
from peh_model.peh import DataLayout, ValidationDesign, EntityList, Observation, ObservableProperty
from typing import TYPE_CHECKING, Generic, cast, List

from pypeh.core.models.typing import T_DataType
from pypeh.core.models.settings import FileSystemSettings
from pypeh.core.models.validation_dto import ValidationConfig
from pypeh.core.session.connections import ConnectionManager
from pypeh.core.models.validation_errors import ValidationErrorReportCollection

if TYPE_CHECKING:
    from typing import Sequence
    from pypeh.core.models.validation_errors import ValidationErrorReport

logger = logging.getLogger(__name__)


class OutDataOpsInterface:
    """
    Example of DataOps methods
    def validate(self, data: Mapping, config: Mapping):
        pass

    def summarize(self, dat: Mapping, config: Mapping):
        pass
    """

    pass


class ValidationInterface(OutDataOpsInterface, Generic[T_DataType]):
    @abstractmethod
    def _validate(self, data: dict[str, Sequence] | T_DataType, config: ValidationConfig) -> ValidationErrorReport:
        raise NotImplementedError

    @classmethod
    def get_default_adapter_class(cls):
        try:
            adapter_module = importlib.import_module("pypeh.adapters.outbound.validation.pandera_adapter.dataops")
            adapter_class = getattr(adapter_module, "DataFrameAdapter")
        except Exception as e:
            logger.error("Exception encountered while attempting to import a Pandera-based DataFrameAdapter")
            raise e
        return adapter_class

    def validate(
        self,
        data: dict[str, Sequence] | T_DataType,
        observation_list: Sequence[Observation],
        observable_properties: List[ObservableProperty],
        dataset_validations: Sequence[ValidationDesign] | None = None,
    ) -> ValidationErrorReportCollection:
        observable_property_dict = {op.id: op for op in observable_properties}
        result_dict = ValidationErrorReportCollection()
        for observation_id, validation_config in ValidationConfig.from_observation_list(
            observation_list,
            observable_property_dict,
            dataset_validations,
        ):
            result_dict[observation_id] = self._validate(data, validation_config)

        return result_dict


class DataImportInterface(OutDataOpsInterface, Generic[T_DataType]):
    @abstractmethod
    def import_data(self, source: str, config: FileSystemSettings) -> T_DataType | List[T_DataType]:
        raise NotImplementedError

    def import_data_layout(
        self,
        source: str,
        config: FileSystemSettings,
        **kwargs,
    ) -> DataLayout | List[DataLayout]:
        provider = ConnectionManager._create_adapter(config)
        layout = provider.load(source)
        if isinstance(layout, EntityList):
            layout = layout.layouts
        if isinstance(layout, list):
            if not all(isinstance(item, DataLayout) for item in layout):
                me = "Imported layouts should all be DataLayout instances"
                logger.error(me)
                raise TypeError(me)
            return cast(List[DataLayout], layout)

        elif isinstance(layout, DataLayout):
            return layout

        else:
            me = f"Imported layout should be a DataLayout instance not {type(layout)}"
            logger.error(me)
            raise TypeError(me)
