"""
Unit tests for artifact storage abstraction.

Tests:
- Local store operations (Requirements 2.1)
- Presigned URL generation (Requirements 2.8, 2.9)
- Manifest conditional write (Requirements 2.4, 2.5)
- Readers treat missing manifest as incomplete (Requirements 2.9)
- Event appending (Requirements 2.11)
- Heartbeat updates (Requirements 2.12)

Requirements: 2.1, 2.4, 2.5, 2.8, 2.9, 2.11, 2.12
"""

import importlib.util
import json
import sys
import threading
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest


def _has_module(name: str) -> bool:
    """Check if a module is available without importing it."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ModuleNotFoundError, ValueError):
        return False


from deploy.manifest import (
    JobCost,
    JobInputs,
    JobManifest,
    JobTiming,
    JobVersions,
)
from deploy.storage import (
    ArtifactStore,
    BlobStore,
    GCSStore,
    LocalStore,
    ManifestAlreadyExistsError,
    S3Store,
    create_store,
)


def create_test_manifest(job_id: str = "test-123", status: str = "SUCCEEDED") -> JobManifest:
    """Create a test manifest for testing."""
    return JobManifest(
        job_id=job_id,
        idempotency_key="test-key",
        deployment="test",
        execution_id="task-1",
        attempt=1,
        status=status,
        inputs=JobInputs(
            company_name="Test Co",
            company_url="https://test.example",
            mode="full",
        ),
        expected_artifacts=["report.md"],
        timing=JobTiming(submitted_at="2026-02-03T10:00:00Z"),
        cost=JobCost(estimated_usd=1.0),
        artifacts={},
        versions=JobVersions(primr="1.0.0", runner="1.0.0"),
    )


def test_blob_store_supports_managed_identity(monkeypatch) -> None:
    credential = object()
    container = MagicMock()
    container_client = MagicMock(return_value=container)
    azure_module = ModuleType("azure")
    azure_module.__path__ = []  # type: ignore[attr-defined]
    storage_module = ModuleType("azure.storage")
    storage_module.__path__ = []  # type: ignore[attr-defined]
    blob_module = ModuleType("azure.storage.blob")
    blob_module.ContainerClient = container_client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "azure", azure_module)
    monkeypatch.setitem(sys.modules, "azure.storage", storage_module)
    monkeypatch.setitem(sys.modules, "azure.storage.blob", blob_module)

    store = BlobStore(
        "artifacts",
        "prod",
        account_name="primrstore",
        credential=credential,
    )

    assert store.container_client is container
    container_client.assert_called_once_with(
        account_url="https://primrstore.blob.core.windows.net",
        container_name="artifacts",
        credential=credential,
    )


class TestLocalStore:
    """Tests for LocalStore implementation."""

    def test_init_creates_base_path(self, tmp_path):
        """Test that LocalStore creates base path on init."""
        store_path = tmp_path / "artifacts"
        store = LocalStore(store_path, "test")

        assert store_path.exists()
        assert store.deployment == "test"

    def test_put_creates_file(self, tmp_path):
        """Test that put creates the artifact file."""
        store = LocalStore(tmp_path, "test")

        store.put("job-123/artifact.txt", b"Hello, World!")

        file_path = tmp_path / "test" / "job-123" / "artifact.txt"
        assert file_path.exists()
        assert file_path.read_bytes() == b"Hello, World!"

    def test_put_creates_parent_directories(self, tmp_path):
        """Test that put creates parent directories as needed."""
        store = LocalStore(tmp_path, "test")

        store.put("job-123/nested/deep/artifact.txt", b"content")

        file_path = tmp_path / "test" / "job-123" / "nested" / "deep" / "artifact.txt"
        assert file_path.exists()

    def test_put_overwrites_existing(self, tmp_path):
        """Test that put overwrites existing files."""
        store = LocalStore(tmp_path, "test")

        store.put("job-123/artifact.txt", b"original")
        store.put("job-123/artifact.txt", b"updated")

        file_path = tmp_path / "test" / "job-123" / "artifact.txt"
        assert file_path.read_bytes() == b"updated"

    def test_get_returns_content(self, tmp_path):
        """Test that get returns file content."""
        store = LocalStore(tmp_path, "test")
        store.put("job-123/artifact.txt", b"Hello, World!")

        content = store.get("job-123/artifact.txt")

        assert content == b"Hello, World!"

    def test_get_returns_none_for_missing(self, tmp_path):
        """Test that get returns None for missing files."""
        store = LocalStore(tmp_path, "test")

        content = store.get("nonexistent/file.txt")

        assert content is None

    def test_list_keys_returns_files(self, tmp_path):
        """Test that list_keys returns all files with prefix."""
        store = LocalStore(tmp_path, "test")
        store.put("job-123/artifact1.txt", b"content1")
        store.put("job-123/artifact2.txt", b"content2")
        store.put("job-456/artifact.txt", b"content3")

        keys = store.list_keys("job-123")

        assert len(keys) == 2
        assert "job-123/artifact1.txt" in keys
        assert "job-123/artifact2.txt" in keys

    def test_list_keys_empty_for_no_match(self, tmp_path):
        """Test that list_keys returns empty list for no matches."""
        store = LocalStore(tmp_path, "test")
        store.put("job-123/artifact.txt", b"content")

        keys = store.list_keys("nonexistent")

        assert keys == []

    def test_presign_returns_file_url(self, tmp_path):
        """Test that presign returns file:// URL for local store."""
        store = LocalStore(tmp_path, "test")
        store.put("job-123/artifact.txt", b"content")

        url = store.presign("job-123/artifact.txt")

        assert url.startswith("file://")
        # Check for the artifact path (handle both forward and back slashes)
        assert "job-123" in url
        assert "artifact.txt" in url


