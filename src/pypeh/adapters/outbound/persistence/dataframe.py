from __future__ import annotations

import logging
import polars as pl
import io

from pathlib import Path
from typing import TYPE_CHECKING, Union, IO

from pypeh.adapters.outbound.persistence.serializations import IOAdapter
from pypeh.adapters.outbound.persistence.serializations import is_consistent_with_layout

if TYPE_CHECKING:
    from peh_model.peh import DataLayout


logger = logging.getLogger(__name__)


class CsvIOImpl(IOAdapter):
    def load(self, source: Union[str, Path, IO[str], IO[bytes]], **kwargs) -> pl.DataFrame:
        try:
            if hasattr(source, "read") and not isinstance(source, (str, Path)):
                encoding = kwargs.get("encoding", None)
                if encoding is None:
                    encoding = "utf-8"
                data = source.read()
                if isinstance(data, memoryview):
                    data = data.tobytes().decode(encoding)
                elif isinstance(data, (bytes, bytearray)):
                    data = data.decode(encoding)
                buffer = io.StringIO(data)
                return pl.read_csv(buffer, **kwargs)
            else:
                return pl.read_csv(source=str(source), **kwargs)

        except Exception as e:
            logger.error(f"Error in CSVIOImpl: {e}")
            raise

    def dump(self, destination: str, **kwargs):
        raise NotImplementedError


class ExcelIOImpl(IOAdapter):
    def load(self, source: Union[str, Path, IO[str], IO[bytes]], validation_layout: DataLayout = None, **kwargs) -> dict[str, pl.DataFrame]:
        try:
            result = None
            default = {
                "sheet_id": 0,
                "engine": "calamine",
                "has_header": True,
            }
            options = {**default, **kwargs}
            if hasattr(source, "read") and not isinstance(source, (str, Path)):
                if isinstance(source, IO) and "b" not in getattr(source, "mode", "b"):
                    raise ValueError("Excel source must be opened in binary mode")
                data = source.read()
                result = pl.read_excel(  # type: ignore
                    source=io.BytesIO(data),  # type: ignore
                    **options,
                )
            else:
                result = pl.read_excel(  # type: ignore
                    source=str(source),  # type: ignore
                    **options,
                )
            if validation_layout is None or is_consistent_with_layout(result, validation_layout):
                return result
            else:
                raise Exception("Excel layout validation failed while loading tabular data")
        except Exception as e:
            logger.error(f"Error in ExcelIOImpl: {e}")
            raise

    def dump(self, destination: str, **kwargs):
        raise NotImplementedError
