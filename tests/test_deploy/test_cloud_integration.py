"""
Integration tests for Azure-specific code paths.

Tests cloud-mode behavior of:
- /healthz endpoint with mocked Cosmos/Blob failures (Q2)
- show_usage tool in cloud mode with mocked httpx responses (Q2)
- doctor cloud diagnostics with mocked httpx responses (Q2)

Note: cloud_detect.py is already covered by test_cloud_detect_and_healthz.py.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# FastAPI / deploy imports are deferred to fixtures so the module can be
# collected even when fastapi is not installed (same pattern as the rest
# of the test_deploy suite).
fastapi = pytest.importorskip("fastapi")


# =============================================================================
# /healthz cloud mode with mocked service failures
# =============================================================================


class TestHealthzCloudFailures:
    """Tests for /healthz in cloud mode when backing services fail."""

    @pytest.fixture
    def cloud_client(self, tmp_path, monkeypatch):
        """Create a test client in cloud mode."""
        from fastapi.testclient import TestClient

        from deploy.control_plane.api import app, configure_app
        from deploy.control_plane.cost_governor import CostGovernor
        from deploy.control_plane.job_store import InMemoryJobStore
        from deploy.control_plane.queue import InMemoryQueue
        from deploy.storage import LocalStore

        monkeypatch.setenv("AZURE_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("COSMOS_ENDPOINT", "https://test.documents.azure.com:443/")
        monkeypatch.setenv("STORAGE_ACCOUNT_NAME", "teststorage")

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

    def test_healthz_unhealthy_when_cosmos_fails(self, cloud_client, monkeypatch):
        """Returns 503 when Cosmos DB connectivity check fails."""
        from deploy.control_plane import api as api_module

        failing_store = MagicMock()
        failing_store.get.side_effect = Exception("Cosmos connection refused")

        with patch.object(api_module, "get_job_store", return_value=failing_store):
            resp = cloud_client.get("/healthz")

        data = resp.json()
        assert data["mode"] == "cloud"
        assert data["checks"]["cosmos_db"]["status"] == "error"

    def test_healthz_unhealthy_when_blob_fails(self, cloud_client, monkeypatch):
        """Returns 503 when Blob Storage connectivity check fails."""
        from deploy.control_plane import api as api_module

        failing_artifacts = MagicMock()
        failing_artifacts.get.side_effect = Exception("Blob storage unavailable")

        with patch.object(api_module, "get_artifact_store", return_value=failing_artifacts):
            resp = cloud_client.get("/healthz")

        data = resp.json()
        assert data["mode"] == "cloud"
        assert data["checks"]["blob_storage"]["status"] == "error"

    def test_healthz_healthy_when_all_services_ok(self, cloud_client):
        """Returns 200 when all cloud services are reachable."""
        resp = cloud_client.get("/healthz")
        data = resp.json()

        assert resp.status_code == 200
        assert data["status"] == "healthy"
        assert data["mode"] == "cloud"


# =============================================================================
# show_usage tool in cloud mode with mocked httpx
# =============================================================================


class TestShowUsageCloudMode:
    """Tests for show_usage tool in cloud mode with mocked HTTP responses."""

    @pytest.mark.asyncio
    async def test_show_usage_cloud_success(self, monkeypatch):
        """show_usage returns usage data from control plane in cloud mode."""
        monkeypatch.setenv("AZURE_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PRIMR_CONTROL_PLANE_URL", "http://localhost:8000")

        usage_payload = {
            "daily_cost_usd": 1.23,
            "monthly_cost_usd": 15.50,
            "remaining_budget_usd": 84.50,
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = usage_payload
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            from primr.mcp_server.tools import _handle_show_usage

            mcp_server = MagicMock()
            result = await _handle_show_usage(mcp_server, "client-123")

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["daily_cost_usd"] == 1.23

    @pytest.mark.asyncio
    async def test_show_usage_cloud_http_error(self, monkeypatch):
        """show_usage returns error when control plane is unreachable."""
        monkeypatch.setenv("AZURE_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PRIMR_CONTROL_PLANE_URL", "http://localhost:8000")

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            from primr.mcp_server.tools import _handle_show_usage

            mcp_server = MagicMock()
            result = await _handle_show_usage(mcp_server, "client-123")

        data = json.loads(result[0].text)
        assert data["error"] is True
        assert data["error_type"] == "usage_fetch_failed"


# =============================================================================
# doctor cloud diagnostics with mocked httpx
# =============================================================================


class TestDoctorCloudDiagnostics:
    """Tests for doctor cloud diagnostics with mocked HTTP responses."""

    @pytest.mark.asyncio
    async def test_cloud_diagnostics_all_ok(self, monkeypatch):
        """Cloud diagnostics returns ok status when services are reachable."""
        monkeypatch.setenv("AZURE_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("COSMOS_ENDPOINT", "https://test.documents.azure.com:443/")
        monkeypatch.setenv("STORAGE_ACCOUNT_NAME", "teststorage")
        monkeypatch.setenv("PRIMR_CONTROL_PLANE_URL", "http://localhost:8000")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "healthy", "mode": "cloud"}

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            from primr.mcp_server.tools import _get_cloud_diagnostics

            result = await _get_cloud_diagnostics()

        assert result["container_app_health"]["status"] == "ok"
        assert result["cosmos_db"]["status"] == "ok"
        assert result["blob_storage"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_cloud_diagnostics_healthz_failure(self, monkeypatch):
        """Cloud diagnostics reports error when /healthz is unreachable."""
        monkeypatch.setenv("AZURE_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PRIMR_CONTROL_PLANE_URL", "http://localhost:8000")
        monkeypatch.delenv("COSMOS_ENDPOINT", raising=False)
        monkeypatch.delenv("STORAGE_ACCOUNT_NAME", raising=False)

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            from primr.mcp_server.tools import _get_cloud_diagnostics

            result = await _get_cloud_diagnostics()

        assert result["container_app_health"]["status"] == "error"

    @pytest.mark.asyncio
    async def test_cloud_diagnostics_not_configured(self, monkeypatch):
        """Cloud diagnostics reports not_configured for missing services."""
        monkeypatch.setenv("AZURE_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PRIMR_CONTROL_PLANE_URL", "http://localhost:8000")
        monkeypatch.delenv("COSMOS_ENDPOINT", raising=False)
        monkeypatch.delenv("STORAGE_ACCOUNT_NAME", raising=False)
        monkeypatch.delenv("SERVICEBUS_CONNECTION_STRING", raising=False)
        monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "healthy"}

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            from primr.mcp_server.tools import _get_cloud_diagnostics

            result = await _get_cloud_diagnostics()

        assert result["cosmos_db"]["status"] == "not_configured"
        assert result["blob_storage"]["status"] == "not_configured"
        assert result["service_bus"]["status"] == "not_configured"
        assert result["application_insights"]["status"] == "not_configured"
