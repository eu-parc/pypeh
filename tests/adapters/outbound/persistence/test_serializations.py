import pytest
import fsspec

from pypeh.adapters.outbound.persistence.serializations import (
    IOAdapterFactory,
    IOAdapter,
    JsonIO,
    YamlIO,
    ExcelIO,
    CsvIO,
)

from pydantic import BaseModel
from peh_model.peh import EntityList

from tests.test_utils.dirutils import get_absolute_path


class MockAdapter(IOAdapter):
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class MockModel(BaseModel):
    empty: str


@pytest.mark.core
class TestIOAdapterFactory:
    @pytest.mark.parametrize(
        "format_name, expected_adapter",
        [
            ("json", "JsonIO"),
            ("yaml", "YamlIO"),
            ("csv", "CsvIO"),
            ("xlsx", "ExcelIO"),
            ("xls", "ExcelIO"),
        ],
    )
    def test_create_known_adapters(self, format_name, expected_adapter):
        adapter = IOAdapterFactory.create(format_name)
        assert adapter.__class__.__name__ == expected_adapter

    def test_create_unknown_adapter_raises_error(self):
        with pytest.raises(ValueError, match="No adapter registered for dataformat: unknown"):
            IOAdapterFactory.create("unknown")

    def test_register_adapter(self):
        IOAdapterFactory.register_adapter("mock", MockAdapter)
        adapter = IOAdapterFactory.create("mock", test_param=True)

        assert isinstance(adapter, MockAdapter)
        assert adapter.kwargs["test_param"]


@pytest.mark.core
class TestYamlIO:
    def test_basic(self):
        source = get_absolute_path("./input/config_basic/_Reference_YAML/observable_entities.yaml")
        yaml_io = YamlIO()
        yaml_io.load(source)

    def test_wrong_schema(self, caplog):
        source = get_absolute_path("./input/config_basic/_Reference_YAML/observable_entities.yaml")
        yaml_io = YamlIO()
        with pytest.raises(ValueError):
            _ = yaml_io.load(source, target_class=MockModel)

    def test_wrong_input(self):
        source = get_absolute_path("./input/wrong_input/random.yaml")
        yaml_io = YamlIO()
        with pytest.raises(TypeError):
            yaml_io.load(source)

    def test_textio(self):
        source = get_absolute_path("./input/config_basic/_Reference_YAML/observable_entities.yaml")
        yaml_io = YamlIO()
        with open(source, "r") as f:
            data = yaml_io.load(f)
        assert isinstance(data, EntityList)


@pytest.mark.core
class TestJsonIO:
    def test_basic(self):
        source = get_absolute_path("./input/observation_results.json")
        json_io = JsonIO()
        with open(source, "r") as f:
            data = json_io.load(f)
        assert isinstance(data, EntityList)


@pytest.mark.dataframe
class TestCsvIO:
    def test_basic_import(self):
        source = get_absolute_path("./input/config_basic/_Tabular_Data/sampling_data_to_import.csv")
        csv_io = CsvIO()
        with fsspec.open(source, "r") as f:
            data = csv_io.load(f, raise_if_empty=False, infer_schema_length=5)  # type: ignore
        from polars import DataFrame

        assert isinstance(data, DataFrame)

        with fsspec.open(source, "rb") as f:
            data = csv_io.load(f, raise_if_empty=False, infer_schema_length=5)  # type: ignore
        assert isinstance(data, DataFrame)


@pytest.mark.dataframe
class TestXlsIO:
    def test_basic_import(self):
        source = get_absolute_path("./input/config_basic/_Tabular_Data/sampling_data_to_import.xlsx")
        excel_io = ExcelIO()
        with fsspec.open(source, "rb") as f:
            data = excel_io.load(f)  # type: ignore
        assert isinstance(data, dict)

    def test_invalid_excel(self):
        source = get_absolute_path("./input/config_invalid/_Tabular_Data/invalid_excel.xlsx")
        excel_io = ExcelIO()
        with fsspec.open(source, "rb") as f:
            with pytest.raises(Exception) as excinfo:
                _ = excel_io.load(f)  # type: ignore
        assert isinstance(excinfo.value, Exception)
