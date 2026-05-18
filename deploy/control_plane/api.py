"""
Control Plane API - FastAPI application for job management.

This module provides the REST API for the control plane:
- POST /submit - create job with idempotency
- GET /status/{job_id} - return job state + last_event
- POST /approve/{job_id} - approve pending job
- POST /cancel/{job_id} - request cancellation
- GET /results/{job_id} - return manifest + presigned URLs

The control plane requires NO LLM keys - only JWT, job store, queue, presign.

Requirements: 3.1, 3.2, 3.3, 3.9, 3.10, 3.11, 3.12, 3.15, 3.16, 3.17, 3.19, 3.20
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import json
import logging
import os
import time
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from deploy.control_plane.budget_tracker import (
    BudgetExceededError,
    BudgetTracker,
)
from deploy.control_plane.cancellation import CancellationService
from deploy.control_plane.cost_governor import (
    CostGovernor,
    QuotaExceededError,
    estimate_cost,
)
from deploy.control_plane.job_store import (
    ConditionalCheckFailedError,
    InMemoryJobStore,
    JobRecord,
    JobStatus,
    JobStore,
    JobTiming,
    canonicalize_inputs,
    format_timestamp,
    get_expected_artifacts,
    hash_api_key,
    hash_inputs,
    hash_job_id,
    utc_now,
)
from deploy.control_plane.metrics import (
    get_metrics,
)
from deploy.control_plane.queue import InMemoryQueue, Queue, QueueMessage
from deploy.control_plane.rate_limiter import (
    RateLimiter,
    RateLimitExceededError,
)
from deploy.storage import ArtifactStore, LocalStore

logger = logging.getLogger(__name__)

# =============================================================================
# PYDANTIC MODELS
# =============================================================================


class SubmitRequest(BaseModel):
    """Request body for job submission."""

    company_name: str = Field(..., min_length=1, description="Company name to research")
    company_url: str = Field(..., description="Company URL to research")
    mode: str = Field(default="full", description="Research mode: scrape, deep, or full")
    idempotency_key: str = Field(..., min_length=1, description="Client-provided idempotency key")
    approve: bool = Field(default=False, description="Auto-approve job (skip PENDING_APPROVAL)")
    options: dict[str, Any] = Field(default_factory=dict, description="Additional options")


class CostEstimateResponse(BaseModel):
    """Cost estimate in response."""

    cost_usd: float
    duration_minutes: int


class SubmitResponse(BaseModel):
    """Response from job submission."""

    job_id: str
    status: str
    estimate: CostEstimateResponse
    is_existing: bool


class LastEvent(BaseModel):
    """Last progress event."""

    stage: str
    percent: int
    message: str
    timestamp: str


class TimingResponse(BaseModel):
    """Timing information in response."""

    submitted_at: str
    started_at: str | None = None
    completed_at: str | None = None


class StatusResponse(BaseModel):
    """Response from status query."""

    job_id: str
    status: str
    timing: TimingResponse
    last_event: LastEvent | None = None
    error: str | None = None


class CancelResponseModel(BaseModel):
    """Response from cancellation."""

    status: str
    message: str


class ArtifactInfo(BaseModel):
    """Artifact information with presigned URL."""

    presigned_url: str
    size_bytes: int
    checksum_sha256: str


class ResultsResponse(BaseModel):
    """Response from results query."""

    job_id: str
    status: str
    manifest: dict[str, Any]
    artifacts: dict[str, ArtifactInfo]


class ApproveResponse(BaseModel):
    """Response from job approval."""

    job_id: str
    status: str
    message: str


class QuotaResponse(BaseModel):
    """Quota information in error response."""

    max_concurrent_jobs: int
    max_daily_cost_usd: float
    max_job_cost_usd: float


class UsageResponse(BaseModel):
    """Usage information in error response."""

    concurrent_jobs: int
    daily_cost_usd: float


class QuotaErrorResponse(BaseModel):
    """Error response for quota exceeded."""

    error: str
    message: str
    quota: QuotaResponse
    usage: UsageResponse


# =============================================================================
# APPLICATION SETUP
# =============================================================================


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Application lifespan handler."""
    _initialize_default_dependencies()
    yield