class TestLocalStoreManifest:
    """Tests for LocalStore manifest operations."""

    def test_put_manifest_creates_file(self, tmp_path):
        """Test that put_manifest creates manifest.json."""
        store = LocalStore(tmp_path, "test")
        manifest = create_test_manifest()

        store.put_manifest("job-123", manifest)

        manifest_path = tmp_path / "test" / "job-123" / "manifest.json"
        assert manifest_path.exists()

        data = json.loads(manifest_path.read_text())
        assert data["job_id"] == "test-123"
        assert data["status"] == "SUCCEEDED"

    def test_put_manifest_fails_if_exists(self, tmp_path):
        """Test that put_manifest fails if manifest already exists."""
        store = LocalStore(tmp_path, "test")
        manifest1 = create_test_manifest("job-123", "SUCCEEDED")
        manifest2 = create_test_manifest("job-123", "FAILED")

        store.put_manifest("job-123", manifest1)

        with pytest.raises(ManifestAlreadyExistsError):
            store.put_manifest("job-123", manifest2)

        # Verify original manifest unchanged
        loaded = store.get_manifest("job-123")
        assert loaded.status == "SUCCEEDED"

    def test_get_manifest_returns_manifest(self, tmp_path):
        """Test that get_manifest returns the manifest."""
        store = LocalStore(tmp_path, "test")
        manifest = create_test_manifest()
        store.put_manifest("job-123", manifest)

        loaded = store.get_manifest("job-123")

        assert loaded is not None
        assert loaded.job_id == "test-123"
        assert loaded.status == "SUCCEEDED"

    def test_get_manifest_returns_none_for_missing(self, tmp_path):
        """Test that get_manifest returns None for missing manifest (incomplete job)."""
        store = LocalStore(tmp_path, "test")

        # Create some artifacts but no manifest
        store.put("job-123/artifact.txt", b"content")

        manifest = store.get_manifest("job-123")

        # Missing manifest = incomplete job
        assert manifest is None

    def test_get_manifest_returns_none_for_invalid_json(self, tmp_path):
        """Test that get_manifest returns None for invalid JSON."""
        store = LocalStore(tmp_path, "test")

        # Create invalid manifest file
        manifest_path = tmp_path / "test" / "job-123" / "manifest.json"
        manifest_path.parent.mkdir(parents=True)
        manifest_path.write_text("not valid json")

        manifest = store.get_manifest("job-123")

        assert manifest is None


class TestLocalStoreEvents:
    """Tests for LocalStore event operations."""

    def test_append_event_creates_file(self, tmp_path):
        """Test that append_event creates events.jsonl."""
        store = LocalStore(tmp_path, "test")

        store.append_event("job-123", {"stage": "starting", "percent": 0})

        events_path = tmp_path / "test" / "job-123" / "events.jsonl"
        assert events_path.exists()

        content = events_path.read_text()
        event = json.loads(content.strip())
        assert event["stage"] == "starting"
        assert event["percent"] == 0

    def test_append_event_appends_to_existing(self, tmp_path):
        """Test that append_event appends to existing file."""
        store = LocalStore(tmp_path, "test")

        store.append_event("job-123", {"stage": "starting", "percent": 0})
        store.append_event("job-123", {"stage": "running", "percent": 50})
        store.append_event("job-123", {"stage": "complete", "percent": 100})

        events_path = tmp_path / "test" / "job-123" / "events.jsonl"
        lines = events_path.read_text().strip().split("\n")

        assert len(lines) == 3
        assert json.loads(lines[0])["stage"] == "starting"
        assert json.loads(lines[1])["stage"] == "running"
        assert json.loads(lines[2])["stage"] == "complete"


