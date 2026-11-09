from __future__ import annotations

import importlib
import json

import pytest
import yaml

from pypeh import S3Config, Session
from pypeh.core.models.constants import ObservablePropertyValueType
from pypeh.core.models.internal_data_layout import Dataset, DatasetSeries


@pytest.fixture
def dataset_series():
    pl = importlib.import_module("polars")

    series = DatasetSeries(label="moto_session_series")
    sample = series.add_empty_dataset("SAMPLE")
    sample.add_observation_to_index("peh:obs_sample")
    series.add_observable_property(
        observation_id="peh:obs_sample",
        observable_property_id="peh:prop_id_sample",
        data_type=ObservablePropertyValueType.STRING,
        dataset_label="SAMPLE",
        element_label="id_sample",
        is_primary_key=True,
    )
    sample.data = pl.DataFrame({"id_sample": ["sample-a", "sample-b"]})

    lab = series.add_empty_dataset("LAB")
    lab.add_observation_to_index("peh:obs_lab")
    series.add_observable_property(
        observation_id="peh:obs_lab",
        observable_property_id="peh:prop_id_sample",
        data_type=ObservablePropertyValueType.STRING,
        dataset_label="LAB",
        element_label="id_sample",
    )
    series.add_observable_property(
        observation_id="peh:obs_lab",
        observable_property_id="peh:prop_chol",
        data_type=ObservablePropertyValueType.FLOAT,
        dataset_label="LAB",
        element_label="chol",
    )
    lab.schema.add_foreign_key_link(
        element_label="id_sample",
        foreign_key_dataset_label="SAMPLE",
        foreign_key_element_label="id_sample",
    )
    lab.data = pl.DataFrame(
        {"id_sample": ["sample-a", "sample-b"], "chol": [1.2, 3.4]}
    )

    return series


@pytest.fixture
def moto_s3_endpoint():
    moto_server = importlib.import_module("moto.server")

    server = moto_server.ThreadedMotoServer(
        ip_address="127.0.0.1",
        port=0,
        verbose=False,
    )
    server.start()
    host, port = server.get_host_and_port()
    yield f"http://{host}:{port}"
    server.stop()


@pytest.fixture
def moto_s3_client(moto_s3_endpoint):
    boto3 = importlib.import_module("boto3")

    return boto3.client(
        "s3",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        aws_session_token="testing",
        endpoint_url=moto_s3_endpoint,
        region_name="us-east-1",
    )


@pytest.fixture
def s3_session(moto_s3_endpoint, moto_s3_client):
    bucket_name = "pypeh-parquet-test"
    moto_s3_client.create_bucket(Bucket=bucket_name)

    return Session(
        connection_config=[
            S3Config(
                label="data",
                config_dict={
                    "aws_access_key_id": "testing",
                    "aws_secret_access_key": "testing",
                    "aws_session_token": "testing",
                    "aws_region": "us-east-1",
                    "endpoint_url": moto_s3_endpoint,
                    "bucket_name": bucket_name,
                    "prefix": "project-prefix",
                },
            )
        ],
        default_connection=None,
    )


