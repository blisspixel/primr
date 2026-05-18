"""
Artifact Storage Abstraction - Storage backends for job artifacts.

This module provides a unified interface for artifact storage across different
cloud providers (S3, Azure Blob, GCS) and local filesystem for testing.

Key features:
- ArtifactStore protocol defining the storage interface
- LocalStore for local testing with atomic writes
- S3Store for AWS S3 with conditional manifest writes (If-None-Match)
- BlobStore for Azure Blob Storage with conditional writes (IfNoneMatch)
- GCSStore for Google Cloud Storage with conditional writes (generation=0)
- Manifest-as-commit pattern: manifest written LAST with conditional check
- Presigned URL generation for secure artifact retrieval

Requirements: 2.1, 2.4, 2.5, 2.8, 2.11, 2.12
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlparse

# Import manifest types
from deploy.manifest import JobManifest, ManifestAlreadyExistsError


def format_timestamp(dt: datetime) -> str:
    """Format datetime as ISO 8601 string."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now() -> datetime:
    """Get current UTC time."""
    return datetime.now(timezone.utc)


@runtime_checkable
class ArtifactStore(Protocol):
    """
    Protocol for artifact storage backends.

    All implementations must support:
    - Atomic artifact writes
    - Conditional manifest writes (fail if exists)
    - Presigned URL generation
    - Event appending for progress tracking
    - Heartbeat updates for liveness
    """

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        """
        Write artifact atomically.

        Args:
            key: Object key (path within the store)
            data: Artifact content as bytes
            content_type: MIME type of the content
        """
        ...

    def get(self, key: str) -> bytes | None:
        """
        Get artifact content.

        Args:
            key: Object key (path within the store)

        Returns:
            Artifact content as bytes, or None if not found
        """
        ...

    def list_keys(self, prefix: str) -> list[str]:
        """
        List all keys with the given prefix.

        Args:
            prefix: Key prefix to filter by

        Returns:
            List of matching keys
        """
        ...

    def presign(self, key: str, expires_in: int = 3600) -> str:
        """
        Generate a presigned URL for artifact retrieval.

        Args:
            key: Object key (path within the store)
            expires_in: URL expiration time in seconds (default 1 hour)

        Returns:
            Presigned URL string
        """
        ...

    def put_manifest(self, job_id: str, manifest: JobManifest) -> None:
        """
        Write manifest with conditional check (fails if exists).

        This implements the manifest-as-commit pattern where the manifest
        is written LAST after all artifacts are complete. The conditional
        write ensures only one runner can successfully write the manifest.

        Args:
            job_id: Job identifier
            manifest: JobManifest to write

        Raises:
            ManifestAlreadyExistsError: If manifest already exists
        """
        ...

    def get_manifest(self, job_id: str) -> JobManifest | None:
        """
        Get manifest for a job.

        Returns None if manifest doesn't exist (job incomplete).

        Args:
            job_id: Job identifier

        Returns:
            JobManifest if exists, None otherwise
        """
        ...

    def append_event(self, job_id: str, event: dict[str, Any]) -> None:
        """
        Append event to events.jsonl for progress tracking.

        Args:
            job_id: Job identifier
            event: Event data to append (will be JSON serialized)
        """
        ...

    def update_heartbeat(self, job_id: str, heartbeat: dict[str, Any]) -> None:
        """
        Update heartbeat file for liveness tracking.

        Args:
            job_id: Job identifier
            heartbeat: Heartbeat data (will be JSON serialized)
        """
        ...


