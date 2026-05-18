"""
Tests for cloud environment auto-detection and /healthz endpoint.

Covers:
- is_cloud_mode() detection logic
- /healthz endpoint in local mode (always healthy)
- /healthz endpoint in cloud mode (connectivity checks)

Requirements: 2.7, 11.2, 11.3
"""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from deploy.control_plane.api import app, configure_app
from deploy.control_plane.cost_governor import CostGovernor
from deploy.control_plane.job_store import InMemoryJobStore
from deploy.control_plane.queue import InMemoryQueue
from deploy.storage import LocalStore
from primr.mcp_server.cloud_detect import is_cloud_mode

# =============================================================================
# is_cloud_mode() TESTS
# =============================================================================


class TestIsCloudMode:
    """Tests for is_cloud_mode() function."""

    def test_local_mode_when_no_env_vars(self, monkeypatch):
        """Returns False when no Azure env vars are set."""
        monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
        monkeypatch.delenv("COSMOS_ENDPOINT", raising=False)
        monkeypatch.delenv("STORAGE_ACCOUNT_NAME", raising=False)

        assert is_cloud_mode() is False

    def test_cloud_mode_with_azure_client_id(self, monkeypatch):
        """Returns True when AZURE_CLIENT_ID is set."""
        monkeypatch.delenv("COSMOS_ENDPOINT", raising=False)
        monkeypatch.delenv("STORAGE_ACCOUNT_NAME", raising=False)
        monkeypatch.setenv("AZURE_CLIENT_ID", "some-client-id")

        assert is_cloud_mode() is True

    def test_cloud_mode_with_cosmos_endpoint(self, monkeypatch):
        """Returns True when COSMOS_ENDPOINT is set."""
        monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
        monkeypatch.delenv("STORAGE_ACCOUNT_NAME", raising=False)
        monkeypatch.setenv("COSMOS_ENDPOINT", "https://mydb.documents.azure.com:443/")

        assert is_cloud_mode() is True

    def test_cloud_mode_with_storage_account(self, monkeypatch):
        """Returns True when STORAGE_ACCOUNT_NAME is set."""
        monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
        monkeypatch.delenv("COSMOS_ENDPOINT", raising=False)
        monkeypatch.setenv("STORAGE_ACCOUNT_NAME", "mystorageaccount")

        assert is_cloud_mode() is True

    def test_cloud_mode_with_all_vars(self, monkeypatch):
        """Returns True when all Azure env vars are set."""
        monkeypatch.setenv("AZURE_CLIENT_ID", "some-client-id")
        monkeypatch.setenv("COSMOS_ENDPOINT", "https://mydb.documents.azure.com:443/")
        monkeypatch.setenv("STORAGE_ACCOUNT_NAME", "mystorageaccount")

        assert is_cloud_mode() is True

    def test_empty_string_is_not_cloud(self, monkeypatch):
        """Empty string env vars do not trigger cloud mode."""
        monkeypatch.setenv("AZURE_CLIENT_ID", "")
        monkeypatch.delenv("COSMOS_ENDPOINT", raising=False)
        monkeypatch.delenv("STORAGE_ACCOUNT_NAME", raising=False)

        assert is_cloud_mode() is False


# =============================================================================
# /healthz ENDPOINT TESTS
# =============================================================================


@pytest.fixture
def healthz_client(tmp_path, monkeypatch):
    """Create a test client for the /healthz endpoint in local mode."""
    # Ensure local mode
    monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
    monkeypatch.delenv("COSMOS_ENDPOINT", raising=False)
    monkeypatch.delenv("STORAGE_ACCOUNT_NAME", raising=False)

    store = InMemoryJobStore()
    queue = InMemoryQueue()
    artifacts = LocalStore(tmp_path, deployment="test")
    governor = CostGovernor(store)

    configure_app(
        job_store=store,
        queue=queue,
        artifact_store=artifacts,
        cost_governor=governor,
        deployment="test",
    )
    return TestClient(app)


class TestHealthzLocal:
    """Tests for /healthz in local mode."""

    def test_healthz_returns_200_in_local_mode(self, healthz_client):
        """In local mode, /healthz always returns 200 healthy."""
        resp = healthz_client.get("/healthz")
        assert resp.status_code == 200

        data = resp.json()
        assert data["status"] == "healthy"
        assert data["mode"] == "local"

    def test_healthz_no_checks_in_local_mode(self, healthz_client):
        """In local mode, /healthz does not include service checks."""
        resp = healthz_client.get("/healthz")
        data = resp.json()

        # Local mode response should not have checks key
        assert "checks" not in data


class TestHealthzCloud:
    """Tests for /healthz in cloud mode."""

    def test_healthz_returns_cloud_mode_with_checks(self, tmp_path, monkeypatch):
        """In cloud mode, /healthz includes service connectivity checks."""
        monkeypatch.setenv("AZURE_CLIENT_ID", "test-client-id")

        store = InMemoryJobStore()
        queue = InMemoryQueue()
        artifacts = LocalStore(tmp_path, deployment="test")
        governor = CostGovernor(store)

        configure_app(
            job_store=store,
            queue=queue,
            artifact_store=artifacts,
            cost_governor=governor,
            deployment="test",
        )
        client = TestClient(app)

        resp = client.get("/healthz")
        data = resp.json()

        assert data["mode"] == "cloud"
        assert "checks" in data
        assert "cosmos_db" in data["checks"]
        assert "blob_storage" in data["checks"]

    def test_healthz_healthy_when_services_ok(self, tmp_path, monkeypatch):
        """In cloud mode with working services, returns 200 healthy."""
        monkeypatch.setenv("COSMOS_ENDPOINT", "https://test.documents.azure.com:443/")

        store = InMemoryJobStore()
        queue = InMemoryQueue()
        artifacts = LocalStore(tmp_path, deployment="test")
        governor = CostGovernor(store)

        configure_app(
            job_store=store,
            queue=queue,
            artifact_store=artifacts,
            cost_governor=governor,
            deployment="test",
        )
        client = TestClient(app)

        resp = client.get("/healthz")
        assert resp.status_code == 200

        data = resp.json()
        assert data["status"] == "healthy"