class TestLocalStoreHeartbeat:
    """Tests for LocalStore heartbeat operations."""

    def test_update_heartbeat_creates_file(self, tmp_path):
        """Test that update_heartbeat creates _heartbeat.json."""
        store = LocalStore(tmp_path, "test")

        heartbeat = {
            "job_id": "job-123",
            "execution_id": "task-1",
            "attempt": 1,
            "last_heartbeat": "2026-02-03T10:00:00Z",
            "stage": "running",
            "percent": 50,
        }
        store.update_heartbeat("job-123", heartbeat)

        heartbeat_path = tmp_path / "test" / "job-123" / "_heartbeat.json"
        assert heartbeat_path.exists()

        data = json.loads(heartbeat_path.read_text())
        assert data["job_id"] == "job-123"
        assert data["stage"] == "running"

    def test_update_heartbeat_overwrites(self, tmp_path):
        """Test that update_heartbeat overwrites existing file."""
        store = LocalStore(tmp_path, "test")

        store.update_heartbeat("job-123", {"stage": "starting", "percent": 0})
        store.update_heartbeat("job-123", {"stage": "running", "percent": 50})

        heartbeat_path = tmp_path / "test" / "job-123" / "_heartbeat.json"
        data = json.loads(heartbeat_path.read_text())

        assert data["stage"] == "running"
        assert data["percent"] == 50


class TestLocalStoreConcurrency:
    """Tests for LocalStore thread safety."""

    def test_concurrent_manifest_writes(self, tmp_path):
        """Test that only one concurrent manifest write succeeds."""
        store = LocalStore(tmp_path, "test")
        results = {"success": 0, "failed": 0}
        lock = threading.Lock()

        def write_manifest(attempt: int):
            manifest = create_test_manifest(f"attempt-{attempt}")
            try:
                store.put_manifest("job-123", manifest)
                with lock:
                    results["success"] += 1
            except ManifestAlreadyExistsError:
                with lock:
                    results["failed"] += 1

        # Start multiple threads trying to write manifest
        threads = [threading.Thread(target=write_manifest, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Only one should succeed
        assert results["success"] == 1
        assert results["failed"] == 4


class TestS3StoreMocked:
    """Tests for S3Store with mocked boto3 client."""

    def test_put_calls_put_object(self):
        """Test that put calls S3 put_object."""
        mock_client = MagicMock()
        store = S3Store("test-bucket", "prod", client=mock_client)

        store.put("job-123/artifact.txt", b"content", "text/plain")

        mock_client.put_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="prod/job-123/artifact.txt",
            Body=b"content",
            ContentType="text/plain",
        )

    def test_get_returns_content(self):
        """Test that get returns S3 object content."""
        mock_client = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"content"
        mock_client.get_object.return_value = {"Body": mock_body}

        store = S3Store("test-bucket", "prod", client=mock_client)

        content = store.get("job-123/artifact.txt")

        assert content == b"content"
        mock_client.get_object.assert_called_once()

    def test_get_returns_none_for_missing(self):
        """Test that get returns None for missing objects."""
        mock_client = MagicMock()
        mock_client.exceptions = MagicMock()
        mock_client.exceptions.NoSuchKey = Exception
        mock_client.get_object.side_effect = mock_client.exceptions.NoSuchKey()

        store = S3Store("test-bucket", "prod", client=mock_client)

        content = store.get("nonexistent.txt")

        assert content is None

    def test_presign_generates_url(self):
        """Test that presign generates presigned URL."""
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = (
            "https://s3.amazonaws.com/test-bucket/prod/job-123/artifact.txt?signature=abc"
        )

        store = S3Store("test-bucket", "prod", client=mock_client)

        url = store.presign("job-123/artifact.txt", expires_in=3600)

        assert url.startswith("https://")
        mock_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "test-bucket", "Key": "prod/job-123/artifact.txt"},
            ExpiresIn=3600,
        )

    def test_put_manifest_uses_if_none_match(self):
        """Test that put_manifest uses If-None-Match for conditional write."""
        mock_client = MagicMock()
        store = S3Store("test-bucket", "prod", client=mock_client)
        manifest = create_test_manifest()

        store.put_manifest("job-123", manifest)

        mock_client.put_object.assert_called_once()
        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs["IfNoneMatch"] == "*"
        assert call_kwargs["Key"] == "prod/job-123/manifest.json"

    def test_put_manifest_raises_on_precondition_failed(self):
        """Test that put_manifest raises ManifestAlreadyExistsError on precondition failure."""
        mock_client = MagicMock()
        error = Exception("PreconditionFailed")
        error.response = {"Error": {"Code": "PreconditionFailed"}}
        mock_client.put_object.side_effect = error

        store = S3Store("test-bucket", "prod", client=mock_client)
        manifest = create_test_manifest()

        with pytest.raises(ManifestAlreadyExistsError):
            store.put_manifest("job-123", manifest)


