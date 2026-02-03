"""
Job Store - Job state persistence for the control plane.

This module provides job state persistence across different cloud providers:
- DynamoDB (AWS)
- Cosmos DB (Azure)
- Firestore (GCP)
- InMemory (testing)

Key features:
- JobRecord dataclass with deployment, canonical_hash, expected_artifacts, execution_id, attempt
- Idempotency key lookup with input mismatch detection (409)
- Conditional writes (put_if_not_exists) for each provider
- Uniqueness constraint: (deployment, api_key_hash, idempotency_key)

Requirements: 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.18
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlparse


class JobStatus(str, Enum):
    """Job lifecycle states."""
    PENDING_APPROVAL = "PENDING_APPROVAL"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ConflictError(Exception):
    """Raised when idempotency key is reused with different inputs."""
    pass


class NotFoundError(Exception):
    """Raised when job is not found."""
    pass


class ConditionalCheckFailedError(Exception):
    """Raised when conditional write fails (job already exists)."""
    pass


def utc_now() -> datetime:
    """Get current UTC time."""
    return datetime.now(timezone.utc)


def format_timestamp(dt: datetime) -> str:
    """Format datetime as ISO 8601 string."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class CostEstimate:
    """Cost and time estimate for a job."""
    cost_usd: float
    duration_minutes: int
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "cost_usd": self.cost_usd,
            "duration_minutes": self.duration_minutes,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CostEstimate":
        return cls(
            cost_usd=data.get("cost_usd", 0.0),
            duration_minutes=data.get("duration_minutes", 0),
        )


@dataclass
class JobInputs:
    """Canonicalized job inputs."""
    company_name: str
    company_url: str
    mode: str
    options: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "company_name": self.company_name,
            "company_url": self.company_url,
            "mode": self.mode,
            "options": self.options,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobInputs":
        return cls(
            company_name=data.get("company_name", ""),
            company_url=data.get("company_url", ""),
            mode=data.get("mode", "full"),
            options=data.get("options", {}),
        )


@dataclass
class JobTiming:
    """Timing information for a job."""
    submitted_at: str
    started_at: str | None = None
    completed_at: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "submitted_at": self.submitted_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobTiming":
        return cls(
            submitted_at=data.get("submitted_at", ""),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
        )


@dataclass
class JobRecord:
    """
    Job record for state persistence.
    
    Uniqueness constraint: (deployment, api_key_hash, idempotency_key)
    """
    job_id: str
    deployment: str
    idempotency_key: str
    api_key_hash: str
    canonical_hash: str  # Hash of canonicalized inputs for mismatch detection
    status: JobStatus
    inputs: JobInputs
    expected_artifacts: list[str]
    estimate: CostEstimate
    timing: JobTiming
    execution_id: str | None = None  # Provider task/job ID
    attempt: int = 1
    artifact_location: str = ""  # e.g., s3://bucket/deployment/job_id/
    error_message: str | None = None
    ttl: int = 0  # Unix timestamp for auto-expiry
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "job_id": self.job_id,
            "deployment": self.deployment,
            "idempotency_key": self.idempotency_key,
            "api_key_hash": self.api_key_hash,
            "canonical_hash": self.canonical_hash,
            "status": self.status.value,
            "inputs": self.inputs.to_dict(),
            "expected_artifacts": self.expected_artifacts,
            "estimate": self.estimate.to_dict(),
            "timing": self.timing.to_dict(),
            "execution_id": self.execution_id,
            "attempt": self.attempt,
            "artifact_location": self.artifact_location,
            "error_message": self.error_message,
            "ttl": self.ttl,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobRecord":
        """Create from dictionary."""
        return cls(
            job_id=data.get("job_id", ""),
            deployment=data.get("deployment", ""),
            idempotency_key=data.get("idempotency_key", ""),
            api_key_hash=data.get("api_key_hash", ""),
            canonical_hash=data.get("canonical_hash", ""),
            status=JobStatus(data.get("status", "QUEUED")),
            inputs=JobInputs.from_dict(data.get("inputs", {})),
            expected_artifacts=data.get("expected_artifacts", []),
            estimate=CostEstimate.from_dict(data.get("estimate", {})),
            timing=JobTiming.from_dict(data.get("timing", {})),
            execution_id=data.get("execution_id"),
            attempt=data.get("attempt", 1),
            artifact_location=data.get("artifact_location", ""),
            error_message=data.get("error_message"),
            ttl=data.get("ttl", 0),
        )


