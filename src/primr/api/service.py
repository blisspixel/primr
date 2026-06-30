"""
REST API service for company research.

This module provides:
- FastAPI application for research requests
- Job management and status tracking
- Webhook notifications
- Health checks
- Security headers middleware
- Request ID tracking for audit trails
"""

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from primr.api.auth import verify_api_key
from primr.api.rate_limit import check_rate_limit, get_rate_limiter
from primr.utils.logging_config import get_logger

logger = get_logger("api.service")


# =============================================================================
# SECURITY MIDDLEWARE
# =============================================================================


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to all responses.

    Adds headers recommended by OWASP:
    - X-Content-Type-Options: Prevents MIME sniffing
    - X-Frame-Options: Prevents clickjacking
    - X-XSS-Protection: Legacy XSS protection
    - Strict-Transport-Security: Enforces HTTPS
    - Content-Security-Policy: Restricts resource loading
    - Referrer-Policy: Controls referrer information
    - Permissions-Policy: Restricts browser features
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Legacy XSS protection (for older browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Enforce HTTPS (1 year, include subdomains)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Content Security Policy - restrict to self
        response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"

        # Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Restrict browser features
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        # Remove server identification header if present
        if "server" in response.headers:
            del response.headers["server"]

        return response


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add request ID for tracing and audit logging.

    Generates a unique ID for each request and includes it in:
    - Response header (X-Request-ID)
    - Request state (for logging)
    """

    async def dispatch(self, request: Request, call_next):
        # Use provided request ID or generate new one
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Store in request state for access in handlers
        request.state.request_id = request_id

        # Log the request with ID
        logger.debug(
            f"Request {request_id}: {request.method} {request.url.path}",
            extra={"request_id": request_id},
        )

        response = await call_next(request)

        # Add request ID to response
        response.headers["X-Request-ID"] = request_id

        return response


class ResearchStatus(str, Enum):
    """Status of a research job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResearchRequest(BaseModel):
    """Request to start a research job."""

    company_name: str = Field(
        ..., description="Name of the company to research", min_length=1, max_length=200
    )
    company_url: str | None = Field(None, description="Company website URL", max_length=2048)
    sections: list[str] | None = Field(None, description="Specific sections to include")
    output_format: str = Field("markdown", description="Output format: markdown, html, text")
    webhook_url: str | None = Field(
        None, description="URL for completion notification", max_length=2048
    )
    priority: int = Field(5, ge=1, le=10, description="Priority 1-10 (10 highest)")


class ResearchResponse(BaseModel):
    """Response with research results."""

    job_id: str
    status: ResearchStatus
    company_name: str
    created_at: str
    completed_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    progress: float = 0.0


class JobStatus(BaseModel):
    """Status of a research job."""

    job_id: str
    status: ResearchStatus
    progress: float
    message: str = ""
    created_at: str
    updated_at: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    uptime_seconds: float
    jobs_pending: int
    jobs_completed: int


@dataclass
class ResearchJob:
    """Internal representation of a research job."""

    job_id: str
    company_name: str
    company_url: str | None
    sections: list[str] | None
    output_format: str
    webhook_url: str | None
    priority: int
    status: ResearchStatus = ResearchStatus.PENDING
    progress: float = 0.0
    message: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    api_key: str = ""


class JobManager:
    """
    Manages research jobs.

    Example:
        manager = JobManager()
        job_id = manager.create_job(request, api_key)
        status = manager.get_status(job_id)
    """

    def __init__(self):
        """Initialize the job manager."""
        self._jobs: dict[str, ResearchJob] = {}
        self._lock = threading.Lock()
        self._start_time = datetime.now()
        self._completed_count = 0
        logger.debug("JobManager initialized")

    def create_job(self, request: ResearchRequest, api_key: str) -> str:
        """
        Create a new research job.

        Args:
            request: Research request
            api_key: API key that created the job

        Returns:
            Job ID
        """
        job_id = str(uuid.uuid4())

        job = ResearchJob(
            job_id=job_id,
            company_name=request.company_name,
            company_url=request.company_url,
            sections=request.sections,
            output_format=request.output_format,
            webhook_url=request.webhook_url,
            priority=request.priority,
            api_key=api_key,
        )

        with self._lock:
            self._jobs[job_id] = job

        logger.info(f"Created job {job_id} for {request.company_name}")
        return job_id

    def get_job(self, job_id: str) -> ResearchJob | None:
        """Get a job by ID."""
        with self._lock:
            return self._jobs.get(job_id)

    def update_status(
        self,
        job_id: str,
        status: ResearchStatus,
        progress: float = 0.0,
        message: str = "",
    ) -> None:
        """Update job status."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = status
                job.progress = progress
                job.message = message
                job.updated_at = datetime.now()

                if status == ResearchStatus.COMPLETED:
                    job.completed_at = datetime.now()
                    self._completed_count += 1

    def set_result(self, job_id: str, result: dict[str, Any]) -> None:
        """Set job result."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.result = result
                job.status = ResearchStatus.COMPLETED
                job.progress = 100.0
                job.completed_at = datetime.now()
                job.updated_at = datetime.now()
                self._completed_count += 1

    def set_error(self, job_id: str, error: str) -> None:
        """Set job error."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.error = error
                job.status = ResearchStatus.FAILED
                job.updated_at = datetime.now()

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a job."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.status in (ResearchStatus.PENDING, ResearchStatus.RUNNING):
                job.status = ResearchStatus.CANCELLED
                job.updated_at = datetime.now()
                return True
            return False

    def list_jobs(self, api_key: str, limit: int = 100) -> list[ResearchJob]:
        """List jobs for an API key."""
        with self._lock:
            jobs = [j for j in self._jobs.values() if j.api_key == api_key]
            jobs.sort(key=lambda j: j.created_at, reverse=True)
            return jobs[:limit]

    def get_stats(self) -> dict[str, Any]:
        """Get job statistics."""
        with self._lock:
            pending = sum(1 for j in self._jobs.values() if j.status == ResearchStatus.PENDING)
            running = sum(1 for j in self._jobs.values() if j.status == ResearchStatus.RUNNING)

            return {
                "pending": pending,
                "running": running,
                "completed": self._completed_count,
                "total": len(self._jobs),
                "uptime_seconds": (datetime.now() - self._start_time).total_seconds(),
            }


# =============================================================================
# FASTAPI APPLICATION
# =============================================================================


def create_app(
    title: str = "Company Research API",
    version: str = "1.1.0",
    job_manager: JobManager | None = None,
    allowed_origins: list[str] | None = None,
) -> FastAPI:
    """
    Create the FastAPI application.

    Args:
        title: API title
        version: API version
        job_manager: Optional custom job manager
        allowed_origins: List of allowed CORS origins (default: localhost only)

    Returns:
        FastAPI application
    """
    import os

    app = FastAPI(
        title=title,
        version=version,
        description="REST API for automated company research",
    )

    # Configure CORS with secure defaults
    # In production, set PRIMR_CORS_ORIGINS environment variable
    if allowed_origins is None:
        cors_env = os.environ.get("PRIMR_CORS_ORIGINS", "")
        if cors_env:
            allowed_origins = [o.strip() for o in cors_env.split(",") if o.strip()]
        else:
            # Secure default: only localhost for development
            allowed_origins = [
                "http://localhost:3000",
                "http://localhost:8080",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:8080",
            ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],  # Only methods we actually use
        allow_headers=["X-API-Key", "Content-Type", "Authorization", "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
        max_age=600,  # Cache preflight for 10 minutes
    )

    # Add security headers middleware
    app.add_middleware(SecurityHeadersMiddleware)

    # Add request ID middleware for tracing
    app.add_middleware(RequestIdMiddleware)

    # Store job manager in app state
    app.state.job_manager = job_manager or JobManager()
    app.state.start_time = datetime.now()

    # Dependency for API key verification with rate limit headers
    async def verify_key(
        request: Request,
        response: Response,
        x_api_key: str = Header(..., alias="X-API-Key"),
    ) -> str:
        if not verify_api_key(x_api_key):
            raise HTTPException(status_code=401, detail="Invalid API key")

        # Check rate limit
        allowed, retry_after = check_rate_limit(x_api_key)

        # Add rate limit headers to response
        limiter = get_rate_limiter()
        remaining = limiter.get_remaining(x_api_key)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Limit"] = str(limiter._config.requests_per_hour)

        if not allowed:
            response.headers["X-RateLimit-Reset"] = str(int(retry_after))
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={
                    "Retry-After": str(int(retry_after)),
                    "X-RateLimit-Remaining": "0",
                },
            )

        return x_api_key

    @app.get("/health", response_model=HealthResponse)
    async def health_check():
        """Health check endpoint."""
        stats = app.state.job_manager.get_stats()
        return HealthResponse(
            status="healthy",
            version=version,
            uptime_seconds=stats["uptime_seconds"],
            jobs_pending=stats["pending"],
            jobs_completed=stats["completed"],
        )

    @app.post("/research", response_model=ResearchResponse)
    async def create_research(
        request: ResearchRequest,
        response: Response,
        api_key: str = Depends(verify_key),
    ) -> ResearchResponse:
        """
        Start a new research job.

        Returns immediately with job ID. Use /research/{job_id} to check status.
        """
        from primr.utils.security import (
            sanitize_company_name,
            sanitize_url_input,
            sanitize_webhook_url,
        )

        # Sanitize company name
        safe_name, error = sanitize_company_name(request.company_name)
        if error:
            raise HTTPException(status_code=400, detail=f"Invalid company name: {error}")

        # Sanitize company URL if provided
        if request.company_url:
            safe_url, error = sanitize_url_input(request.company_url)
            if error:
                raise HTTPException(status_code=400, detail=f"Invalid company URL: {error}")
            request.company_url = safe_url

        # Sanitize webhook URL if provided
        if request.webhook_url:
            safe_webhook, error = sanitize_webhook_url(request.webhook_url)
            if error:
                raise HTTPException(status_code=400, detail=f"Invalid webhook URL: {error}")
            request.webhook_url = safe_webhook

        # Update request with sanitized name
        request.company_name = safe_name

        raise HTTPException(
            status_code=501,
            detail=(
                "REST API research submission is not wired to the production pipeline yet. "
                "Use the CLI or MCP server for real runs."
            ),
            headers={
                "X-RateLimit-Remaining": response.headers.get("X-RateLimit-Remaining", "0"),
                "X-RateLimit-Limit": response.headers.get("X-RateLimit-Limit", "0"),
            },
        )

    @app.get("/research/{job_id}", response_model=ResearchResponse)
    async def get_research(job_id: str, api_key: str = Depends(verify_key)) -> ResearchResponse:
        """Get research job status and results."""
        job = app.state.job_manager.get_job(job_id)

        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

        if job.api_key != api_key:
            raise HTTPException(status_code=403, detail="Access denied")

        return ResearchResponse(
            job_id=job.job_id,
            status=job.status,
            company_name=job.company_name,
            created_at=job.created_at.isoformat(),
            completed_at=job.completed_at.isoformat() if job.completed_at else None,
            result=job.result,
            error=job.error,
            progress=job.progress,
        )

    @app.delete("/research/{job_id}")
    async def cancel_research(job_id: str, api_key: str = Depends(verify_key)) -> dict[str, str]:
        """Cancel a research job."""
        job = app.state.job_manager.get_job(job_id)

        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

        if job.api_key != api_key:
            raise HTTPException(status_code=403, detail="Access denied")

        if app.state.job_manager.cancel_job(job_id):
            return {"message": "Job cancelled"}
        else:
            raise HTTPException(status_code=400, detail="Cannot cancel job")

    @app.get("/research", response_model=list[JobStatus])
    async def list_research(
        api_key: str = Depends(verify_key), limit: int = 100
    ) -> list[JobStatus]:
        """List research jobs for the authenticated user."""
        jobs = app.state.job_manager.list_jobs(api_key, limit)

        return [
            JobStatus(
                job_id=j.job_id,
                status=j.status,
                progress=j.progress,
                message=j.message,
                created_at=j.created_at.isoformat(),
                updated_at=j.updated_at.isoformat(),
            )
            for j in jobs
        ]

    return app
