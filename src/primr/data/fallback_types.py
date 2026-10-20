"""Shared fallback result and HTTP callback contracts, without orchestration imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class HttpGet(Protocol):
    """The closed, SSRF-safe HTTP seam used by first-party recovery adapters."""

    def __call__(
        self,
        url: str,
        timeout: float = 15.0,
        headers: dict[str, str] | None = None,
        params: dict[str, str | int] | None = None,
    ) -> tuple[int | None, bytes | None, str | None]:
        """Return status, body, and content type through the guarded HTTP seam."""


@dataclass
class FallbackPage:
    """A page of content recovered from a fallback source."""

    url: str
    source: str  # "subdomain" | "feed" | "first_party_pdf" | "structured_data" | ...
    content: str  # extracted plain text
    raw_html: bytes | None = None
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
