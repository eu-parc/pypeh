import pytest

from pypeh.core.models.settings import S3Config, LocalFileConfig


@pytest.mark.core
class TestS3Env:
    def test_custom_env_prefix(self, monkeypatch):
        monkeypatch.setenv("MYBUCKET_BUCKET_NAME", "my-test-bucket")
        monkeypatch.setenv("MYBUCKET_AWS_REGION", "eu-central-1")

        config_base = S3Config(env_prefix="MYBUCKET_")
        settings = config_base.make_settings()

        assert settings.bucket_name == "my-test-bucket"
        assert settings.aws_region == "eu-central-1"

    def test_override_env(self, monkeypatch):
        monkeypatch.setenv("MYBUCKET_BUCKET_NAME", "my-test-bucket")
        monkeypatch.setenv("MYBUCKET_ENDPOINT_URL", "http://endpoint-example.local")
        override = {"aws_region": "eu-central-1"}

        config_base = S3Config(env_prefix="MYBUCKET_", config_dict=override)
        settings = config_base.make_settings()

        assert settings.bucket_name == "my-test-bucket"
        assert settings.aws_region == "eu-central-1"
        assert settings.endpoint_url == "http://endpoint-example.local"


@pytest.mark.core
class TestLocalFileEnv:
    def test_custom_env_prefix(self, monkeypatch):
        monkeypatch.setenv("MY_DEFAULT_ROOT_FOLDER", "here/it/is")
        config_base = LocalFileConfig(env_prefix="MY_DEFAULT_")
        settings = config_base.make_settings()
        assert settings.root_folder == "here/it/is"

    def test_override_env(self, monkeypatch):
        monkeypatch.setenv("MY_DEFAULT_ROOT_FOLDER", "here/it/is")
        override = {"root_folder": "actually/it/is/here"}
        config_base = LocalFileConfig(env_prefix="MY_DEFAULT_ROOT_FOLDER_", config_dict=override)
        settings = config_base.make_settings()
        assert settings.root_folder == "actually/it/is/here"
