import logging
import os

import azure.functions as func
from azure.identity import DefaultAzureCredential

from deploy.control_plane.job_store import CosmosStore
from deploy.control_plane.reconciler import Reconciler, ReconciliationConfig
from deploy.storage import BlobStore


def main(timer: func.TimerRequest) -> None:
    """Timer-triggered reconciliation function."""
    logging.info("Reconciler function triggered")

    # Get configuration from environment
    cosmos_endpoint = os.environ.get("COSMOS_ENDPOINT")
    storage_account_name = os.environ.get("STORAGE_ACCOUNT_NAME")
    deployment = os.environ.get("DEPLOYMENT", "prod")
    database = os.environ.get("COSMOS_DATABASE", "primr")
    container = os.environ.get("COSMOS_CONTAINER", "jobs")
    storage_container = os.environ.get("STORAGE_CONTAINER", "artifacts")

    # Use DefaultAzureCredential (managed identity) instead of connection strings
    credential = DefaultAzureCredential()

    # Create stores using managed identity
    job_store = CosmosStore(
        endpoint=cosmos_endpoint,
        credential=credential,
        database_name=database,
        container_name=container,
    )
    artifact_store = BlobStore(
        container_name=storage_container,
        deployment=deployment,
        account_name=storage_account_name,
        credential=credential,
    )

    # Create reconciler with config
    config = ReconciliationConfig(
        max_duration_seconds=7200,  # 2 hours
        cancellation_grace_seconds=300,  # 5 minutes
        heartbeat_stale_seconds=600,  # 10 minutes
    )
    reconciler = Reconciler(job_store, artifact_store, config)

    # Run reconciliation
    result = reconciler.reconcile()

    logging.info(f"Reconciliation complete: {result.to_dict()}")