class LocalStore:
    """
    Local filesystem artifact store for testing.

    Uses temp file + rename for atomic writes.
    Implements conditional manifest writes by checking existence before write.
    """

    def __init__(self, base_path: str | Path, deployment: str = "local") -> None:
        """
        Initialize local store.

        Args:
            base_path: Base directory for artifact storage
            deployment: Deployment namespace (e.g., dev, staging, prod)
        """
        self.base_path = Path(base_path)
        self.deployment = deployment
        self._lock = threading.Lock()

        # Ensure base path exists
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_path(self, key: str) -> Path:
        """Get full path for a key."""
        return self.base_path / self.deployment / key

    def _get_job_path(self, job_id: str) -> Path:
        """Get path for a job's artifacts."""
        return self.base_path / self.deployment / job_id

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        """Write artifact atomically using temp file + rename."""
        path = self._get_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write to temp file first, then rename for atomicity
        fd, temp_path = tempfile.mkstemp(
            suffix=".tmp",
            prefix="artifact_",
            dir=path.parent,
        )
        try:
            os.close(fd)
            temp_file = Path(temp_path)
            temp_file.write_bytes(data)
            # Use replace() instead of rename() to allow overwriting on Windows
            temp_file.replace(path)
        except Exception:
            # Clean up temp file on error
            try:
                Path(temp_path).unlink()
            except OSError:
                pass
            raise

    def get(self, key: str) -> bytes | None:
        """Get artifact content, returns None if not found."""
        path = self._get_path(key)
        if not path.exists():
            return None
        try:
            return path.read_bytes()
        except OSError:
            return None

    def list_keys(self, prefix: str) -> list[str]:
        """List all keys with the given prefix."""
        base = self.base_path / self.deployment
        if not base.exists():
            return []

        keys = []
        prefix_path = base / prefix if prefix else base

        # If prefix is a directory, list its contents
        if prefix_path.is_dir():
            for path in prefix_path.rglob("*"):
                if path.is_file():
                    rel_path = path.relative_to(base)
                    # Always use forward slashes for consistency
                    keys.append(str(rel_path).replace("\\", "/"))
        else:
            # List files matching the prefix
            parent = prefix_path.parent
            if parent.exists():
                for path in parent.iterdir():
                    rel_str = str(path.relative_to(base)).replace("\\", "/")
                    if path.is_file() and rel_str.startswith(prefix):
                        keys.append(rel_str)

        return sorted(keys)

    def presign(self, key: str, expires_in: int = 3600) -> str:
        """
        Generate a 'presigned' URL for local files.

        For local testing, returns a file:// URL.
        """
        path = self._get_path(key)
        return f"file://{path.absolute()}"

    def put_manifest(self, job_id: str, manifest: JobManifest) -> None:
        """
        Write manifest with conditional check (fails if exists).

        Uses temp file + rename for atomicity, with existence check.
        """
        manifest_path = self._get_job_path(job_id) / "manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)

        with self._lock:
            # Check if manifest already exists (conditional create)
            if manifest_path.exists():
                raise ManifestAlreadyExistsError(f"Manifest for {job_id} already exists")

            # Write to temp file first
            fd, temp_path = tempfile.mkstemp(
                suffix=".json",
                prefix="manifest_",
                dir=manifest_path.parent,
            )
            try:
                os.close(fd)
                temp_file = Path(temp_path)
                temp_file.write_text(manifest.to_json())

                # Check again before rename (minimize race window)
                if manifest_path.exists():
                    temp_file.unlink()
                    raise ManifestAlreadyExistsError(f"Manifest for {job_id} already exists")

                temp_file.rename(manifest_path)
            except ManifestAlreadyExistsError:
                raise
            except Exception:
                # Clean up temp file on error
                try:
                    Path(temp_path).unlink()
                except OSError:
                    pass
                raise

    def get_manifest(self, job_id: str) -> JobManifest | None:
        """Get manifest, returns None if job incomplete."""
        manifest_path = self._get_job_path(job_id) / "manifest.json"
        return JobManifest.load(manifest_path)

    def append_event(self, job_id: str, event: dict[str, Any]) -> None:
        """Append event to events.jsonl."""
        events_path = self._get_job_path(job_id) / "events.jsonl"
        events_path.parent.mkdir(parents=True, exist_ok=True)

        with self._lock, open(events_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    def update_heartbeat(self, job_id: str, heartbeat: dict[str, Any]) -> None:
        """Update heartbeat file atomically."""
        heartbeat_path = self._get_job_path(job_id) / "_heartbeat.json"
        heartbeat_path.parent.mkdir(parents=True, exist_ok=True)

        # Write atomically via temp file
        fd, temp_path = tempfile.mkstemp(
            suffix=".json",
            prefix="heartbeat_",
            dir=heartbeat_path.parent,
        )
        try:
            os.close(fd)
            temp_file = Path(temp_path)
            temp_file.write_text(json.dumps(heartbeat, indent=2))
            # Use replace() instead of rename() to allow overwriting on Windows
            temp_file.replace(heartbeat_path)
        except Exception:
            try:
                Path(temp_path).unlink()
            except OSError:
                pass
            raise


class S3Store:
    """
    AWS S3 artifact store.

    Uses If-None-Match: * for conditional manifest writes.
    """

    def __init__(
        self,
        bucket: str,
        deployment: str,
        region: str | None = None,
        client: Any = None,
    ) -> None:
        """
        Initialize S3 store.

        Args:
            bucket: S3 bucket name
            deployment: Deployment namespace (prefix)
            region: AWS region (optional, uses default if not specified)
            client: Optional boto3 S3 client (for testing/injection)
        """
        self.bucket = bucket
        self.deployment = deployment
        self.region = region

        if client is not None:
            self._client = client
        else:
            self._client = None  # Lazy initialization

    @property
    def client(self) -> Any:
        """Get or create boto3 S3 client."""
        if self._client is None:
            import boto3

            self._client = boto3.client("s3", region_name=self.region)
        return self._client

    def _get_key(self, key: str) -> str:
        """Get full S3 key with deployment prefix."""
        return f"{self.deployment}/{key}"

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        """Write artifact to S3."""
        self.client.put_object(
            Bucket=self.bucket,
            Key=self._get_key(key),
            Body=data,
            ContentType=content_type,
        )

    def get(self, key: str) -> bytes | None:
        """Get artifact from S3, returns None if not found."""
        try:
            response = self.client.get_object(
                Bucket=self.bucket,
                Key=self._get_key(key),
            )
            return response["Body"].read()
        except self.client.exceptions.NoSuchKey:
            return None
        except Exception as e:
            # Handle ClientError for NoSuchKey
            if hasattr(e, "response") and e.response.get("Error", {}).get("Code") == "NoSuchKey":
                return None
            raise

    def list_keys(self, prefix: str) -> list[str]:
        """List all keys with the given prefix."""
        full_prefix = self._get_key(prefix)
        keys = []

        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=full_prefix):
            for obj in page.get("Contents", []):
                # Remove deployment prefix from key
                key = obj["Key"]
                if key.startswith(f"{self.deployment}/"):
                    key = key[len(f"{self.deployment}/") :]
                keys.append(key)

        return keys

    def presign(self, key: str, expires_in: int = 3600) -> str:
        """Generate presigned URL for S3 object."""
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": self._get_key(key)},
            ExpiresIn=expires_in,
        )

    def put_manifest(self, job_id: str, manifest: JobManifest) -> None:
        """
        Write manifest with conditional check (If-None-Match: *).

        Fails if manifest already exists.
        """
        key = self._get_key(f"{job_id}/manifest.json")

        try:
            # Conditional write: fail if object already exists
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=manifest.to_json().encode("utf-8"),
                ContentType="application/json",
                IfNoneMatch="*",  # Only write if object doesn't exist
            )
        except Exception as e:
            # Check for PreconditionFailed error
            if hasattr(e, "response"):
                error_code = e.response.get("Error", {}).get("Code", "")
                if error_code == "PreconditionFailed":
                    raise ManifestAlreadyExistsError(f"Manifest for {job_id} already exists") from e
            raise

    def get_manifest(self, job_id: str) -> JobManifest | None:
        """Get manifest from S3, returns None if not found."""
        data = self.get(f"{job_id}/manifest.json")
        if data is None:
            return None
        try:
            return JobManifest.from_dict(json.loads(data.decode("utf-8")))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def append_event(self, job_id: str, event: dict[str, Any]) -> None:
        """
        Append event to events.jsonl.

        Note: S3 doesn't support true append, so we read-modify-write.
        For high-frequency updates, consider using a different approach.
        """
        key = f"{job_id}/events.jsonl"
        existing = self.get(key)

        if existing:
            content = existing.decode("utf-8") + json.dumps(event) + "\n"
        else:
            content = json.dumps(event) + "\n"

        self.put(key, content.encode("utf-8"), "application/x-ndjson")

    def update_heartbeat(self, job_id: str, heartbeat: dict[str, Any]) -> None:
        """Update heartbeat file in S3."""
        self.put(
            f"{job_id}/_heartbeat.json",
            json.dumps(heartbeat, indent=2).encode("utf-8"),
            "application/json",
        )