def canonicalize_inputs(
    company_name: str,
    company_url: str,
    mode: str,
    options: dict[str, Any] | None = None,
) -> JobInputs:
    """
    Normalize inputs for consistent hashing and comparison.
    
    - Strips whitespace from company_name
    - Normalizes URL (lowercase host, remove trailing slash)
    - Sorts options dictionary
    """
    # Normalize URL
    parsed = urlparse(company_url)
    normalized_url = f"{parsed.scheme}://{parsed.netloc.lower()}{parsed.path.rstrip('/')}"
    if parsed.query:
        normalized_url += f"?{parsed.query}"
    
    return JobInputs(
        company_name=company_name.strip(),
        company_url=normalized_url,
        mode=mode,
        options=dict(sorted((options or {}).items())),
    )


def hash_inputs(inputs: JobInputs) -> str:
    """Compute SHA-256 hash of canonicalized inputs."""
    data = json.dumps(inputs.to_dict(), sort_keys=True)
    return hashlib.sha256(data.encode()).hexdigest()


def hash_job_id(deployment: str, idempotency_key: str, api_key: str) -> str:
    """
    Derive deterministic job_id from (deployment, idempotency_key, api_key).
    
    This prevents collisions across environments and tenants.
    """
    data = f"{deployment}:{idempotency_key}:{api_key}"
    return hashlib.sha256(data.encode()).hexdigest()[:24]


def hash_api_key(api_key: str) -> str:
    """Hash API key for storage (never store raw keys)."""
    return f"sha256:{hashlib.sha256(api_key.encode()).hexdigest()}"


def get_expected_artifacts(mode: str) -> list[str]:
    """Return expected artifacts for each mode."""
    return {
        "scrape": ["scraped_content.txt", "insights.txt"],
        "deep": ["dossier.txt", "report.docx", "report.md"],
        "full": ["scraped_content.txt", "insights.txt", "dossier.txt", "report.docx", "report.md"],
    }.get(mode, ["scraped_content.txt", "insights.txt", "dossier.txt", "report.docx", "report.md"])


@runtime_checkable
class JobStore(Protocol):
    """Protocol for job state persistence."""
    
    def get(self, job_id: str) -> JobRecord | None:
        """Get job by ID, returns None if not found."""
        ...
    
    def put_if_not_exists(self, job: JobRecord) -> None:
        """
        Create job with conditional write (fails if exists).
        
        Raises:
            ConditionalCheckFailedError: If job already exists
        """
        ...
    
    def update(self, job: JobRecord) -> None:
        """Update existing job."""
        ...
    
    def query_by_status(
        self,
        status: list[JobStatus],
        started_before: datetime | None = None,
    ) -> list[JobRecord]:
        """Query jobs by status, optionally filtered by start time."""
        ...


class InMemoryJobStore:
    """
    In-memory job store for testing.
    
    Thread-safe implementation using locks.
    """
    
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()
    
    def get(self, job_id: str) -> JobRecord | None:
        """Get job by ID."""
        with self._lock:
            return self._jobs.get(job_id)
    
    def put_if_not_exists(self, job: JobRecord) -> None:
        """Create job with conditional write."""
        with self._lock:
            if job.job_id in self._jobs:
                raise ConditionalCheckFailedError(f"Job {job.job_id} already exists")
            self._jobs[job.job_id] = job
    
    def update(self, job: JobRecord) -> None:
        """Update existing job."""
        with self._lock:
            if job.job_id not in self._jobs:
                raise NotFoundError(f"Job {job.job_id} not found")
            self._jobs[job.job_id] = job
    
    def query_by_status(
        self,
        status: list[JobStatus],
        started_before: datetime | None = None,
    ) -> list[JobRecord]:
        """Query jobs by status."""
        with self._lock:
            results = []
            for job in self._jobs.values():
                if job.status in status:
                    if started_before and job.timing.started_at:
                        # Parse started_at and compare
                        started = datetime.fromisoformat(
                            job.timing.started_at.replace("Z", "+00:00")
                        )
                        if started >= started_before:
                            continue
                    results.append(job)
            return results
    
    def clear(self) -> None:
        """Clear all jobs (for testing)."""
        with self._lock:
            self._jobs.clear()