app = FastAPI(
    title="Primr Cloud API",
    description="Control plane for serverless Primr job execution",
    version="1.0.0",
    lifespan=_lifespan,
)


# =============================================================================
# DEPENDENCY INJECTION
# =============================================================================

# Global instances (configured at startup)
_job_store: JobStore | None = None
_queue: Queue | None = None
_artifact_store: ArtifactStore | None = None
_cancellation_service: CancellationService | None = None
_cost_governor: CostGovernor | None = None
_rate_limiter: RateLimiter | None = None
_budget_tracker: BudgetTracker | None = None
_deployment: str = "default"


def configure_app(
    job_store: JobStore,
    queue: Queue,
    artifact_store: ArtifactStore,
    cancellation_service: CancellationService | None = None,
    cost_governor: CostGovernor | None = None,
    rate_limiter: RateLimiter | None = None,
    budget_tracker: BudgetTracker | None = None,
    deployment: str = "default",
) -> None:
    """
    Configure the application with dependencies.

    Call this before starting the server.
    """
    global \
        _job_store, \
        _queue, \
        _artifact_store, \
        _cancellation_service, \
        _cost_governor, \
        _rate_limiter, \
        _budget_tracker, \
        _deployment
    _job_store = job_store
    _queue = queue
    _artifact_store = artifact_store
    _cancellation_service = cancellation_service or CancellationService(job_store)
    _cost_governor = cost_governor or CostGovernor(job_store)
    _rate_limiter = rate_limiter or RateLimiter()
    _budget_tracker = budget_tracker or BudgetTracker()
    _deployment = deployment


def get_job_store() -> JobStore:
    """Get job store dependency."""
    if _job_store is None:
        raise RuntimeError("Application not configured. Call configure_app() first.")
    return _job_store


def get_queue() -> Queue:
    """Get queue dependency."""
    if _queue is None:
        raise RuntimeError("Application not configured. Call configure_app() first.")
    return _queue


def get_artifact_store() -> ArtifactStore:
    """Get artifact store dependency."""
    if _artifact_store is None:
        raise RuntimeError("Application not configured. Call configure_app() first.")
    return _artifact_store


def get_cancellation_service() -> CancellationService:
    """Get cancellation service dependency."""
    if _cancellation_service is None:
        raise RuntimeError("Application not configured. Call configure_app() first.")
    return _cancellation_service


def get_cost_governor() -> CostGovernor:
    """Get cost governor dependency."""
    if _cost_governor is None:
        raise RuntimeError("Application not configured. Call configure_app() first.")
    return _cost_governor


def get_rate_limiter() -> RateLimiter:
    """Get rate limiter dependency."""
    if _rate_limiter is None:
        raise RuntimeError("Application not configured. Call configure_app() first.")
    return _rate_limiter


def get_budget_tracker() -> BudgetTracker:
    """Get budget tracker dependency."""
    if _budget_tracker is None:
        raise RuntimeError("Application not configured. Call configure_app() first.")
    return _budget_tracker


def get_deployment() -> str:
    """Get deployment namespace."""
    return _deployment


def _load_static_api_keys() -> set[str]:
    """Comma-separated bearer tokens accepted as valid API keys.

    Configured via ``PRIMR_CONTROL_PLANE_API_KEYS``. Each token must be at
    least 16 characters. Constant-time comparison is used at verify time.
    Empty / unset means no static keys are accepted — JWT mode must then
    be configured, otherwise the API rejects every request (fail closed).
    """
    raw = os.environ.get("PRIMR_CONTROL_PLANE_API_KEYS", "")
    keys: set[str] = set()
    for token in raw.split(","):
        candidate = token.strip()
        if not candidate:
            continue
        if len(candidate) < 16:
            logger.warning(
                "control plane: ignoring PRIMR_CONTROL_PLANE_API_KEYS entry shorter than 16 chars"
            )
            continue
        keys.add(candidate)
    return keys


def _verify_static_api_key(presented: str) -> bool:
    """Constant-time check against configured static keys."""
    import hmac

    return any(hmac.compare_digest(presented, key) for key in _load_static_api_keys())