@pytest.mark.s3
class TestS3Integration:
    def test_session_dataset_series_parquet_roundtrip_via_moto_s3(
        self,
        s3_session,
        moto_s3_client,
        dataset_series,
    ):
        source_paths = s3_session.dump_tabular_dataset_series(
            dataset_series=dataset_series,
            connection_label="data",
        )

        assert source_paths == ["SAMPLE.parquet", "LAB.parquet"]

        response = moto_s3_client.list_objects_v2(
            Bucket="pypeh-parquet-test",
            Prefix="project-prefix/",
        )
        assert {obj["Key"] for obj in response["Contents"]} == {
            "project-prefix/SAMPLE.parquet",
            "project-prefix/LAB.parquet",
        }

        loaded = s3_session.read_tabular_dataset_series(
            source_paths=source_paths,
            file_format="parquet",
            connection_label="data",
        )

        assert set(loaded.parts) == {"SAMPLE", "LAB"}
        assert loaded.context_lookup("peh:obs_lab", "peh:prop_chol") == (
            "LAB",
            "chol",
        )
        assert loaded.resolve_join("LAB", "SAMPLE") is not None
        lab_dataset = loaded["LAB"]
        assert isinstance(lab_dataset, Dataset)
        assert lab_dataset.data is not None
        assert lab_dataset.data.shape == (2, 2)

    def test_session_dataset_series_dump_outside_prefix_roundtrips(
        self,
        s3_session,
        moto_s3_client,
        dataset_series,
    ):
        source_paths = s3_session.dump_tabular_dataset_series(
            dataset_series=dataset_series,
            output_path="s3://pypeh-parquet-test/other/out",
            connection_label="data",
        )

        assert source_paths == [
            "s3://pypeh-parquet-test/other/out/SAMPLE.parquet",
            "s3://pypeh-parquet-test/other/out/LAB.parquet",
        ]

        response = moto_s3_client.list_objects_v2(
            Bucket="pypeh-parquet-test",
            Prefix="other/out/",
        )
        assert {obj["Key"] for obj in response["Contents"]} == {
            "other/out/SAMPLE.parquet",
            "other/out/LAB.parquet",
        }

        loaded = s3_session.read_tabular_dataset_series(
            source_paths=source_paths,
            file_format="parquet",
            connection_label="data",
        )

        assert set(loaded.parts) == {"SAMPLE", "LAB"}

    def test_study_metadata_roundtrip_via_moto_s3(
        self, s3_session, moto_s3_client
    ):
        metadata = {
            "observations": [],
            "datasets": [{"described_by": None, "variables": []}],
            "provenance": {
                "pypeh_version": "0.9.1",
                "peh_model_version": "1.2.3",
                "validation_report": None,
            },
        }
        for file_format in ("yaml", "json"):
            path = f"metadata/study.{file_format}"
            written = s3_session.dump_study_metadata(
                metadata,
                path,
                file_format=file_format,
                connection_label="data",
            )
            assert written == path
            response = moto_s3_client.get_object(
                Bucket="pypeh-parquet-test",
                Key=f"project-prefix/{path}",
            )
            payload = response["Body"].read().decode("utf-8")
            loaded = (
                yaml.safe_load(payload)
                if file_format == "yaml"
                else json.loads(payload)
            )
            assert loaded == metadata

        outside = "s3://pypeh-parquet-test/other/study.json"
        written = s3_session.dump_study_metadata(
            metadata,
            outside,
            file_format="json",
            connection_label="data",
        )
        assert written == outside
        response = moto_s3_client.get_object(
            Bucket="pypeh-parquet-test", Key="other/study.json"
        )
        assert json.loads(response["Body"].read()) == metadata

        # Moto's in-memory bucket survives across server fixtures, so leave
        # no metadata keys for the parquet tests' exact listing assertion.
        for key in (
            "project-prefix/metadata/study.yaml",
            "project-prefix/metadata/study.json",
            "other/study.json",
        ):
            moto_s3_client.delete_object(Bucket="pypeh-parquet-test", Key=key)

    @pytest.mark.parametrize(
        "output_path",
        [
            "",
            "metadata/",
            "s3://pypeh-parquet-test/project-prefix",
            "s3://pypeh-parquet-test/project-prefix/",
            "s3://another-bucket/project-prefix/metadata.yaml",
        ],
    )
    def test_study_metadata_rejects_bad_s3_paths_without_writing(
        self, s3_session, moto_s3_client, output_path
    ):
        def keys():
            response = moto_s3_client.list_objects_v2(
                Bucket="pypeh-parquet-test"
            )
            return {obj["Key"] for obj in response.get("Contents", [])}

        before = keys()
        with pytest.raises(ValueError, match="output_path|bucket"):
            s3_session.dump_study_metadata(
                {"observations": []},
                output_path,
                file_format="yaml",
                connection_label="data",
            )
        assert keys() == before