class DynamoDBStore:
    """
    AWS DynamoDB job store.
    
    Uses ConditionExpression="attribute_not_exists(job_id)" for conditional writes.
    """
    
    def __init__(
        self,
        table_name: str,
        region: str | None = None,
        client: Any = None,
    ) -> None:
        """
        Initialize DynamoDB store.
        
        Args:
            table_name: DynamoDB table name
            region: AWS region (optional)
            client: Optional boto3 DynamoDB client (for testing)
        """
        self.table_name = table_name
        self.region = region
        self._client = client
    
    @property
    def client(self) -> Any:
        """Get or create boto3 DynamoDB client."""
        if self._client is None:
            import boto3
            self._client = boto3.client("dynamodb", region_name=self.region)
        return self._client
    
    def _to_dynamodb_item(self, job: JobRecord) -> dict[str, Any]:
        """Convert JobRecord to DynamoDB item format."""
        item = {
            "job_id": {"S": job.job_id},
            "deployment": {"S": job.deployment},
            "idempotency_key": {"S": job.idempotency_key},
            "api_key_hash": {"S": job.api_key_hash},
            "canonical_hash": {"S": job.canonical_hash},
            "status": {"S": job.status.value},
            "inputs": {"S": json.dumps(job.inputs.to_dict())},
            "expected_artifacts": {"SS": job.expected_artifacts} if job.expected_artifacts else {"SS": ["_empty"]},
            "estimate": {"S": json.dumps(job.estimate.to_dict())},
            "timing": {"S": json.dumps(job.timing.to_dict())},
            "attempt": {"N": str(job.attempt)},
            "artifact_location": {"S": job.artifact_location},
            "ttl": {"N": str(job.ttl)},
        }
        if job.execution_id:
            item["execution_id"] = {"S": job.execution_id}
        if job.error_message:
            item["error_message"] = {"S": job.error_message}
        return item
    
    def _from_dynamodb_item(self, item: dict[str, Any]) -> JobRecord:
        """Convert DynamoDB item to JobRecord."""
        expected = item.get("expected_artifacts", {}).get("SS", [])
        if expected == ["_empty"]:
            expected = []
        
        return JobRecord(
            job_id=item["job_id"]["S"],
            deployment=item["deployment"]["S"],
            idempotency_key=item["idempotency_key"]["S"],
            api_key_hash=item["api_key_hash"]["S"],
            canonical_hash=item["canonical_hash"]["S"],
            status=JobStatus(item["status"]["S"]),
            inputs=JobInputs.from_dict(json.loads(item["inputs"]["S"])),
            expected_artifacts=expected,
            estimate=CostEstimate.from_dict(json.loads(item["estimate"]["S"])),
            timing=JobTiming.from_dict(json.loads(item["timing"]["S"])),
            execution_id=item.get("execution_id", {}).get("S"),
            attempt=int(item["attempt"]["N"]),
            artifact_location=item["artifact_location"]["S"],
            error_message=item.get("error_message", {}).get("S"),
            ttl=int(item["ttl"]["N"]),
        )
    
    def get(self, job_id: str) -> JobRecord | None:
        """Get job by ID."""
        try:
            response = self.client.get_item(
                TableName=self.table_name,
                Key={"job_id": {"S": job_id}},
            )
            item = response.get("Item")
            if not item:
                return None
            return self._from_dynamodb_item(item)
        except Exception:
            return None
    
    def put_if_not_exists(self, job: JobRecord) -> None:
        """Create job with conditional write."""
        try:
            self.client.put_item(
                TableName=self.table_name,
                Item=self._to_dynamodb_item(job),
                ConditionExpression="attribute_not_exists(job_id)",
            )
        except Exception as e:
            if "ConditionalCheckFailedException" in str(type(e)):
                raise ConditionalCheckFailedError(f"Job {job.job_id} already exists") from e
            raise
    
    def update(self, job: JobRecord) -> None:
        """Update existing job."""
        self.client.put_item(
            TableName=self.table_name,
            Item=self._to_dynamodb_item(job),
        )
    
    def query_by_status(
        self,
        status: list[JobStatus],
        started_before: datetime | None = None,
    ) -> list[JobRecord]:
        """Query jobs by status using scan (GSI recommended for production)."""
        results = []
        status_values = [s.value for s in status]
        
        # Note: In production, use a GSI on status for efficient queries
        paginator = self.client.get_paginator("scan")
        for page in paginator.paginate(TableName=self.table_name):
            for item in page.get("Items", []):
                if item["status"]["S"] in status_values:
                    job = self._from_dynamodb_item(item)
                    if started_before and job.timing.started_at:
                        started = datetime.fromisoformat(
                            job.timing.started_at.replace("Z", "+00:00")
                        )
                        if started >= started_before:
                            continue
                    results.append(job)
        
        return results