def _verify_jwt(presented: str) -> bool:
    """Verify an HS256 JWT against PRIMR_CONTROL_PLANE_JWT_SECRET.

    Rejects unsigned tokens (alg=none), expired tokens, and any token
    whose signature does not match. Returns False on any failure so the
    caller can fall back to static-key verification.
    """
    secret = os.environ.get("PRIMR_CONTROL_PLANE_JWT_SECRET", "").strip()
    if not secret or len(secret) < 32:
        return False
    try:
        import jwt  # PyJWT
    except ImportError:
        logger.warning(
            "control plane: JWT auth configured but PyJWT not installed — install primr[a2a] or PyJWT"
        )
        return False

    try:
        jwt.decode(
            presented,
            secret,
            algorithms=["HS256"],
            options={"require": ["exp"]},
        )
        return True
    except Exception as e:  # InvalidTokenError, ExpiredSignatureError, etc.
        logger.debug("control plane: JWT verification failed: %s", e)
        return False


def get_api_key(authorization: str = Header(default="")) -> str:
    """
    Extract and verify the API key from the Authorization header.

    Accepts either a static bearer token (PRIMR_CONTROL_PLANE_API_KEYS) or
    a signed JWT (PRIMR_CONTROL_PLANE_JWT_SECRET). Tries JWT first because
    JWT setups also typically have a few break-glass static keys.

    Expects: ``Bearer <token>``. Returns the verified raw token so callers
    can hash it into the api_key_hash used for tenancy / rate limits /
    ownership comparisons.

    Fails closed:
    - Missing or malformed Authorization header -> 401
    - No verifier configured (neither static keys nor JWT secret) -> 503
    - Token does not validate against any configured verifier -> 401
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    if authorization.startswith("Bearer "):
        presented = authorization[7:].strip()
    else:
        presented = authorization.strip()

    if not presented:
        raise HTTPException(status_code=401, detail="Authorization header required")

    static_keys = _load_static_api_keys()
    jwt_secret = os.environ.get("PRIMR_CONTROL_PLANE_JWT_SECRET", "").strip()

    if not static_keys and (not jwt_secret or len(jwt_secret) < 32):
        # No verifier configured. The previous behavior here was to accept
        # any string, which made every privileged route world-callable.
        # Refuse all traffic until the operator wires real credentials.
        logger.error(
            "control plane: rejecting request — neither PRIMR_CONTROL_PLANE_API_KEYS "
            "nor a 32+ char PRIMR_CONTROL_PLANE_JWT_SECRET is configured"
        )
        raise HTTPException(
            status_code=503,
            detail="Control plane authentication is not configured",
        )

    if _verify_jwt(presented) or _verify_static_api_key(presented):
        return presented

    raise HTTPException(status_code=401, detail="Invalid or expired credentials")


def _require_job_owner(job: JobRecord, api_key: str) -> None:
    """Raise 404 unless ``api_key`` owns the job.

    We deliberately return 404 (not 403) so that an attacker holding any
    valid bearer token cannot probe for the existence of other tenants'
    job IDs. The hash comparison is constant-time.
    """
    import hmac

    caller_hash = hash_api_key(api_key)
    if not hmac.compare_digest(caller_hash, job.api_key_hash):
        raise HTTPException(status_code=404, detail=f"Job {job.job_id} not found")


# =============================================================================
# API ENDPOINTS
# =============================================================================


@app.post("/submit", response_model=SubmitResponse)
async def submit_job(
    request: SubmitRequest,
    api_key: str = Depends(get_api_key),
    job_store: JobStore = Depends(get_job_store),  # noqa: B008 - FastAPI dependency injection
    queue: Queue = Depends(get_queue),  # noqa: B008 - FastAPI dependency injection
    cost_governor: CostGovernor = Depends(get_cost_governor),  # noqa: B008 - FastAPI dependency injection
    rate_limiter: RateLimiter = Depends(get_rate_limiter),  # noqa: B008 - FastAPI dependency injection
) -> SubmitResponse:
    """
    Submit a research job.

    Creates a new job or returns existing job if idempotency_key matches.
    Returns 409 if idempotency_key matches but inputs differ.
    Returns 429 if quota exceeded or rate limited.
    """
    deployment = get_deployment()
    api_key_hash = hash_api_key(api_key)

    # Check rate limit first
    rate_result = rate_limiter.check(api_key_hash)
    if not rate_result.allowed:
        # Record rate limit hit
        metrics = get_metrics()
        metrics.record_rate_limit_hit(api_key_hash)
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limited",
                "message": "Too many requests",
                "retry_after": rate_result.retry_after,
            },
            headers={"Retry-After": str(int(rate_result.retry_after or 1))},
        )

    # Validate mode
    if request.mode not in ("scrape", "deep", "full"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode: {request.mode}. Must be scrape, deep, or full",
        )

    # Canonicalize inputs
    canonical = canonicalize_inputs(
        company_name=request.company_name,
        company_url=request.company_url,
        mode=request.mode,
        options=request.options,
    )
    canonical_hash = hash_inputs(canonical)

    # Derive job_id from (deployment, idempotency_key, api_key)
    job_id = hash_job_id(deployment, request.idempotency_key, api_key)

    # Check for existing job
    existing = job_store.get(job_id)
    if existing:
        # CRITICAL: Reject if same idempotency_key but different inputs
        if existing.canonical_hash != canonical_hash:
            raise HTTPException(
                status_code=409,
                detail=f"Idempotency key '{request.idempotency_key}' already used with different inputs. "
                "Use a new idempotency_key for different requests.",
            )
        return SubmitResponse(
            job_id=existing.job_id,
            status=existing.status.value,
            estimate=CostEstimateResponse(
                cost_usd=existing.estimate.cost_usd,
                duration_minutes=existing.estimate.duration_minutes,
            ),
            is_existing=True,
        )

    # Estimate cost
    estimate = estimate_cost(request.mode)

    # Check quota
    try:
        cost_governor.check_quota(api_key_hash, estimate)
    except QuotaExceededError as e:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "quota_exceeded",
                "message": str(e),
                "quota": e.quota.to_dict(),
                "usage": e.usage.to_dict(),
            },
        ) from e

    # Determine initial status
    if request.approve:
        initial_status = JobStatus.QUEUED
    else:
        initial_status = JobStatus.PENDING_APPROVAL

    # Create job record
    now = utc_now()
    job = JobRecord(
        job_id=job_id,
        deployment=deployment,
        idempotency_key=request.idempotency_key,
        api_key_hash=api_key_hash,
        canonical_hash=canonical_hash,
        status=initial_status,
        inputs=canonical,
        expected_artifacts=get_expected_artifacts(request.mode),
        estimate=estimate,
        timing=JobTiming(submitted_at=format_timestamp(now)),
        ttl=int(time.time()) + 30 * 24 * 3600,  # 30 day retention
    )

    # Conditional write (prevents race conditions)
    try:
        job_store.put_if_not_exists(job)
    except ConditionalCheckFailedError as e:
        # Another request created the job concurrently - return it
        existing = job_store.get(job_id)
        if existing:
            if existing.canonical_hash != canonical_hash:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency key collision with different inputs",
                ) from e
            return SubmitResponse(
                job_id=existing.job_id,
                status=existing.status.value,
                estimate=CostEstimateResponse(
                    cost_usd=existing.estimate.cost_usd,
                    duration_minutes=existing.estimate.duration_minutes,
                ),
                is_existing=True,
            )
        raise HTTPException(status_code=500, detail="Failed to create job") from e

    # Enqueue if approved
    if request.approve:
        message = QueueMessage(
            job_id=job_id,
            deployment=deployment,
            api_key_hash=api_key_hash,
            inputs=canonical.to_dict(),
            enqueued_at=format_timestamp(now),
            attempt=1,
        )
        queue.enqueue(message)

    # Record metrics
    metrics = get_metrics()
    metrics.record_job_submitted(request.mode, deployment)

    return SubmitResponse(
        job_id=job_id,
        status=initial_status.value,
        estimate=CostEstimateResponse(
            cost_usd=estimate.cost_usd,
            duration_minutes=estimate.duration_minutes,
        ),
        is_existing=False,
    )


@app.get("/status/{job_id}", response_model=StatusResponse)
async def get_status(
    job_id: str,
    api_key: str = Depends(get_api_key),
    job_store: JobStore = Depends(get_job_store),  # noqa: B008 - FastAPI dependency injection
    artifact_store: ArtifactStore = Depends(get_artifact_store),  # noqa: B008 - FastAPI dependency injection
) -> StatusResponse:
    """
    Get job status.

    Returns 404 if job not found OR if the caller is not the job owner.
    Returning 404 on ownership mismatch prevents authenticated attackers
    from probing for other tenants' job IDs.
    Includes last_event from events.jsonl or heartbeat for progress tracking.
    """
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    _require_job_owner(job, api_key)

    # Try to get last event from events.jsonl or heartbeat
    last_event = None
    try:
        last_event = _get_last_event(artifact_store, job_id)
    except Exception:
        pass  # Ignore errors reading events

    return StatusResponse(
        job_id=job.job_id,
        status=job.status.value,
        timing=TimingResponse(
            submitted_at=job.timing.submitted_at,
            started_at=job.timing.started_at,
            completed_at=job.timing.completed_at,
        ),
        last_event=last_event,
        error=job.error_message,
    )


@app.post("/approve/{job_id}", response_model=ApproveResponse)
async def approve_job(
    job_id: str,
    api_key: str = Depends(get_api_key),
    job_store: JobStore = Depends(get_job_store),  # noqa: B008 - FastAPI dependency injection
    queue: Queue = Depends(get_queue),  # noqa: B008 - FastAPI dependency injection
) -> ApproveResponse:
    """
    Approve a pending job.

    Returns 404 if job not found or not owned by caller.
    Returns 409 if job not in PENDING_APPROVAL state.
    """
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    _require_job_owner(job, api_key)

    if job.status != JobStatus.PENDING_APPROVAL:
        raise HTTPException(
            status_code=409,
            detail=f"Job is not pending approval (current status: {job.status.value})",
        )

    # Update status to QUEUED
    job.status = JobStatus.QUEUED
    job_store.update(job)

    # Enqueue the job
    message = QueueMessage(
        job_id=job_id,
        deployment=job.deployment,
        api_key_hash=job.api_key_hash,
        inputs=job.inputs.to_dict(),
        enqueued_at=format_timestamp(utc_now()),
        attempt=job.attempt,
    )
    queue.enqueue(message)

    return ApproveResponse(
        job_id=job_id,
        status=JobStatus.QUEUED.value,
        message="Job approved and queued for execution",
    )


@app.post("/cancel/{job_id}", response_model=CancelResponseModel)
async def cancel_job(
    job_id: str,
    api_key: str = Depends(get_api_key),
    job_store: JobStore = Depends(get_job_store),  # noqa: B008 - FastAPI dependency injection
    cancellation_service: CancellationService = Depends(get_cancellation_service),  # noqa: B008 - FastAPI dependency injection
) -> CancelResponseModel:
    """
    Cancel a job (best-effort).

    Returns 404 if job not found or not owned by caller.
    """
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    _require_job_owner(job, api_key)

    result = cancellation_service.cancel_job(job_id)

    if result.result.value == "NOT_FOUND":
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return CancelResponseModel(
        status=result.status.value,
        message=result.message,
    )


@app.get("/results/{job_id}", response_model=ResultsResponse)
async def get_results(
    job_id: str,
    api_key: str = Depends(get_api_key),
    job_store: JobStore = Depends(get_job_store),  # noqa: B008 - FastAPI dependency injection
    artifact_store: ArtifactStore = Depends(get_artifact_store),  # noqa: B008 - FastAPI dependency injection
) -> ResultsResponse:
    """
    Get job results with presigned URLs.

    Returns 404 if job not found or not owned by caller.
    Returns 425 (Too Early) if job exists but manifest not yet written.
    """
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    _require_job_owner(job, api_key)

    # Get manifest from artifact store
    manifest = artifact_store.get_manifest(job_id)
    if not manifest:
        raise HTTPException(
            status_code=425,
            detail=f"Job {job_id} not complete (no manifest yet)",
        )

    # Generate presigned URLs for artifacts
    artifacts = {}
    for name, meta in manifest.artifacts.items():
        key = f"{job_id}/{name}"
        artifacts[name] = ArtifactInfo(
            presigned_url=artifact_store.presign(key),
            size_bytes=meta.size_bytes,
            checksum_sha256=meta.checksum_sha256,
        )

    return ResultsResponse(
        job_id=job_id,
        status=manifest.status,
        manifest=manifest.to_dict(),
        artifacts=artifacts,
    )


@app.get("/usage/{api_key_hash}")
async def get_usage(
    api_key_hash: str,
    _api_key: str = Depends(get_api_key),
    budget_tracker: BudgetTracker = Depends(get_budget_tracker),  # noqa: B008 - FastAPI dependency injection
) -> JSONResponse:
    """
    Get budget usage for an API key.

    Returns cumulative spend (daily, monthly, all-time), job count,
    and remaining budget for the authenticated API key.
    Only allows querying the caller's own usage.

    Requirements: 6.4
    """
    # Compute the caller's api_key_hash and enforce own-usage-only access
    caller_hash = hash_api_key(_api_key)
    if caller_hash != api_key_hash:
        raise HTTPException(status_code=403, detail="Cannot query usage for a different API key")

    status = budget_tracker.get_budget_status(api_key_hash)
    return JSONResponse(content=status.to_dict())


@app.get("/healthz")
async def healthz() -> JSONResponse:
    """
    Health check endpoint.

    In cloud mode: verifies connectivity to Cosmos DB and Blob Storage.
    In local mode: always returns 200 with healthy status.

    Returns 200 (healthy) or 503 (unhealthy).

    Requirements: 2.7
    """
    from primr.mcp_server.cloud_detect import is_cloud_mode

    if not is_cloud_mode():
        return JSONResponse(
            status_code=200,
            content={"status": "healthy", "mode": "local"},
        )

    # Cloud mode: check connectivity to backing services
    checks: dict[str, Any] = {}

    # Check Cosmos DB connectivity
    try:
        store = get_job_store()
        # A lightweight read to verify connectivity
        store.get("__healthz_probe__")
        checks["cosmos_db"] = {"status": "ok"}
    except Exception:
        logger.exception("Health check: Cosmos DB connectivity failed")
        checks["cosmos_db"] = {"status": "error", "detail": "connectivity check failed"}

    # Check Blob Storage connectivity
    try:
        artifact_store = get_artifact_store()
        # A lightweight read to verify connectivity
        artifact_store.get("__healthz_probe__")
        checks["blob_storage"] = {"status": "ok"}
    except Exception:
        logger.exception("Health check: Blob Storage connectivity failed")
        checks["blob_storage"] = {"status": "error", "detail": "connectivity check failed"}

    all_ok = all(c["status"] == "ok" for c in checks.values())
    status_code = 200 if all_ok else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if all_ok else "unhealthy",
            "mode": "cloud",
            "checks": checks,
        },
    )


@app.get("/metrics")
async def get_metrics_endpoint(
    api_key: str = Depends(get_api_key),
) -> JSONResponse:
    """
    Get control plane metrics.

    Returns metrics in JSON format for monitoring systems.
    Requires authentication.
    """
    metrics = get_metrics()
    return JSONResponse(content=json.loads(metrics.to_json()))


@app.get("/metrics/prometheus")
async def get_prometheus_metrics(
    api_key: str = Depends(get_api_key),
) -> str:
    """
    Get control plane metrics in Prometheus format.

    Returns metrics in Prometheus text format.
    Requires authentication.
    """
    from fastapi.responses import PlainTextResponse

    metrics = get_metrics()
    return PlainTextResponse(content=metrics.to_prometheus(), media_type="text/plain")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _get_last_event(artifact_store: ArtifactStore, job_id: str) -> LastEvent | None:
    """
    Get last event from events.jsonl or heartbeat.

    Tries events.jsonl first, falls back to heartbeat.
    """
    # Try events.jsonl first
    events_data = artifact_store.get(f"{job_id}/events.jsonl")
    if events_data:
        lines = events_data.decode("utf-8").strip().split("\n")
        if lines:
            try:
                last = json.loads(lines[-1])
                return LastEvent(
                    stage=last.get("stage", "unknown"),
                    percent=last.get("percent", 0),
                    message=last.get("message", ""),
                    timestamp=last.get("ts", ""),
                )
            except json.JSONDecodeError:
                pass

    # Fall back to heartbeat
    heartbeat_data = artifact_store.get(f"{job_id}/_heartbeat.json")
    if heartbeat_data:
        try:
            heartbeat = json.loads(heartbeat_data.decode("utf-8"))
            return LastEvent(
                stage=heartbeat.get("stage", "unknown"),
                percent=heartbeat.get("percent", 0),
                message=f"Heartbeat at {heartbeat.get('last_heartbeat', '')}",
                timestamp=heartbeat.get("last_heartbeat", ""),
            )
        except json.JSONDecodeError:
            pass

    return None


# =============================================================================
# ERROR HANDLERS
# =============================================================================


@app.exception_handler(QuotaExceededError)
async def quota_exceeded_handler(request: Request, exc: QuotaExceededError) -> JSONResponse:
    """Handle quota exceeded errors."""
    return JSONResponse(
        status_code=429,
        content={
            "error": "quota_exceeded",
            "message": str(exc),
            "quota": exc.quota.to_dict(),
            "usage": exc.usage.to_dict(),
        },
    )


@app.exception_handler(BudgetExceededError)
async def budget_exceeded_handler(request: Request, exc: BudgetExceededError) -> JSONResponse:
    """Handle budget exceeded errors."""
    content: dict[str, Any] = {
        "error": "quota_exceeded",
        "message": str(exc),
        "limit_type": exc.limit_type,
        "limits": exc.limits.to_dict(),
        "usage": exc.usage.to_dict(),
    }
    if exc.reset_at:
        content["reset_at"] = exc.reset_at
    return JSONResponse(status_code=429, content=content)


@app.exception_handler(RateLimitExceededError)
async def rate_limit_handler(request: Request, exc: RateLimitExceededError) -> JSONResponse:
    """Handle rate limit exceeded errors."""
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limited",
            "message": str(exc),
            "retry_after": exc.result.retry_after,
        },
        headers={"Retry-After": str(int(exc.result.retry_after or 1))},
    )


# =============================================================================
# STARTUP/SHUTDOWN
# =============================================================================


def _initialize_default_dependencies() -> None:
    """Initialize default dependencies when app is not explicitly configured."""
    # If not configured, use defaults for local development
    global \
        _job_store, \
        _queue, \
        _artifact_store, \
        _cancellation_service, \
        _cost_governor, \
        _rate_limiter, \
        _budget_tracker, \
        _deployment

    if _job_store is None:
        import tempfile

        _job_store = InMemoryJobStore()
        _queue = InMemoryQueue()
        _artifact_store = LocalStore(tempfile.mkdtemp(prefix="primr_artifacts_"))
        _cancellation_service = CancellationService(_job_store)
        _cost_governor = CostGovernor(_job_store)
        _rate_limiter = RateLimiter()
        _budget_tracker = BudgetTracker()
        _deployment = os.environ.get("DEPLOYMENT", "local")


# =============================================================================
# MAIN
# =============================================================================


def create_app(
    job_store: JobStore | None = None,
    queue: Queue | None = None,
    artifact_store: ArtifactStore | None = None,
    rate_limiter: RateLimiter | None = None,
    budget_tracker: BudgetTracker | None = None,
    deployment: str = "default",
) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Args:
        job_store: Job state store (defaults to InMemoryJobStore)
        queue: Message queue (defaults to InMemoryQueue)
        artifact_store: Artifact store (defaults to LocalStore)
        rate_limiter: Rate limiter (defaults to RateLimiter)
        budget_tracker: Budget tracker (defaults to BudgetTracker)
        deployment: Deployment namespace

    Returns:
        Configured FastAPI application
    """
    import tempfile

    store = job_store or InMemoryJobStore()
    q = queue or InMemoryQueue()
    artifacts = artifact_store or LocalStore(tempfile.mkdtemp(prefix="primr_artifacts_"))
    limiter = rate_limiter or RateLimiter()
    tracker = budget_tracker or BudgetTracker()

    configure_app(
        job_store=store,
        queue=q,
        artifact_store=artifacts,
        rate_limiter=limiter,
        budget_tracker=tracker,
        deployment=deployment,
    )

    return app


if __name__ == "__main__":
    import uvicorn

    # Create app with defaults
    create_app()

    # Run server
    uvicorn.run(app, host="0.0.0.0", port=8000)