@pytest.mark.skipif(not _has_module("google.api_core"), reason="google-cloud-storage not installed")
class TestGCSStoreMocked:
    """Tests for GCSStore with mocked GCS client."""

    def test_put_uploads_blob(self):
        """Test that put uploads to GCS blob."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        store = GCSStore("test-bucket", "prod", bucket=mock_bucket)

        store.put("job-123/artifact.txt", b"content", "text/plain")

        mock_bucket.blob.assert_called_once_with("prod/job-123/artifact.txt")
        mock_blob.upload_from_string.assert_called_once_with(b"content", content_type="text/plain")

    def test_put_manifest_uses_generation_match(self):
        """Test that put_manifest uses if_generation_match=0 for conditional write."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        store = GCSStore("test-bucket", "prod", bucket=mock_bucket)
        manifest = create_test_manifest()

        store.put_manifest("job-123", manifest)

        mock_blob.upload_from_string.assert_called_once()
        call_kwargs = mock_blob.upload_from_string.call_args[1]
        assert call_kwargs["if_generation_match"] == 0

    def test_put_manifest_raises_on_precondition_failed(self):
        """Test that put_manifest raises ManifestAlreadyExistsError on precondition failure."""
        from google.api_core.exceptions import PreconditionFailed

        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.upload_from_string.side_effect = PreconditionFailed("Precondition failed")
        mock_bucket.blob.return_value = mock_blob

        store = GCSStore("test-bucket", "prod", bucket=mock_bucket)
        manifest = create_test_manifest()

        with pytest.raises(ManifestAlreadyExistsError):
            store.put_manifest("job-123", manifest)

    def test_presign_generates_signed_url(self):
        """Test that presign generates signed URL."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.generate_signed_url.return_value = (
            "https://storage.googleapis.com/test-bucket/prod/job-123/artifact.txt?signature=abc"
        )
        mock_bucket.blob.return_value = mock_blob

        store = GCSStore("test-bucket", "prod", bucket=mock_bucket)

        url = store.presign("job-123/artifact.txt", expires_in=3600)

        assert url.startswith("https://")
        mock_blob.generate_signed_url.assert_called_once()


@pytest.mark.skipif(not _has_module("azure.core"), reason="azure-storage-blob not installed")
class TestBlobStoreMocked:
    """Tests for BlobStore with mocked Azure client."""

    def test_put_uploads_blob(self):
        """Test that put uploads to Azure Blob."""
        mock_container = MagicMock()
        mock_blob_client = MagicMock()
        mock_container.get_blob_client.return_value = mock_blob_client

        store = BlobStore("test-container", "prod", container_client=mock_container)

        store.put("job-123/artifact.txt", b"content", "text/plain")

        mock_container.get_blob_client.assert_called_once_with("prod/job-123/artifact.txt")
        mock_blob_client.upload_blob.assert_called_once()

    def test_put_manifest_uses_overwrite_false(self):
        """Test that put_manifest uses overwrite=False for conditional write."""
        mock_container = MagicMock()
        mock_blob_client = MagicMock()
        mock_container.get_blob_client.return_value = mock_blob_client

        store = BlobStore("test-container", "prod", container_client=mock_container)
        manifest = create_test_manifest()

        store.put_manifest("job-123", manifest)

        mock_blob_client.upload_blob.assert_called_once()
        call_kwargs = mock_blob_client.upload_blob.call_args[1]
        assert call_kwargs["overwrite"] is False

    def test_put_manifest_raises_on_resource_exists(self):
        """Test that put_manifest raises ManifestAlreadyExistsError on ResourceExistsError."""
        from azure.core.exceptions import ResourceExistsError

        mock_container = MagicMock()
        mock_blob_client = MagicMock()
        mock_blob_client.upload_blob.side_effect = ResourceExistsError("Blob already exists")
        mock_container.get_blob_client.return_value = mock_blob_client

        store = BlobStore("test-container", "prod", container_client=mock_container)
        manifest = create_test_manifest()

        with pytest.raises(ManifestAlreadyExistsError):
            store.put_manifest("job-123", manifest)


class TestCreateStore:
    """Tests for create_store factory function."""

    def test_create_local_store_from_path(self, tmp_path):
        """Test creating LocalStore from file path."""
        store = create_store(str(tmp_path), "test")

        assert isinstance(store, LocalStore)
        assert store.deployment == "test"

    def test_create_local_store_from_file_url(self, tmp_path):
        """Test creating LocalStore from file:// URL."""
        store = create_store(f"file://{tmp_path}", "test")

        assert isinstance(store, LocalStore)

    def test_create_s3_store_from_url(self):
        """Test creating S3Store from s3:// URL."""
        store = create_store("s3://my-bucket", "prod")

        assert isinstance(store, S3Store)
        assert store.bucket == "my-bucket"
        assert store.deployment == "prod"

    def test_create_gcs_store_from_url(self):
        """Test creating GCSStore from gs:// URL."""
        store = create_store("gs://my-bucket", "staging")

        assert isinstance(store, GCSStore)
        assert store.bucket_name == "my-bucket"
        assert store.deployment == "staging"

    def test_create_blob_store_from_url(self):
        """Test creating BlobStore from Azure Blob URL."""
        with patch.dict("os.environ", {"AZURE_STORAGE_CONNECTION_STRING": "test-connection"}):
            store = create_store("https://myaccount.blob.core.windows.net/mycontainer", "dev")

        assert isinstance(store, BlobStore)
        assert store.container_name == "mycontainer"
        assert store.deployment == "dev"

    def test_create_store_raises_for_unsupported_scheme(self):
        """Test that create_store raises ValueError for unsupported schemes."""
        with pytest.raises(ValueError, match="Unsupported storage URL scheme"):
            create_store("ftp://example.com/bucket", "test")


