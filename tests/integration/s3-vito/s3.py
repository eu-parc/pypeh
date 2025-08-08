from contextlib import contextmanager
from pypeh.core.models.settings import S3Config
from pypeh.adapters.outbound.persistence.hosts import S3StorageProvider


@contextmanager
def s3_context(env_file=".env", env_prefix="S3_"):
    config = S3Config(env_prefix=env_prefix)
    settings = config.make_settings(_env_file=env_file)
    s3io = S3StorageProvider(settings)
    yield s3io


def verify_existence():
    """Requirement: VPN connection"""
    with s3_context() as s3io:
        bucket_root = s3io.bucket + "/"
        print(f"bucket root: {bucket_root}")
        try:
            found_file = s3io.file_system.exists(bucket_root + "test.xlsx")
        except Exception as e:
            print(f"Error while looking for test.xlsx: {e}")
    if found_file:
        print("✅ Found test.xlsx")
    else:
        print("❌ File not found.")


def load_testfile():
    """Requirement: VPN connection"""
    with s3_context() as s3io:
        try:
            data = s3io.load("test.xlsx")
        except Exception as e:
            print(f"Error while looking for test.xlsx: {e}")
    if data is not None:
        print("✅ Loaded test.xlsx")
    else:
        print("❌ Could not load test.xlsx")


def main():
    verify_existence()
    load_testfile()


if __name__ == "__main__":
    main()
