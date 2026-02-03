"""
Control Plane - Job submission, status, and result retrieval API.

This module provides the control plane service for the serverless cloud deployment.
The control plane handles:
- Job submission with idempotency
- Job status queries
- Job approval for pending jobs
- Job cancellation
- Result retrieval with presigned URLs

The control plane requires NO LLM keys - only JWT, job store, queue, and presign credentials.

Requirements: 3.1-3.20, 4.1-4.7
"""

from deploy.control_plane.job_store import (
    JobRecord,
    JobStatus,
    JobStore,
    InMemoryJobStore,
    ConflictError,
    NotFoundError,
    canonicalize_inputs,
    hash_inputs,
    hash_job_id,
    hash_api_key,
    get_expected_artifacts,
)
from deploy.control_plane.queue import Queue, InMemoryQueue, QueueMessage
from deploy.control_plane.cancellation import CancellationService, CancelResponse
from deploy.control_plane.cost_governor import CostGovernor, QuotaExceededError, estimate_cost
from deploy.control_plane.api import app, create_app, configure_app

__all__ = [
    # Job Store
    "JobRecord",
    "JobStatus",
    "JobStore",
    "InMemoryJobStore",
    "ConflictError",
    "NotFoundError",
    "canonicalize_inputs",
    "hash_inputs",
    "hash_job_id",
    "hash_api_key",
    "get_expected_artifacts",
    # Queue
    "Queue",
    "InMemoryQueue",
    "QueueMessage",
    # Cancellation
    "CancellationService",
    "CancelResponse",
    # Cost Governor
    "CostGovernor",
    "QuotaExceededError",
    "estimate_cost",
    # API
    "app",
    "create_app",
    "configure_app",
]