class BlobStore:
    """
    Azure Blob Storage artifact store.

    Uses IfNoneMatch="*" for conditional manifest writes.
    """

    def __init__(
        self,
        container_name: str,
        deployment: str,
        connection_string: str | None = None,
        container_client: Any = None,
    ) -> None:
        """
        Initialize Azure Blob store.

        Args:
            container_name: Azure Blob container name
            deployment: Deployment namespace (prefix)
            connection_string: Azure Storage connection string
            container_client: Optional container client (for testing/injection)
        """
        self.container_name = container_name
        self.deployment = deployment
        self.connection_string = connection_string

        if container_client is not None:
            self._container_client = container_client
        else:
            self._container_client = None  # Lazy initialization

    @property
    def container_client(self) -> Any:
        """Get or create Azure container client."""
        if self._container_client is None:
            from azure.storage.blob import ContainerClient

            self._container_client = ContainerClient.from_connection_string(
                self.connection_string,
                container_name=self.container_name,
            )
        return self._container_client

    def _get_blob_name(self, key: str) -> str:
        """Get full blob name with deployment prefix."""
        return f"{self.deployment}/{key}"

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        """Write artifact to Azure Blob."""
        from azure.storage.blob import ContentSettings

        blob_client = self.container_client.get_blob_client(self._get_blob_name(key))
        blob_client.upload_blob(
            data,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )

    def get(self, key: str) -> bytes | None:
        """Get artifact from Azure Blob, returns None if not found."""
        try:
            blob_client = self.container_client.get_blob_client(self._get_blob_name(key))
            return blob_client.download_blob().readall()
        except Exception as e:
            # Check for BlobNotFound
            if "BlobNotFound" in str(e) or "ResourceNotFoundError" in str(type(e)):
                return None
            raise

    def list_keys(self, prefix: str) -> list[str]:
        """List all keys with the given prefix."""
        full_prefix = self._get_blob_name(prefix)
        keys = []

        for blob in self.container_client.list_blobs(name_starts_with=full_prefix):
            # Remove deployment prefix from name
            name = blob.name
            if name.startswith(f"{self.deployment}/"):
                name = name[len(f"{self.deployment}/") :]
            keys.append(name)

        return keys

    def presign(self, key: str, expires_in: int = 3600) -> str:
        """Generate SAS URL for Azure Blob."""
        from azure.storage.blob import BlobSasPermissions, generate_blob_sas

        blob_client = self.container_client.get_blob_client(self._get_blob_name(key))

        # Generate SAS token
        sas_token = generate_blob_sas(
            account_name=blob_client.account_name,
            container_name=self.container_name,
            blob_name=self._get_blob_name(key),
            account_key=blob_client.credential.account_key
            if hasattr(blob_client.credential, "account_key")
            else None,
            permission=BlobSasPermissions(read=True),
            expiry=utc_now() + timedelta(seconds=expires_in),
        )

        return f"{blob_client.url}?{sas_token}"

    def put_manifest(self, job_id: str, manifest: JobManifest) -> None:
        """
        Write manifest with conditional check (IfNoneMatch="*").

        Fails if manifest already exists.
        """
        from azure.core.exceptions import ResourceExistsError
        from azure.storage.blob import ContentSettings

        blob_name = self._get_blob_name(f"{job_id}/manifest.json")
        blob_client = self.container_client.get_blob_client(blob_name)

        try:
            # Conditional write: fail if blob already exists
            blob_client.upload_blob(
                manifest.to_json(),
                content_settings=ContentSettings(content_type="application/json"),
                overwrite=False,  # This is equivalent to IfNoneMatch="*"
            )
        except ResourceExistsError as e:
            raise ManifestAlreadyExistsError(f"Manifest for {job_id} already exists") from e

    def get_manifest(self, job_id: str) -> JobManifest | None:
        """Get manifest from Azure Blob, returns None if not found."""
        data = self.get(f"{job_id}/manifest.json")
        if data is None:
            return None
        try:
            return JobManifest.from_dict(json.loads(data.decode("utf-8")))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def append_event(self, job_id: str, event: dict[str, Any]) -> None:
        """
        Append event to events.jsonl.

        Note: Azure Blob doesn't support true append for block blobs,
        so we read-modify-write. For append blobs, use append_block.
        """
        key = f"{job_id}/events.jsonl"
        existing = self.get(key)

        if existing:
            content = existing.decode("utf-8") + json.dumps(event) + "\n"
        else:
            content = json.dumps(event) + "\n"

        self.put(key, content.encode("utf-8"), "application/x-ndjson")

    def update_heartbeat(self, job_id: str, heartbeat: dict[str, Any]) -> None:
        """Update heartbeat file in Azure Blob."""
        self.put(
            f"{job_id}/_heartbeat.json",
            json.dumps(heartbeat, indent=2).encode("utf-8"),
            "application/json",
        )


