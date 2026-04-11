"""
Cloud environment auto-detection.

Detects whether the MCP server is running in a cloud (Azure) deployment
or locally, based on the presence of Azure-specific environment variables.

Requirements: 11.2, 11.3
"""

import os

# Environment variables that indicate cloud (Azure) deployment
CLOUD_ENV_VARS = (
    "AZURE_CLIENT_ID",
    "COSMOS_ENDPOINT",
    "STORAGE_ACCOUNT_NAME",
)


def is_cloud_mode() -> bool:
    """
    Detect whether the server is running in cloud mode.

    Cloud mode is detected when any of the Azure-specific environment
    variables are set: AZURE_CLIENT_ID, COSMOS_ENDPOINT, STORAGE_ACCOUNT_NAME.

    Returns:
        True if running in cloud mode, False for local mode.
    """
    return any(os.environ.get(var) for var in CLOUD_ENV_VARS)
