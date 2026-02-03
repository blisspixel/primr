"""
Cancellation Logic - Provider-specific job cancellation.

This module provides cancellation logic for different cloud providers:
- AWS: ECS StopTask
- Azure: Container Apps Jobs stop
- GCP: Cloud Run Jobs cancel

Key features:
- Provider-specific stop APIs
- QUEUED → CANCELLED immediate transition
- RUNNING → CANCEL_REQUESTED → CANCELLED/FAILED transitions

Requirements: 3.12, 3.13, 3.14
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from deploy.control_plane.job_store import JobRecord, JobStatus, JobStore


class CancellationResult(str, Enum):
    """Result of cancellation attempt."""
    CANCELLED = "CANCELLED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    ALREADY_COMPLETED = "ALREADY_COMPLETED"
    NOT_FOUND = "NOT_FOUND"
    FAILED = "FAILED"


@dataclass
class CancelResponse:
    """Response from cancellation attempt."""
    result: CancellationResult
    status: JobStatus
    message: str


@runtime_checkable
class ProviderCancellation(Protocol):
    """Protocol for provider-specific cancellation."""
    
    def stop_job(self, execution_id: str) -> bool:
        """
        Stop a running job.
        
        Args:
            execution_id: Provider-specific execution ID
            
        Returns:
            True if job was stopped immediately, False if stop is pending
        """
        ...


class NoOpCancellation:
    """No-op cancellation for testing."""
    
    def stop_job(self, execution_id: str) -> bool:
        """Always returns True (immediate stop)."""
        return True


class ECSCancellation:
    """
    AWS ECS cancellation.
    
    Uses StopTask to send SIGTERM, waits stopTimeout, then SIGKILL.
    """
    
    def __init__(
        self,
        cluster: str,
        region: str | None = None,
        client: Any = None,
    ) -> None:
        """
        Initialize ECS cancellation.
        
        Args:
            cluster: ECS cluster name or ARN
            region: AWS region
            client: Optional boto3 ECS client (for testing)
        """
        self.cluster = cluster
        self.region = region
        self._client = client
    
    @property
    def client(self) -> Any:
        """Get or create boto3 ECS client."""
        if self._client is None:
            import boto3
            self._client = boto3.client("ecs", region_name=self.region)
        return self._client
    
    def stop_job(self, execution_id: str) -> bool:
        """
        Stop an ECS task.
        
        Args:
            execution_id: ECS task ARN
            
        Returns:
            True if task was stopped, False if stop is pending
        """
        try:
            response = self.client.stop_task(
                cluster=self.cluster,
                task=execution_id,
                reason="User requested cancellation",
            )
            
            # Check if task is already stopped
            task = response.get("task", {})
            last_status = task.get("lastStatus", "")
            
            return last_status in ("STOPPED", "DEPROVISIONING")
        except Exception as e:
            # Task might not exist or already stopped
            if "TaskNotFoundException" in str(type(e)):
                return True
            raise


class StepFunctionsCancellation:
    """
    AWS Step Functions cancellation.
    
    Uses StopExecution to stop the state machine execution.
    """
    
    def __init__(
        self,
        region: str | None = None,
        client: Any = None,
    ) -> None:
        """
        Initialize Step Functions cancellation.
        
        Args:
            region: AWS region
            client: Optional boto3 Step Functions client (for testing)
        """
        self.region = region
        self._client = client
    
    @property
    def client(self) -> Any:
        """Get or create boto3 Step Functions client."""
        if self._client is None:
            import boto3
            self._client = boto3.client("stepfunctions", region_name=self.region)
        return self._client
    
    def stop_job(self, execution_id: str) -> bool:
        """
        Stop a Step Functions execution.
        
        Args:
            execution_id: Step Functions execution ARN
            
        Returns:
            True if execution was stopped
        """
        try:
            self.client.stop_execution(
                executionArn=execution_id,
                cause="User requested cancellation",
            )
            return True
        except Exception as e:
            if "ExecutionDoesNotExist" in str(type(e)):
                return True
            raise


class ContainerAppsCancellation:
    """
    Azure Container Apps Jobs cancellation.
    
    Sends SIGTERM, then SIGKILL after grace period.
    """
    
    def __init__(
        self,
        resource_group: str,
        job_name: str,
        subscription_id: str | None = None,
        client: Any = None,
    ) -> None:
        """
        Initialize Container Apps cancellation.
        
        Args:
            resource_group: Azure resource group
            job_name: Container Apps job name
            subscription_id: Azure subscription ID
            client: Optional ContainerAppsClient (for testing)
        """
        self.resource_group = resource_group
        self.job_name = job_name
        self.subscription_id = subscription_id
        self._client = client
    
    @property
    def client(self) -> Any:
        """Get or create Container Apps client."""
        if self._client is None:
            from azure.mgmt.appcontainers import ContainerAppsAPIClient
            from azure.identity import DefaultAzureCredential
            
            credential = DefaultAzureCredential()
            self._client = ContainerAppsAPIClient(credential, self.subscription_id)
        return self._client
    
    def stop_job(self, execution_id: str) -> bool:
        """
        Stop a Container Apps job execution.
        
        Args:
            execution_id: Job execution name
            
        Returns:
            True if job was stopped
        """
        try:
            self.client.jobs.stop_execution(
                resource_group_name=self.resource_group,
                job_name=self.job_name,
                job_execution_name=execution_id,
            )
            return True
        except Exception:
            return False


class CloudRunJobsCancellation:
    """
    GCP Cloud Run Jobs cancellation.
    
    Sends SIGTERM, then SIGKILL after 10s.
    """
    
    def __init__(
        self,
        project: str,
        location: str,
        job_name: str,
        client: Any = None,
    ) -> None:
        """
        Initialize Cloud Run Jobs cancellation.
        
        Args:
            project: GCP project ID
            location: GCP region
            job_name: Cloud Run job name
            client: Optional Cloud Run client (for testing)
        """
        self.project = project
        self.location = location
        self.job_name = job_name
        self._client = client
    
    @property
    def client(self) -> Any:
        """Get or create Cloud Run client."""
        if self._client is None:
            from google.cloud import run_v2
            self._client = run_v2.ExecutionsClient()
        return self._client
    
    def stop_job(self, execution_id: str) -> bool:
        """
        Cancel a Cloud Run job execution.
        
        Args:
            execution_id: Execution name
            
        Returns:
            True if job was cancelled
        """
        try:
            # Cloud Run Jobs uses cancel_execution
            name = f"projects/{self.project}/locations/{self.location}/jobs/{self.job_name}/executions/{execution_id}"
            self.client.cancel_execution(name=name)
            return True
        except Exception:
            return False


class CancellationService:
    """
    Service for handling job cancellation.
    
    Coordinates between job store and provider-specific cancellation.
    """
    
    def __init__(
        self,
        job_store: JobStore,
        provider: ProviderCancellation | None = None,
    ) -> None:
        """
        Initialize cancellation service.
        
        Args:
            job_store: Job state store
            provider: Provider-specific cancellation (optional)
        """
        self.job_store = job_store
        self.provider = provider or NoOpCancellation()
    
    def cancel_job(self, job_id: str) -> CancelResponse:
        """
        Cancel a job.
        
        State transitions:
        - QUEUED → CANCELLED (immediate)
        - RUNNING → CANCEL_REQUESTED (stop signal sent)
        - PENDING_APPROVAL → CANCELLED (immediate)
        - Already completed → no change
        
        Args:
            job_id: Job ID to cancel
            
        Returns:
            CancelResponse with result and message
        """
        from datetime import datetime, timezone
        from deploy.control_plane.job_store import format_timestamp, utc_now
        
        job = self.job_store.get(job_id)
        if not job:
            return CancelResponse(
                result=CancellationResult.NOT_FOUND,
                status=JobStatus.CANCELLED,  # Placeholder
                message=f"Job {job_id} not found",
            )
        
        # Already completed - no action needed
        if job.status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED):
            return CancelResponse(
                result=CancellationResult.ALREADY_COMPLETED,
                status=job.status,
                message=f"Job already completed with status {job.status.value}",
            )
        
        # QUEUED or PENDING_APPROVAL - cancel immediately
        if job.status in (JobStatus.QUEUED, JobStatus.PENDING_APPROVAL):
            job.status = JobStatus.CANCELLED
            job.timing.completed_at = format_timestamp(utc_now())
            self.job_store.update(job)
            return CancelResponse(
                result=CancellationResult.CANCELLED,
                status=JobStatus.CANCELLED,
                message="Job cancelled before execution",
            )
        
        # RUNNING - request cancellation from provider
        if job.status == JobStatus.RUNNING:
            if job.execution_id:
                try:
                    stopped = self.provider.stop_job(job.execution_id)
                    if stopped:
                        job.status = JobStatus.CANCELLED
                        job.timing.completed_at = format_timestamp(utc_now())
                        self.job_store.update(job)
                        return CancelResponse(
                            result=CancellationResult.CANCELLED,
                            status=JobStatus.CANCELLED,
                            message="Job cancelled",
                        )
                    else:
                        job.status = JobStatus.CANCEL_REQUESTED
                        self.job_store.update(job)
                        return CancelResponse(
                            result=CancellationResult.CANCEL_REQUESTED,
                            status=JobStatus.CANCEL_REQUESTED,
                            message="Cancellation requested, awaiting runner exit",
                        )
                except Exception as e:
                    return CancelResponse(
                        result=CancellationResult.FAILED,
                        status=job.status,
                        message=f"Failed to stop job: {str(e)}",
                    )
            else:
                # No execution_id - mark as cancel requested
                job.status = JobStatus.CANCEL_REQUESTED
                self.job_store.update(job)
                return CancelResponse(
                    result=CancellationResult.CANCEL_REQUESTED,
                    status=JobStatus.CANCEL_REQUESTED,
                    message="Cancellation requested",
                )
        
        # CANCEL_REQUESTED - already cancelling
        if job.status == JobStatus.CANCEL_REQUESTED:
            return CancelResponse(
                result=CancellationResult.CANCEL_REQUESTED,
                status=JobStatus.CANCEL_REQUESTED,
                message="Cancellation already in progress",
            )
        
        # Unknown state
        return CancelResponse(
            result=CancellationResult.FAILED,
            status=job.status,
            message=f"Cannot cancel job in state {job.status.value}",
        )
