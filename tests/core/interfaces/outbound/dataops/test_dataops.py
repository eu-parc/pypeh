import pytest
import abc

from typing import Protocol, Any, Generic
from peh_model.peh import DataLayout

from pypeh.core.interfaces.outbound.dataops import T_DataType, ValidationInterface
from pypeh.core.models.validation_errors import ValidationErrorReport
from pypeh.core.models.constants import ValidationErrorLevel
from pypeh.core.models.validation_dto import (
    ValidationExpression,
    ValidationDesign,
    ColumnValidation,
    ValidationConfig,
)
from pypeh.core.models.settings import LocalFileSettings
from tests.test_utils.dirutils import get_absolute_path


class DataOpsProtocol(Protocol, Generic[T_DataType]):
    data_format: T_DataType

    def validate(self, data, config) -> ValidationErrorReport: ...

    def import_data(self, source, config) -> Any: ...

    def import_data_layout(self, source, config) -> Any: ...


class TestValidation(abc.ABC):
    """Abstract base class for testing dataops adapters."""

    @abc.abstractmethod
    def get_adapter(self) -> DataOpsProtocol:
        """Return the adapter implementation to test."""
        raise NotImplementedError

    def test_getting_default_adapter_from_interface(self):
        adapter_class = ValidationInterface.get_default_adapter_class()
        adapter = adapter_class()
        assert isinstance(adapter, ValidationInterface)
        assert isinstance(adapter, type(self.get_adapter()))

    def test_validate(self):
        adapter = self.get_adapter()

        data = {
            "col1": [1, 2, 3, None],
            "col2": [2, 3, 1, None],
        }

        config = ValidationConfig(
            name="test_config",
            columns=[
                ColumnValidation(
                    unique_name="col1",
                    data_type="integer",
                    required=True,
                    nullable=False,
                    validations=[
                        ValidationDesign(
                            name="name",
                            error_level=ValidationErrorLevel.ERROR,
                            expression=ValidationExpression(
                                command="is_greater_than",
                                arg_columns=["col1"],
                            ),
                        )
                    ],
                )
            ],
            identifying_column_names=["col1"],
            validations=[
                ValidationDesign(
                    name="name",
                    error_level=ValidationErrorLevel.ERROR,
                    expression=ValidationExpression(
                        command="is_greater_than",
                        arg_columns=["col2"],
                        subject=["col1"],
                    ),
                )
            ],
        )

        result = adapter._validate(data, config)

        assert result is not None
        assert result.total_errors == 3


class TestDataImport(abc.ABC):
    """Abstract base class for testing dataops adapters."""

    @abc.abstractmethod
    def get_adapter(self) -> DataOpsProtocol:
        """Return the adapter implementation to test."""
        raise NotImplementedError

    def test_import_data_layout(self):
        adapter = self.get_adapter()
        source = "./input/datalayout.yaml"
        path = get_absolute_path(source)
        config = LocalFileSettings()
        data = adapter.import_data_layout(path, config)
        if isinstance(data, list):
            assert all(isinstance(dl, DataLayout) for dl in data)
        else:
            assert isinstance(data, DataLayout)

    def test_import_csv(self):
        adapter = self.get_adapter()
        source = "./input/data.csv"
        path = get_absolute_path(source)
        config = LocalFileSettings()
        data = adapter.import_data(path, config)
        assert isinstance(data, adapter.data_format)

    def test_import_excel(self):
        adapter = self.get_adapter()
        source = "./input/data.xlsx"
        path = get_absolute_path(source)
        config = LocalFileSettings()
        data = adapter.import_data(path, config)
        assert all(isinstance(d, adapter.data_format) for d in data.values())


@pytest.mark.dataframe
class TestDataFrameDataOps(TestValidation, TestDataImport):
    def get_adapter(self) -> DataOpsProtocol:
        try:
            from pypeh.adapters.outbound.validation.pandera_adapter import dataops as dfops

            return dfops.DataFrameAdapter()
        except ImportError:
            pytest.skip("Necessary modules not installed")


@pytest.mark.other
class TestUnknownDataOps(TestValidation):
    def get_adapter(self) -> DataOpsProtocol:
        raise NotImplementedError
