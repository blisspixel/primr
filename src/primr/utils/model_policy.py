"""Process-local policy for workflows that must not call model backends."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from concurrent.futures import Executor, Future
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from typing import ParamSpec, TypeVar

__all__ = [
    "ModelCallsDisabledError",
    "disable_model_calls",
    "model_calls_disabled",
    "require_model_calls_allowed",
    "submit_with_model_policy",
]

_MODEL_CALLS_DISABLED: ContextVar[bool] = ContextVar(
    "primr_model_calls_disabled",
    default=False,
)
_DISABLE_MODEL_CALLS_ENV = "PRIMR_DISABLE_MODEL_CALLS"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_P = ParamSpec("_P")
_T = TypeVar("_T")


class ModelCallsDisabledError(RuntimeError):
    """Raised before model egress when the current workflow forbids it."""


def model_calls_disabled() -> bool:
    """Return whether the current context explicitly forbids model calls."""

    if _MODEL_CALLS_DISABLED.get():
        return True
    return os.getenv(_DISABLE_MODEL_CALLS_ENV, "").strip().lower() in _TRUE_VALUES


def require_model_calls_allowed(operation: str = "model call") -> None:
    """Fail before provider egress when model calls are disabled."""

    if model_calls_disabled():
        raise ModelCallsDisabledError(f"{operation} is disabled for this workflow")


@contextmanager
def disable_model_calls() -> Iterator[None]:
    """Disable model calls for the current execution context."""

    token = _MODEL_CALLS_DISABLED.set(True)
    try:
        yield
    finally:
        _MODEL_CALLS_DISABLED.reset(token)


def submit_with_model_policy(
    executor: Executor,
    function: Callable[_P, _T],
    /,
    *args: _P.args,
    **kwargs: _P.kwargs,
) -> Future[_T]:
    """Submit work with an isolated copy of the caller's model policy."""

    context = copy_context()

    def invoke() -> _T:
        return context.run(function, *args, **kwargs)

    return executor.submit(invoke)