class TestMissingManifestSemantics:
    """Tests for missing manifest = incomplete job semantics."""

    def test_artifacts_without_manifest_is_incomplete(self, tmp_path):
        """Test that artifacts without manifest indicates incomplete job."""
        store = LocalStore(tmp_path, "test")

        # Write some artifacts but no manifest
        store.put("job-123/artifact1.txt", b"content1")
        store.put("job-123/artifact2.txt", b"content2")
        store.append_event("job-123", {"stage": "running", "percent": 50})

        # Job should be considered incomplete
        manifest = store.get_manifest("job-123")
        assert manifest is None

        # But artifacts should still be accessible
        assert store.get("job-123/artifact1.txt") == b"content1"
        assert store.get("job-123/artifact2.txt") == b"content2"

    def test_manifest_presence_indicates_completion(self, tmp_path):
        """Test that manifest presence indicates job completion."""
        store = LocalStore(tmp_path, "test")

        # Write artifacts and manifest
        store.put("job-123/artifact.txt", b"content")
        manifest = create_test_manifest()
        store.put_manifest("job-123", manifest)

        # Job should be considered complete
        loaded = store.get_manifest("job-123")
        assert loaded is not None
        assert loaded.status == "SUCCEEDED"

    def test_failed_job_has_manifest(self, tmp_path):
        """Test that failed jobs also have manifests."""
        store = LocalStore(tmp_path, "test")

        # Write partial artifacts and failed manifest
        store.put("job-123/partial.txt", b"partial content")
        manifest = create_test_manifest(status="FAILED")
        manifest.error = "timeout"
        store.put_manifest("job-123", manifest)

        # Job should be considered complete (even though failed)
        loaded = store.get_manifest("job-123")
        assert loaded is not None
        assert loaded.status == "FAILED"
        assert loaded.error == "timeout"


class TestArtifactStoreProtocol:
    """Tests for ArtifactStore protocol compliance."""

    def test_local_store_implements_protocol(self, tmp_path):
        """Test that LocalStore implements ArtifactStore protocol."""
        store = LocalStore(tmp_path, "test")

        # Check that store has all required methods
        assert hasattr(store, "put")
        assert hasattr(store, "get")
        assert hasattr(store, "list_keys")
        assert hasattr(store, "presign")
        assert hasattr(store, "put_manifest")
        assert hasattr(store, "get_manifest")
        assert hasattr(store, "append_event")
        assert hasattr(store, "update_heartbeat")

        # Check that it's recognized as implementing the protocol
        assert isinstance(store, ArtifactStore)
