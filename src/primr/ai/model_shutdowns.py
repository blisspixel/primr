"""Compare registered OpenAI model lifecycles with live shutdown metadata.

OpenAI's free ``GET /v1/models`` rows carry an optional ``shutdown_date``
field: a ``YYYY-MM-DD`` string, or null when no shutdown is announced. This
module reads those rows and reports registered models whose live shutdown the
registry does not record yet. It is report-only: it never edits the registry,
routing, or any configuration.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal

ShutdownStatus = Literal["unrecorded", "date_mismatch"]
LOOKUP_TIMEOUT_SECONDS = 10.0


class ShutdownLookupError(RuntimeError):
    """The live model list could not be read; ``reason`` is a fixed code."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class RecordedLifecycle:
    """What the registry records about one OpenAI model."""

    expiration_date: date | None
    replacement_model: str | None = None


@dataclass(frozen=True)
class ShutdownFinding:
    """A live shutdown date that the registry does not record."""

    model: str
    status: ShutdownStatus
    live_date: date
    recorded_date: date | None
    replacement_model: str | None
    past: bool


@dataclass(frozen=True)
class ShutdownReport:
    """Comparison of registered OpenAI models with the live model list."""

    checked: int
    findings: tuple[ShutdownFinding, ...]
    # Registered with a date, but OpenAI's row announces none (withdrawn or extended).
    unannounced: tuple[str, ...] = ()
    # Absent from the live list with no recorded retirement: removed, or no key access.
    unlisted: tuple[str, ...] = ()
    # Absent from the live list after the registry's recorded retirement date.
    unlisted_retired: tuple[str, ...] = ()


def _field(row: Any, name: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(name)
    value = getattr(row, name, None)
    if value is None:
        extra = getattr(row, "model_extra", None)
        if isinstance(extra, Mapping):
            value = extra.get(name)
    return value


def parse_live_shutdowns(rows: Iterable[Any]) -> dict[str, date | None]:
    """Map each listed model ID to its announced shutdown date, if any.

    Rows may be SDK model objects or plain mappings. A missing, null, or
    unparseable ``shutdown_date`` is treated as not announced.
    """
    live: dict[str, date | None] = {}
    for row in rows:
        model_id = _field(row, "id")
        if not isinstance(model_id, str) or not model_id.strip():
            continue
        raw = _field(row, "shutdown_date")
        shutdown: date | None = None
        if isinstance(raw, str):
            try:
                shutdown = date.fromisoformat(raw.strip())
            except ValueError:
                shutdown = None
        live[model_id.strip()] = shutdown
    return live


def registered_openai_lifecycles() -> dict[str, RecordedLifecycle]:
    """Return every OpenAI model ID the registry can select, with its lifecycle."""
    from primr.config.models import ModelRegistry, PrimrModels

    recorded = {
        model.name: RecordedLifecycle(model.expiration_date, model.replacement_model)
        for model in ModelRegistry.OPENAI_MODELS
    }
    recorded.setdefault(PrimrModels.OPENAI_IMAGE_MODEL, RecordedLifecycle(None))
    return recorded


def compare_shutdowns(
    recorded: Mapping[str, RecordedLifecycle],
    live: Mapping[str, date | None],
    today: date,
) -> ShutdownReport:
    """Report registered models whose live shutdown date is not recorded.

    A model is unavailable on its shutdown date (``require_available`` uses
    the same rule), so a live date on or before ``today`` is past. Registered
    models absent from the live list are returned separately, split by
    whether the registry already records them as retired.
    """
    findings: list[ShutdownFinding] = []
    unannounced: list[str] = []
    unlisted: list[str] = []
    unlisted_retired: list[str] = []
    checked = 0
    for name in sorted(recorded):
        lifecycle = recorded[name]
        if name not in live:
            retired = lifecycle.expiration_date is not None and lifecycle.expiration_date <= today
            (unlisted_retired if retired else unlisted).append(name)
            continue
        checked += 1
        live_date = live[name]
        if live_date is None:
            if lifecycle.expiration_date is not None:
                unannounced.append(name)
            continue
        if live_date == lifecycle.expiration_date:
            continue
        findings.append(
            ShutdownFinding(
                model=name,
                status="unrecorded" if lifecycle.expiration_date is None else "date_mismatch",
                live_date=live_date,
                recorded_date=lifecycle.expiration_date,
                replacement_model=lifecycle.replacement_model,
                past=live_date <= today,
            )
        )
    return ShutdownReport(
        checked=checked,
        findings=tuple(findings),
        unannounced=tuple(unannounced),
        unlisted=tuple(unlisted),
        unlisted_retired=tuple(unlisted_retired),
    )


def fetch_openai_model_rows() -> list[Any]:
    """List OpenAI models through the provider seam after the SSRF guard."""
    from primr.ai.providers import KNOWN_PROVIDERS, build_provider
    from primr.ai.providers.openai_compatible import OpenAICompatibleProvider
    from primr.utils.url_security import is_safe_url

    entry = next(entry for entry in KNOWN_PROVIDERS if entry.name == "openai")
    provider = build_provider(entry)
    if not isinstance(provider, OpenAICompatibleProvider):
        raise ShutdownLookupError("provider_shape")
    safe, _reason = is_safe_url(provider.base_url)
    if not safe:
        # The guard resolves DNS, so an offline machine also stops here.
        raise ShutdownLookupError("ssrf_guard_or_dns")
    return provider.list_models(timeout=LOOKUP_TIMEOUT_SECONDS)


def check_openai_shutdowns(
    *,
    today: date | None = None,
    list_rows: Callable[[], Iterable[Any]] | None = None,
) -> ShutdownReport:
    """Compare the registry with OpenAI's live shutdown dates (one free call)."""
    rows = (list_rows or fetch_openai_model_rows)()
    return compare_shutdowns(
        registered_openai_lifecycles(),
        parse_live_shutdowns(rows),
        today or datetime.now(UTC).date(),
    )
