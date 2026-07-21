"""Azure AI Foundry provider.

Microsoft Foundry (formerly Azure AI Studio / Azure OpenAI) exposes an
OpenAI-compatible surface at ``.../openai/v1/``, callable with the plain
``openai`` SDK using an API key plus the resource base URL. This provider is a
thin :class:`OpenAICompatibleProvider` that resolves that per-user base URL from
the environment, so it inherits chat, usage accounting, retry/backoff, and the
free ``models.list`` credential probe unchanged.

Env:
- ``AZURE_OPENAI_API_KEY`` — the resource/project key (Bearer auth).
- ``AZURE_OPENAI_BASE_URL`` — the full OpenAI-compatible base, e.g.
  ``https://<resource>.openai.azure.com/openai/v1/`` or the Foundry project form
  ``https://<account>.services.ai.azure.com/api/projects/<project>/openai/v1/``.
- ``AZURE_OPENAI_ENDPOINT`` — alternative to BASE_URL; the resource root
  (``https://<resource>.openai.azure.com``), from which the ``/openai/v1/`` base
  is derived.

The model id passed to a call is the Azure *deployment name*.
"""

from __future__ import annotations

import os

from primr.ai.providers.base import CredentialCheck
from primr.ai.providers.openai_compatible import OpenAICompatibleProvider

AZURE_FOUNDRY_API_KEY_ENV = "AZURE_OPENAI_API_KEY"
_UNRESOLVED_BASE_URL = "https://azure-openai-base-url-unset.invalid/openai/v1"


def resolve_foundry_base_url() -> str | None:
    """Resolve the OpenAI-compatible base URL for Azure Foundry from the env.

    Returns ``None`` when neither ``AZURE_OPENAI_BASE_URL`` nor
    ``AZURE_OPENAI_ENDPOINT`` is set, so callers can treat the provider as
    unconfigured rather than hitting a placeholder host.
    """
    explicit = os.getenv("AZURE_OPENAI_BASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    if endpoint:
        root = endpoint.rstrip("/")
        # Already an /openai/v1 style base? Use as-is; otherwise derive it.
        if "/openai/v1" in root:
            return root
        return f"{root}/openai/v1"
    return None


class AzureFoundryProvider(OpenAICompatibleProvider):
    """Azure AI Foundry via its OpenAI-compatible endpoint."""

    def __init__(self) -> None:
        super().__init__(
            name="foundry",
            base_url=resolve_foundry_base_url() or _UNRESOLVED_BASE_URL,
            api_key_env=AZURE_FOUNDRY_API_KEY_ENV,
            billing_help_url="https://ai.azure.com/",
        )

    def is_available(self) -> bool:
        """Available only when the key AND a resolvable base URL are configured."""
        if resolve_foundry_base_url() is None:
            return False
        return super().is_available()

    def validate_credentials(self) -> CredentialCheck:
        if resolve_foundry_base_url() is None:
            return CredentialCheck(
                provider=self.name,
                ok=False,
                detail="AZURE_OPENAI_BASE_URL or AZURE_OPENAI_ENDPOINT not set",
            )
        # Re-resolve in case the env changed since construction.
        self._base_url = resolve_foundry_base_url() or _UNRESOLVED_BASE_URL
        self._client = None
        return super().validate_credentials()