class GCSStore:
    """
    Google Cloud Storage artifact store.

    Uses if_generation_match=0 for conditional manifest writes.
    """

    def __init__(
        self,
        bucket_name: str,
        deployment: str,
        project: str | None = None,
        bucket: Any = None,
    ) -> None:
        """
        Initialize GCS store.

        Args:
            bucket_name: GCS bucket name
            deployment: Deployment namespace (prefix)
            project: GCP project ID (optional)
            bucket: Optional GCS bucket object (for testing/injection)
        """
        self.bucket_name = bucket_name
        self.deployment = deployment
        self.project = project

        if bucket is not None:
            self._bucket = bucket
        else:
            self._bucket = None  # Lazy initialization

    @property
    def bucket(self) -> Any:
        """Get or create GCS bucket object."""
        if self._bucket is None:
            from google.cloud import storage

            client = storage.Client(project=self.project)
            self._bucket = client.bucket(self.bucket_name)
        return self._bucket

    def _get_blob_name(self, key: str) -> str:
        """Get full blob name with deployment prefix."""
        return f"{self.deployment}/{key}"

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        """Write artifact to GCS."""
        blob = self.bucket.blob(self._get_blob_name(key))
        blob.upload_from_string(data, content_type=content_type)

    def get(self, key: str) -> bytes | None:
        """Get artifact from GCS, returns None if not found."""
        try:
            blob = self.bucket.blob(self._get_blob_name(key))
            return blob.download_as_bytes()
        except Exception as e:
            # Check for NotFound
            if "NotFound" in str(type(e)) or "404" in str(e):
                return None
            raise

    def list_keys(self, prefix: str) -> list[str]:
        """List all keys with the given prefix."""
        full_prefix = self._get_blob_name(prefix)
        keys = []

        for blob in self.bucket.list_blobs(prefix=full_prefix):
            # Remove deployment prefix from name
            name = blob.name
            if name.startswith(f"{self.deployment}/"):
                name = name[len(f"{self.deployment}/") :]
            keys.append(name)

        return keys

    def presign(self, key: str, expires_in: int = 3600) -> str:
        """Generate signed URL for GCS object."""
        blob = self.bucket.blob(self._get_blob_name(key))
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=expires_in),
            method="GET",
        )

    def put_manifest(self, job_id: str, manifest: JobManifest) -> None:
        """
        Write manifest with conditional check (if_generation_match=0).

        if_generation_match=0 means "only if object doesn't exist".
        Fails if manifest already exists.
        """
        from google.api_core.exceptions import PreconditionFailed

        blob = self.bucket.blob(self._get_blob_name(f"{job_id}/manifest.json"))

        try:
            # Conditional write: fail if blob already exists
            # if_generation_match=0 means "only create if doesn't exist"
            blob.upload_from_string(
                manifest.to_json(),
                content_type="application/json",
                if_generation_match=0,
            )
        except PreconditionFailed as e:
            raise ManifestAlreadyExistsError(f"Manifest for {job_id} already exists") from e

    def get_manifest(self, job_id: str) -> JobManifest | None:
        """Get manifest from GCS, returns None if not found."""
        data = self.get(f"{job_id}/manifest.json")
        if data is None:
            return None
        try:
            return JobManifest.from_dict(json.loads(data.decode("utf-8")))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def append_event(self, job_id: str, event: dict[str, Any]) -> None:
        """
        Append event to events.jsonl.

        Note: GCS doesn't support true append, so we read-modify-write.
        For high-frequency updates, consider using Cloud Pub/Sub or Firestore.
        """
        key = f"{job_id}/events.jsonl"
        existing = self.get(key)

        if existing:
            content = existing.decode("utf-8") + json.dumps(event) + "\n"
        else:
            content = json.dumps(event) + "\n"

        self.put(key, content.encode("utf-8"), "application/x-ndjson")

    def update_heartbeat(self, job_id: str, heartbeat: dict[str, Any]) -> None:
        """Update heartbeat file in GCS."""
        self.put(
            f"{job_id}/_heartbeat.json",
            json.dumps(heartbeat, indent=2).encode("utf-8"),
            "application/json",
        )


