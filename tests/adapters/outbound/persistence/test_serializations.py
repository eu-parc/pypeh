import io

import fsspec
import linkml_runtime.loaders
import pytest
import rdflib

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

from pypeh.core.cache.containers import CacheContainer, CacheContainerFactory
from tests.test_utils.dirutils import get_absolute_path
from tests.test_utils.xlsx import write_minimal_xlsx


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

    def test_typed_sheet(self):
        typed_dict = {
            "id_sample": "string",
            "samplingyear": "float",
            "samplingmonth": "string",
            "samplingday": "float",
            "samplinghour": "float",
            "samplingminutes": "float",
        }
        source = get_absolute_path("./input/validation_test_03_data.xlsx")
        excel_io = ExcelIO()
        with fsspec.open(source, "rb") as f:
            result = excel_io.load_section(
                f,  # type: ignore
                section_name="SAMPLE",
                data_schema=typed_dict,
            )
        import polars as pl

        assert isinstance(result, pl.DataFrame)

    def test_typed_excel(self):
        typed_dict = {
            "SAMPLE": {
                "id_sample": "string",
                "samplingyear": "float",
                "samplingmonth": "string",
                "samplingday": "float",
                "samplinghour": "float",
                "samplingminutes": "float",
            },
            "SAMPLETIMEPOINT_BSS": {"id_sample": "integer", "chol": "float", "chol_loq": "float", "chol_lod": "float"},
        }
        source = get_absolute_path("./input/validation_test_03_data.xlsx")
        excel_io = ExcelIO()
        with fsspec.open(source, "rb") as f:
            result = excel_io.load(
                f,  # type: ignore
                data_schema=typed_dict,
            )
        assert isinstance(result, dict)

    def test_typed_sheet_type_mismatch_is_loaded_as_null(self, tmp_path):
        source = tmp_path / "typed_mismatch.xlsx"
        write_minimal_xlsx(
            source,
            sheet_name="SAMPLE",
            headers=["id_sample", "chol"],
            rows=[
                ["sample_a", 1.2],
                ["sample_b", "oops"],
                ["sample_c", 3.4],
            ],
        )

        excel_io = ExcelIO()
        result = excel_io.load_section(
            source,
            section_name="SAMPLE",
            data_schema={"id_sample": "string", "chol": "float"},
            cast_error_policy="null",
        )

        assert result.shape == (3, 2)
        assert result["id_sample"].to_list() == [
            "sample_a",
            "sample_b",
            "sample_c",
        ]
        assert result["chol"].to_list() == [1.2, None, 3.4]

    def test_typed_sheet_type_mismatch_raises_when_requested(self, tmp_path):
        from pypeh.adapters.persistence.dataframe import DataFrameTypeCastError

        source = tmp_path / "typed_mismatch.xlsx"
        write_minimal_xlsx(
            source,
            sheet_name="SAMPLE",
            headers=["id_sample", "chol"],
            rows=[
                ["sample_a", 1.2],
                ["sample_b", "oops"],
                ["sample_c", 3.4],
            ],
        )

        excel_io = ExcelIO()
        with pytest.raises(
            DataFrameTypeCastError,
            match="Failed to cast Excel sheet 'SAMPLE'",
        ):
            excel_io.load_section(
                source,
                section_name="SAMPLE",
                data_schema={"id_sample": "string", "chol": "float"},
                cast_error_policy="raise",
            )


@pytest.mark.core
class TestDump:
    @pytest.fixture(scope="class")
    def container(self) -> CacheContainer:
        source = get_absolute_path("./input/config_basic/_Reference_YAML/observable_properties.yaml")
        yaml_io = YamlIO()
        entity_list = yaml_io.load(source)
        assert isinstance(entity_list, EntityList)
        cache = CacheContainerFactory.new()
        cache.unpack_entity_list(entity_list=entity_list)
        return cache

    def test_dump_cache_yaml(self, container):
        entity_list = container.pack_entity_list()
        adapter = IOAdapterFactory.create(format="yaml")
        buffer = io.StringIO()
        loader = linkml_runtime.loaders.YAMLLoader()

        adapter.dump(entity_list, buffer)
        data = buffer.getvalue()
        assert len(data) > 0
        new_entity_list = loader.load_any(source=data, target_class=EntityList)
        assert isinstance(entity_list, EntityList)
        assert entity_list == new_entity_list

    @pytest.mark.parametrize("format", ["trig", "turtle"])
    def test_dump_cache_rdf(self, container, format):
        entity_list = container.pack_entity_list()
        adapter = IOAdapterFactory.create(format=format)
        buffer = io.BytesIO()

        adapter.dump(entity_list, buffer)
        data = buffer.getvalue()
        assert data, "RDF serialization is empty"
        if format == "trig":
            g = rdflib.Dataset()
            g.parse(data=data, format="trig")
            assert len(g) > 0
        else:
            g = rdflib.Graph()
            g.parse(data=data, format=format)
            ns = dict(g.namespaces())
            assert "peh" in ns
            assert "pehterms" in ns
            OP = rdflib.URIRef(ns["pehterms"] + "ObservableProperty")
            assert (None, rdflib.RDF.type, OP) in g, "No ObservableProperty instances found"
            EL = rdflib.URIRef(ns["pehterms"] + "EntityList")
            assert (None, rdflib.RDF.type, EL) in g, "No EntityList found"
            observable_properties_pred = rdflib.URIRef(ns["pehterms"] + "observable_properties")
            entity_lists = list(g.subjects(rdflib.RDF.type, EL))
            assert entity_lists, "No EntityList subjects found"
            for el in entity_lists:
                props = list(g.objects(el, observable_properties_pred))
                assert props, "EntityList has no observable_properties"
                for p in props:
                    label_pred = rdflib.URIRef(ns["rdfs"] + "label")
                    assert (p, label_pred, None) in g, f"Observable property {p} has no rdfs label"
