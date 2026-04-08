"""Minimal bearer-auth middleware shims."""

from typing import Any


class BearerAuthBackend:
    def __init__(self, verifier: Any):
        self.verifier = verifier


class RequireAuthMiddleware:
    def __init__(self, backend: BearerAuthBackend):
        self.backend = backend

    def __call__(self, app: Any) -> Any:
        return app