def create_store(url: str, deployment: str = "default") -> ArtifactStore:
    """
    Factory function to create appropriate store based on URL scheme.

    Supported URL schemes:
    - file:///path/to/dir -> LocalStore
    - /path/to/dir or C:\\path\\to\\dir -> LocalStore (plain paths)
    - s3://bucket-name -> S3Store
    - gs://bucket-name -> GCSStore
    - https://*.blob.core.windows.net/container -> BlobStore

    Args:
        url: Storage URL
        deployment: Deployment namespace

    Returns:
        Appropriate ArtifactStore implementation

    Raises:
        ValueError: If URL scheme is not supported
    """
    parsed = urlparse(url)

    # Handle Windows drive letters (e.g., C:\path) - urlparse treats C: as scheme
    if len(parsed.scheme) == 1 and parsed.scheme.isalpha():
        # This is a Windows path like C:\path\to\dir
        return LocalStore(url, deployment)

    if parsed.scheme == "file":
        # file:// URL - extract the path
        # On Windows, file:///C:/path becomes /C:/path, need to strip leading /
        path = parsed.path
        if path.startswith("/") and len(path) > 2 and path[2] == ":":
            path = path[1:]  # Remove leading / for Windows paths
        return LocalStore(path, deployment)

    if parsed.scheme == "":
        # Plain path (Unix-style or relative)
        return LocalStore(url, deployment)

    if parsed.scheme == "s3":
        # AWS S3
        bucket = parsed.netloc
        return S3Store(bucket, deployment)

    if parsed.scheme == "gs":
        # Google Cloud Storage
        bucket = parsed.netloc
        return GCSStore(bucket, deployment)

    if parsed.scheme in ("https", "http") and ".blob.core.windows.net" in parsed.netloc:
        # Azure Blob Storage
        # URL format: https://<account>.blob.core.windows.net/<container>
        parts = parsed.path.strip("/").split("/")
        container = parts[0] if parts else "artifacts"
        # Connection string would need to be provided via environment
        connection_string = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
        return BlobStore(container, deployment, connection_string)

    raise ValueError(f"Unsupported storage URL scheme: {parsed.scheme}")