class CosmosStore:
    """
    Azure Cosmos DB job store.
    
    Uses etag for conditional writes.
    """
    
    def __init__(
        self,
        database_name: str,
        container_name: str,
        connection_string: str | None = None,
        container: Any = None,
    ) -> None:
        """
        Initialize Cosmos DB store.
        
        Args:
            database_name: Cosmos DB database name
            container_name: Container name
            connection_string: Azure Cosmos DB connection string
            container: Optional container client (for testing)
        """
        self.database_name = database_name
        self.container_name = container_name
        self.connection_string = connection_string
        self._container = container
    
    @property
    def container(self) -> Any:
        """Get or create Cosmos DB container client."""
        if self._container is None:
            from azure.cosmos import CosmosClient
            client = CosmosClient.from_connection_string(self.connection_string)
            database = client.get_database_client(self.database_name)
            self._container = database.get_container_client(self.container_name)
        return self._container
    
    def get(self, job_id: str) -> JobRecord | None:
        """Get job by ID."""
        try:
            item = self.container.read_item(item=job_id, partition_key=job_id)
            return JobRecord.from_dict(item)
        except Exception:
            return None
    
    def put_if_not_exists(self, job: JobRecord) -> None:
        """Create job with conditional write."""
        from azure.cosmos.exceptions import CosmosResourceExistsError
        
        try:
            item = job.to_dict()
            item["id"] = job.job_id  # Cosmos DB requires 'id' field
            self.container.create_item(body=item)
        except CosmosResourceExistsError as e:
            raise ConditionalCheckFailedError(f"Job {job.job_id} already exists") from e
    
    def update(self, job: JobRecord) -> None:
        """Update existing job."""
        item = job.to_dict()
        item["id"] = job.job_id
        self.container.upsert_item(body=item)
    
    def query_by_status(
        self,
        status: list[JobStatus],
        started_before: datetime | None = None,
    ) -> list[JobRecord]:
        """Query jobs by status."""
        status_values = [f"'{s.value}'" for s in status]
        query = f"SELECT * FROM c WHERE c.status IN ({', '.join(status_values)})"
        
        results = []
        for item in self.container.query_items(query=query, enable_cross_partition_query=True):
            job = JobRecord.from_dict(item)
            if started_before and job.timing.started_at:
                started = datetime.fromisoformat(
                    job.timing.started_at.replace("Z", "+00:00")
                )
                if started >= started_before:
                    continue
            results.append(job)
        
        return results


class FirestoreStore:
    """
    Google Cloud Firestore job store.
    
    Uses transaction with create() for conditional writes.
    """
    
    def __init__(
        self,
        collection_name: str,
        project: str | None = None,
        db: Any = None,
    ) -> None:
        """
        Initialize Firestore store.
        
        Args:
            collection_name: Firestore collection name
            project: GCP project ID
            db: Optional Firestore client (for testing)
        """
        self.collection_name = collection_name
        self.project = project
        self._db = db
    
    @property
    def db(self) -> Any:
        """Get or create Firestore client."""
        if self._db is None:
            from google.cloud import firestore
            self._db = firestore.Client(project=self.project)
        return self._db
    
    def get(self, job_id: str) -> JobRecord | None:
        """Get job by ID."""
        doc = self.db.collection(self.collection_name).document(job_id).get()
        if not doc.exists:
            return None
        return JobRecord.from_dict(doc.to_dict())
    
    def put_if_not_exists(self, job: JobRecord) -> None:
        """Create job with conditional write using transaction."""
        from google.cloud.firestore_v1.base_document import DocumentSnapshot
        from google.api_core.exceptions import AlreadyExists
        
        doc_ref = self.db.collection(self.collection_name).document(job.job_id)
        
        @self.db.transactional
        def create_in_transaction(transaction):
            doc = doc_ref.get(transaction=transaction)
            if doc.exists:
                raise ConditionalCheckFailedError(f"Job {job.job_id} already exists")
            transaction.set(doc_ref, job.to_dict())
        
        try:
            transaction = self.db.transaction()
            create_in_transaction(transaction)
        except ConditionalCheckFailedError:
            raise
        except AlreadyExists as e:
            raise ConditionalCheckFailedError(f"Job {job.job_id} already exists") from e
    
    def update(self, job: JobRecord) -> None:
        """Update existing job."""
        self.db.collection(self.collection_name).document(job.job_id).set(job.to_dict())
    
    def query_by_status(
        self,
        status: list[JobStatus],
        started_before: datetime | None = None,
    ) -> list[JobRecord]:
        """Query jobs by status."""
        status_values = [s.value for s in status]
        query = self.db.collection(self.collection_name).where("status", "in", status_values)
        
        results = []
        for doc in query.stream():
            job = JobRecord.from_dict(doc.to_dict())
            if started_before and job.timing.started_at:
                started = datetime.fromisoformat(
                    job.timing.started_at.replace("Z", "+00:00")
                )
                if started >= started_before:
                    continue
            results.append(job)
        
        return results
