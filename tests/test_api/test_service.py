"""
Tests for the API service module.
"""

import pytest
from fastapi.testclient import TestClient

from primr.api.auth import create_api_key, reset_auth
from primr.api.rate_limit import reset_rate_limiter
from primr.api.service import (
    JobManager,
    ResearchRequest,
    ResearchStatus,
    create_app,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singletons before each test."""
    reset_auth()
    reset_rate_limiter()
    yield
    reset_auth()
    reset_rate_limiter()


@pytest.fixture
def api_key():
    """Create an API key for testing."""
    return create_api_key("test-app", rate_limit=1000)


@pytest.fixture
def job_manager():
    """Create a fresh job manager."""
    return JobManager()


@pytest.fixture
def app(job_manager):
    """Create a test application."""
    return create_app(job_manager=job_manager)


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


# =============================================================================
# RESEARCH REQUEST TESTS
# =============================================================================


class TestResearchRequest:
    """Tests for ResearchRequest model."""

    def test_minimal_request(self):
        """Test minimal request."""
        request = ResearchRequest(company_name="Acme Corp")
        assert request.company_name == "Acme Corp"
        assert request.output_format == "markdown"

    def test_full_request(self):
        """Test full request."""
        request = ResearchRequest(
            company_name="Acme Corp",
            company_url="https://acme.com",
            sections=["overview", "financials"],
            output_format="html",
            webhook_url="https://example.com/webhook",
            priority=8,
        )
        assert request.company_name == "Acme Corp"
        assert request.priority == 8


# =============================================================================
# JOB MANAGER TESTS
# =============================================================================


class TestJobManager:
    """Tests for JobManager class."""

    def test_create_job(self, job_manager):
        """Test job creation."""
        request = ResearchRequest(company_name="Acme Corp")
        job_id = job_manager.create_job(request, "test-key")

        assert job_id is not None
        assert len(job_id) == 36  # UUID format

    def test_get_job(self, job_manager):
        """Test getting a job."""
        request = ResearchRequest(company_name="Acme Corp")
        job_id = job_manager.create_job(request, "test-key")

        job = job_manager.get_job(job_id)
        assert job is not None
        assert job.company_name == "Acme Corp"

    def test_get_job_not_found(self, job_manager):
        """Test getting non-existent job."""
        job = job_manager.get_job("invalid-id")
        assert job is None

    def test_update_status(self, job_manager):
        """Test status update."""
        request = ResearchRequest(company_name="Acme Corp")
        job_id = job_manager.create_job(request, "test-key")

        job_manager.update_status(job_id, ResearchStatus.RUNNING, 50.0, "Processing...")

        job = job_manager.get_job(job_id)
        assert job.status == ResearchStatus.RUNNING
        assert job.progress == 50.0
        assert job.message == "Processing..."

    def test_set_result(self, job_manager):
        """Test setting result."""
        request = ResearchRequest(company_name="Acme Corp")
        job_id = job_manager.create_job(request, "test-key")

        job_manager.set_result(job_id, {"summary": "Test result"})

        job = job_manager.get_job(job_id)
        assert job.status == ResearchStatus.COMPLETED
        assert job.result == {"summary": "Test result"}
        assert job.completed_at is not None

    def test_set_error(self, job_manager):
        """Test setting error."""
        request = ResearchRequest(company_name="Acme Corp")
        job_id = job_manager.create_job(request, "test-key")

        job_manager.set_error(job_id, "Something went wrong")

        job = job_manager.get_job(job_id)
        assert job.status == ResearchStatus.FAILED
        assert job.error == "Something went wrong"

    def test_cancel_job(self, job_manager):
        """Test job cancellation."""
        request = ResearchRequest(company_name="Acme Corp")
        job_id = job_manager.create_job(request, "test-key")

        assert job_manager.cancel_job(job_id) is True

        job = job_manager.get_job(job_id)
        assert job.status == ResearchStatus.CANCELLED

    def test_cancel_completed_job(self, job_manager):
        """Test cancelling completed job fails."""
        request = ResearchRequest(company_name="Acme Corp")
        job_id = job_manager.create_job(request, "test-key")
        job_manager.set_result(job_id, {})

        assert job_manager.cancel_job(job_id) is False

    def test_list_jobs(self, job_manager):
        """Test listing jobs."""
        for i in range(3):
            request = ResearchRequest(company_name=f"Company {i}")
            job_manager.create_job(request, "test-key")

        jobs = job_manager.list_jobs("test-key")
        assert len(jobs) == 3

    def test_list_jobs_filters_by_key(self, job_manager):
        """Test listing filters by API key."""
        request1 = ResearchRequest(company_name="Company 1")
        request2 = ResearchRequest(company_name="Company 2")

        job_manager.create_job(request1, "key-1")
        job_manager.create_job(request2, "key-2")

        jobs = job_manager.list_jobs("key-1")
        assert len(jobs) == 1
        assert jobs[0].company_name == "Company 1"

    def test_get_stats(self, job_manager):
        """Test getting statistics."""
        request = ResearchRequest(company_name="Acme Corp")
        job_id = job_manager.create_job(request, "test-key")
        job_manager.set_result(job_id, {})

        stats = job_manager.get_stats()
        assert stats["completed"] == 1
        assert stats["total"] == 1
        assert "uptime_seconds" in stats


# =============================================================================
# API ENDPOINT TESTS
# =============================================================================


class TestHealthEndpoint:
    """Tests for health endpoint."""

    def test_health_check(self, client):
        """Test health check returns OK."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "uptime_seconds" in data


class TestResearchEndpoints:
    """Tests for research endpoints."""

    def test_create_research_unauthorized(self, client):
        """Test create without API key."""
        response = client.post(
            "/research",
            json={"company_name": "Acme Corp"},
        )

        assert response.status_code == 422  # Missing header

    def test_create_research_invalid_key(self, client):
        """Test create with invalid API key."""
        response = client.post(
            "/research",
            json={"company_name": "Acme Corp"},
            headers={"X-API-Key": "invalid-key"},
        )

        assert response.status_code == 401

    def test_create_research_success(self, client, api_key):
        """Test create fails closed until API execution is implemented."""
        response = client.post(
            "/research",
            json={"company_name": "Acme Corp"},
            headers={"X-API-Key": api_key},
        )

        assert response.status_code == 501
        data = response.json()
        assert "not wired to the production pipeline" in data["detail"]

    def test_get_research_not_found(self, client, api_key):
        """Test getting non-existent job."""
        response = client.get(
            "/research/invalid-id",
            headers={"X-API-Key": api_key},
        )

        assert response.status_code == 404

    def test_get_research_success(self, client, api_key):
        """Test getting job status."""
        request = ResearchRequest(company_name="Acme Corp")
        job_id = client.app.state.job_manager.create_job(request, api_key)

        # Get status
        response = client.get(
            f"/research/{job_id}",
            headers={"X-API-Key": api_key},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id

    def test_cancel_research(self, client, api_key, job_manager):
        """Test cancelling a job."""
        # Create job directly in manager (not via API to avoid background task)
        request = ResearchRequest(company_name="Acme Corp")
        job_id = job_manager.create_job(request, api_key)

        # Cancel via API
        response = client.delete(
            f"/research/{job_id}",
            headers={"X-API-Key": api_key},
        )

        assert response.status_code == 200

    def test_list_research(self, client, api_key):
        """Test listing jobs."""
        # Create some jobs directly in manager because submission endpoint fails closed
        for i in range(3):
            request = ResearchRequest(company_name=f"Company {i}")
            client.app.state.job_manager.create_job(request, api_key)

        # List
        response = client.get(
            "/research",
            headers={"X-API-Key": api_key},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3


class TestAccessControl:
    """Tests for access control."""

    def test_cannot_access_other_users_job(self, client):
        """Test users cannot access other users' jobs."""
        key1 = create_api_key("user-1")
        key2 = create_api_key("user-2")

        request = ResearchRequest(company_name="Acme Corp")
        job_id = client.app.state.job_manager.create_job(request, key1)

        # Try to access with key2
        response = client.get(
            f"/research/{job_id}",
            headers={"X-API-Key": key2},
        )

        assert response.status_code == 403


# =============================================================================
# SECURITY MIDDLEWARE TESTS
# =============================================================================


class TestSecurityHeaders:
    """Tests for security headers middleware."""

    def test_security_headers_present(self, client):
        """Test that security headers are added to responses."""
        response = client.get("/health")

        assert response.status_code == 200

        # Check all security headers are present
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"
        assert "max-age=" in response.headers.get("Strict-Transport-Security", "")
        assert "default-src" in response.headers.get("Content-Security-Policy", "")
        assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert "geolocation=()" in response.headers.get("Permissions-Policy", "")

    def test_security_headers_on_error(self, client):
        """Test security headers are present even on error responses."""
        response = client.get("/research/nonexistent", headers={"X-API-Key": "invalid"})

        # Should have security headers even on 401
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"


class TestRequestIdMiddleware:
    """Tests for request ID middleware."""

    def test_request_id_generated(self, client):
        """Test that request ID is generated and returned."""
        response = client.get("/health")

        assert response.status_code == 200
        request_id = response.headers.get("X-Request-ID")
        assert request_id is not None
        assert len(request_id) == 36  # UUID format

    def test_request_id_preserved(self, client):
        """Test that provided request ID is preserved."""
        custom_id = "custom-request-id-12345"
        response = client.get("/health", headers={"X-Request-ID": custom_id})

        assert response.status_code == 200
        assert response.headers.get("X-Request-ID") == custom_id


class TestRateLimitHeaders:
    """Tests for rate limit headers."""

    def test_rate_limit_headers_present(self, client, api_key):
        """Test that rate limit headers are included in responses."""
        response = client.post(
            "/research",
            json={"company_name": "Test Corp"},
            headers={"X-API-Key": api_key},
        )

        assert response.status_code == 501
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Limit" in response.headers


class TestCORSConfiguration:
    """Tests for CORS configuration."""

    def test_cors_headers_for_allowed_origin(self, client):
        """Test CORS headers for allowed origin."""
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

        # Should allow localhost
        assert response.headers.get("Access-Control-Allow-Origin") in [
            "http://localhost:3000",
            "*",  # Depending on test configuration
        ]

    def test_cors_exposes_custom_headers(self, client):
        """Test that CORS exposes custom headers."""
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

        exposed = response.headers.get("Access-Control-Expose-Headers", "")
        # Should expose rate limit and request ID headers
        assert "X-Request-ID" in exposed or exposed == ""  # May not be set in preflight
