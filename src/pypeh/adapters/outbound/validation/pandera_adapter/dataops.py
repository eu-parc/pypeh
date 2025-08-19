"""
This part of the code should contain the reusable part
of the PyHBM library, aka, the part that would otherwise
be copied across projects. Ideally, it also contains a
specification on what the custom part should look like.
"""

from __future__ import annotations

import logging

from dataguard import Validator, ErrorCollector
from peh_model.peh import DataLayout
from polars import DataFrame
from typing import TYPE_CHECKING, List, Dict

from pypeh.core.interfaces.outbound.dataops import (
    ValidationInterface,
    DataImportInterface,
)
from pypeh.core.models.validation_errors import ValidationErrorReport
from pypeh.core.models.validation_dto import ValidationConfig
from pypeh.adapters.outbound.validation.pandera_adapter.parsers import parse_config, parse_error_report
from pypeh.adapters.outbound.persistence.hosts import HostFactory, FileIO

if TYPE_CHECKING:
    from typing import Mapping
    from pypeh.core.models.settings import FileSystemSettings

logger = logging.getLogger(__name__)


class DataFrameAdapter(ValidationInterface[DataFrame], DataImportInterface[DataFrame]):
    data_format = DataFrame

    def parse_configuration(self, config: ValidationConfig) -> Mapping:
        return parse_config(config)

    def get_error_collector(self):
        return ErrorCollector()

    def cleanup(self):
        self.get_error_collector().clear_errors()

    def _validate(self, data: dict[str, list] | DataFrame, config: ValidationConfig) -> ValidationErrorReport:
        config_map = self.parse_configuration(config)
        validator = Validator.config_from_mapping(config=config_map, logger=logger)
        _ = validator.validate(data)

        return parse_error_report(self.get_error_collector().get_errors())

    def summarize(self, data: Mapping, config: Mapping):
        pass

    def import_data(self, source: str, config: FileSystemSettings, **kwargs) -> DataFrame | Dict[str, DataFrame]:
        provider = HostFactory.create(config)
        # format  = # should either be .csv or .xls/.xlsx
        # or provide additional info in kwargs
        format = FileIO.get_format(source)
        if format not in set(("csv", "xls", "xlsx")):
            # TODO: provide transformation function from format to dataframe
            logger.error("File format should either be .csv, .xls, or .xlsx")
            raise ValueError
        data = provider.load(source)
        if not isinstance(data, DataFrame):
            me = "Imported data is not a dataframe or dict of dataframes."
            if isinstance(data, dict):
                if not all(isinstance(d, DataFrame) for d in data.values()):
                    logger.error(me)
                    raise TypeError(me)
            else:
                logger.error(me)
                raise TypeError(me)
        return data

    def import_data_layout(
        self,
        source: str,
        config: FileSystemSettings,
        **kwargs,
    ) -> DataLayout | List[DataLayout]:
        return super().import_data_layout(source, config, **kwargs)
