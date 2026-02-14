"""Minimal auth provider types."""

from dataclasses import dataclass


@dataclass
class AccessToken:
    token: str
    client_id: str
    scopes: list[str]
    expires_at: float | int | None = None

