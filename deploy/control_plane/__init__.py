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

from deploy.control_plane.api import app, configure_app, create_app
from deploy.control_plane.cancellation import CancellationService, CancelResponse
from deploy.control_plane.cost_governor import CostGovernor, QuotaExceededError, estimate_cost
from deploy.control_plane.job_store import (
    ConflictError,
    InMemoryJobStore,
    JobRecord,
    JobStatus,
    JobStore,
    NotFoundError,
    canonicalize_inputs,
    get_expected_artifacts,
    hash_api_key,
    hash_inputs,
    hash_job_id,
)
from deploy.control_plane.queue import InMemoryQueue, Queue, QueueMessage

__all__ = [
    "CancelResponse",
    # Cancellation
    "CancellationService",
    "ConflictError",
    # Cost Governor
    "CostGovernor",
    "InMemoryJobStore",
    "InMemoryQueue",
    # Job Store
    "JobRecord",
    "JobStatus",
    "JobStore",
    "NotFoundError",
    # Queue
    "Queue",
    "QueueMessage",
    "QuotaExceededError",
    # API
    "app",
    "canonicalize_inputs",
    "configure_app",
    "create_app",
    "estimate_cost",
    "get_expected_artifacts",
    "hash_api_key",
    "hash_inputs",
    "hash_job_id",
]
