import yaml # type: ignore[import-untyped]

from importlib.resources import files
from linkml_runtime import SchemaView


def get_schema_view():
    path = files("peh_model").joinpath("schema/peh.yaml")
    with path.open("r") as f:
        schema = yaml.safe_load(f)
        schema_view = SchemaView(schema)
    return schema_view
