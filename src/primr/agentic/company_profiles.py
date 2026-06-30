"""Filesystem-backed tracked-company profiles for research memory layer 1."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from primr.utils.atomic_io import atomic_replace
from primr.utils.security import mask_sensitive_data
from primr.utils.user_cache import get_user_data_subdir
from primr.utils.validators import InputValidationError, validate_company_name, validate_url

PROFILE_SCHEMA_VERSION = 1
PROFILE_FILE_NAME = "profile.json"
EXPORT_JSON_NAME = "profile-export.json"
EXPORT_MARKDOWN_NAME = "profile-export.md"
MAX_RUN_POINTERS = 20
MAX_ARTIFACT_POINTERS = 12


def get_default_company_profile_path() -> Path:
    """Return the default durable tracked-company profile directory."""
    return get_user_data_subdir("company_profiles")


@dataclass(frozen=True)
class CompanyRunPointer:
    """Body-free pointer to one owned research run for a tracked company."""

    run_id: str
    recorded_at: str
    status: str = "completed"
    artifacts: tuple[str, ...] = ()
    manifest_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the run pointer to stable JSON-safe metadata."""
        return {
            "run_id": self.run_id,
            "recorded_at": self.recorded_at,
            "status": self.status,
            "artifacts": list(self.artifacts),
            "manifest_path": self.manifest_path,
        }

    @classmethod
    def from_value(cls, value: Any) -> CompanyRunPointer:
        """Load modern run-pointer objects and legacy string pointers."""
        if isinstance(value, dict):
            artifacts = value.get("artifacts", [])
            if not isinstance(artifacts, list):
                artifacts = []
            return cls(
                run_id=str(value.get("run_id") or value.get("id") or "unknown"),
                recorded_at=str(value.get("recorded_at") or value.get("completed_at") or "unknown"),
                status=str(value.get("status") or "completed"),
                artifacts=tuple(str(item) for item in artifacts),
                manifest_path=(
                    str(value["manifest_path"]) if value.get("manifest_path") is not None else None
                ),
            )
        return cls(
            run_id=str(value),
            recorded_at="unknown",
            status="completed",
            artifacts=(),
            manifest_path=None,
        )


@dataclass(frozen=True)
class CompanyProfile:
    """Local metadata for one tracked company."""

    schema_version: int
    name: str
    url: str
    slug: str
    created_at: str
    updated_at: str
    last_run_at: str | None = None
    run_pointers: tuple[CompanyRunPointer, ...] = ()
    retention_policy: str = "keep_until_cleared"
    classification: str = "operator_data_third_party_profile"

    @property
    def freshness_status(self) -> str:
        """Return a deterministic freshness label until run timestamps exist."""
        return "unrun" if self.last_run_at is None else "tracked"

    def to_dict(self) -> dict[str, Any]:
        """Serialize the profile to a stable JSON-safe mapping."""
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "url": self.url,
            "slug": self.slug,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_run_at": self.last_run_at,
            "freshness": {"status": self.freshness_status},
            "run_pointers": [pointer.to_dict() for pointer in self.run_pointers],
            "retention": {"policy": self.retention_policy},
            "classification": self.classification,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompanyProfile:
        """Load a profile from a JSON mapping."""
        retention = data.get("retention") if isinstance(data.get("retention"), dict) else {}
        run_pointers = data.get("run_pointers", [])
        if not isinstance(run_pointers, list):
            run_pointers = []
        return cls(
            schema_version=int(data.get("schema_version", PROFILE_SCHEMA_VERSION)),
            name=str(data["name"]),
            url=str(data["url"]),
            slug=str(data["slug"]),
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
            last_run_at=(str(data["last_run_at"]) if data.get("last_run_at") is not None else None),
            run_pointers=tuple(CompanyRunPointer.from_value(item) for item in run_pointers),
            retention_policy=str(retention.get("policy", "keep_until_cleared")),
            classification=str(data.get("classification", "operator_data_third_party_profile")),
        )


@dataclass(frozen=True)
class CompanyProfileExport:
    """Paths and payload for a tracked-company export bundle."""

    json_path: Path
    markdown_path: Path
    payload: dict[str, Any]


class CompanyProfileStore:
    """Manage local tracked-company profile folders."""

    def __init__(self, root_path: str | Path | None = None) -> None:
        if root_path is None:
            root_path = get_default_company_profile_path()
        elif isinstance(root_path, str):
            root_path = Path(root_path)
        self.root_path = root_path
        self.root_path.mkdir(parents=True, exist_ok=True)

    def track(self, name: str, url: str) -> CompanyProfile:
        """Create or update a tracked company profile."""
        clean_name = validate_company_name(name)
        clean_url = _validate_profile_url(url)
        slug = _profile_slug(clean_name)
        path = self._profile_path(slug)
        existing = self._load_profile_file(path) if path.exists() else None
        now = _utc_now()
        profile = CompanyProfile(
            schema_version=PROFILE_SCHEMA_VERSION,
            name=clean_name,
            url=clean_url,
            slug=slug,
            created_at=existing.created_at if existing else now,
            updated_at=now,
            last_run_at=existing.last_run_at if existing else None,
            run_pointers=existing.run_pointers if existing else (),
            retention_policy=existing.retention_policy if existing else "keep_until_cleared",
            classification=(
                existing.classification if existing else "operator_data_third_party_profile"
            ),
        )
        self._save_profile(profile)
        return profile

    def list_profiles(self) -> list[CompanyProfile]:
        """Return all readable tracked profiles sorted by company name."""
        profiles: list[CompanyProfile] = []
        for profile_path in self.root_path.glob(f"*/{PROFILE_FILE_NAME}"):
            try:
                profiles.append(self._load_profile_file(profile_path))
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return sorted(profiles, key=lambda profile: profile.name.casefold())

    def get_profile(self, name: str) -> CompanyProfile | None:
        """Return a tracked profile by company name, if present."""
        clean_name = validate_company_name(name)
        profile_path = self._profile_path(_profile_slug(clean_name))
        if profile_path.exists():
            return self._load_profile_file(profile_path)

        target = clean_name.casefold()
        for profile in self.list_profiles():
            if profile.name.casefold() == target:
                return profile
        return None

    def record_run(
        self,
        name: str,
        run_id: str,
        *,
        status: str = "completed",
        artifacts: list[str] | tuple[str, ...] | None = None,
        manifest_path: str | None = None,
        recorded_at: str | None = None,
    ) -> CompanyProfile:
        """Attach a bounded body-free run pointer to an existing profile."""
        profile = self.get_profile(name)
        if profile is None:
            raise InputValidationError("company_name", "Tracked company profile not found")

        pointer = _build_run_pointer(
            run_id,
            status=status,
            artifacts=artifacts or (),
            manifest_path=manifest_path,
            recorded_at=recorded_at or _utc_now(),
        )
        existing = [item for item in profile.run_pointers if item.run_id != pointer.run_id]
        updated = replace(
            profile,
            updated_at=_utc_now(),
            last_run_at=pointer.recorded_at,
            run_pointers=tuple([pointer, *existing][:MAX_RUN_POINTERS]),
        )
        self._save_profile(updated)
        return updated

    def export_profile(
        self,
        name: str,
        *,
        hypotheses: list[dict[str, Any]] | None = None,
    ) -> CompanyProfileExport:
        """Write a structured local export bundle for a tracked company."""
        profile = self.get_profile(name)
        if profile is None:
            raise InputValidationError("company_name", "Tracked company profile not found")

        payload = _build_export_payload(profile, hypotheses or [])
        _raise_if_secret_payload(payload)
        export_dir = self.profile_dir(profile) / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        json_path = export_dir / EXPORT_JSON_NAME
        markdown_path = export_dir / EXPORT_MARKDOWN_NAME
        _atomic_write_text(
            json_path,
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
        )
        _atomic_write_text(markdown_path, _render_export_markdown(payload))
        return CompanyProfileExport(
            json_path=json_path,
            markdown_path=markdown_path,
            payload=payload,
        )

    def profile_dir(self, profile: CompanyProfile) -> Path:
        """Return the directory that contains a profile."""
        return self.root_path / profile.slug

    def _profile_path(self, slug: str) -> Path:
        return self.root_path / slug / PROFILE_FILE_NAME

    def _save_profile(self, profile: CompanyProfile) -> None:
        data = profile.to_dict()
        _raise_if_secret_payload(data)
        profile_dir = self.profile_dir(profile)
        profile_dir.mkdir(parents=True, exist_ok=True)
        path = profile_dir / PROFILE_FILE_NAME
        _atomic_write_text(path, json.dumps(data, indent=2, sort_keys=True) + "\n")

    @staticmethod
    def _load_profile_file(path: Path) -> CompanyProfile:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("company profile must be a JSON object")
        return CompanyProfile.from_dict(data)


def _profile_slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    base = base[:72].strip("-") or "company"
    digest = hashlib.sha256(name.casefold().encode("utf-8")).hexdigest()[:8]
    return f"{base}-{digest}"


def _validate_profile_url(url: str) -> str:
    clean_url = validate_url(url)
    parsed = urlparse(clean_url)
    if parsed.username or parsed.password:
        raise InputValidationError("url", "Company profile URL cannot contain userinfo")
    if mask_sensitive_data(clean_url) != clean_url:
        raise InputValidationError("url", "Company profile URL contains a secret-like value")
    return clean_url


def _build_run_pointer(
    run_id: str,
    *,
    status: str,
    artifacts: list[str] | tuple[str, ...],
    manifest_path: str | None,
    recorded_at: str,
) -> CompanyRunPointer:
    return CompanyRunPointer(
        run_id=_clean_pointer_text("run_id", run_id),
        recorded_at=_clean_pointer_text("recorded_at", recorded_at),
        status=_clean_pointer_text("status", status),
        artifacts=tuple(
            _clean_pointer_text("artifact", str(item))
            for item in list(artifacts)[:MAX_ARTIFACT_POINTERS]
        ),
        manifest_path=(
            _clean_pointer_text("manifest_path", manifest_path)
            if manifest_path is not None
            else None
        ),
    )


def _clean_pointer_text(field: str, value: str) -> str:
    text = value.strip()
    if not text:
        raise InputValidationError(field, "Run pointer value cannot be empty")
    if len(text) > 1024:
        raise InputValidationError(field, "Run pointer value is too long")
    if "\x00" in text or "\n" in text or "\r" in text:
        raise InputValidationError(field, "Run pointer value must be single-line text")
    if mask_sensitive_data(text) != text:
        raise InputValidationError(field, "Run pointer value contains a secret-like value")
    return text


def _build_export_payload(
    profile: CompanyProfile,
    hypotheses: list[dict[str, Any]],
) -> dict[str, Any]:
    gaps = [
        {
            "id": "claim_store",
            "status": "missing",
            "reason": "Layer 2 claim store is not implemented yet.",
        },
    ]
    if not profile.run_pointers:
        gaps.append(
            {
                "id": "run_history",
                "status": "missing",
                "reason": "No run-history pointers were found for this company.",
            }
        )
    if not hypotheses:
        gaps.append(
            {
                "id": "hypotheses",
                "status": "empty",
                "reason": "No persisted hypotheses were found for this company.",
            }
        )

    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "type": "Company",
        "company": profile.to_dict(),
        "run_history": [pointer.to_dict() for pointer in profile.run_pointers],
        "hypotheses": hypotheses,
        "flagged_gaps": gaps,
        "bundle": {
            "json": EXPORT_JSON_NAME,
            "markdown": EXPORT_MARKDOWN_NAME,
        },
    }


def _render_export_markdown(payload: dict[str, Any]) -> str:
    company = payload["company"]
    lines = [
        "---",
        "type: Company",
        f"schema_version: {payload['schema_version']}",
        f"name: {_yaml_string(company['name'])}",
        f"url: {_yaml_string(company['url'])}",
        f"freshness: {_yaml_string(company['freshness']['status'])}",
        "---",
        "",
        f"# {company['name']}",
        "",
        f"- URL: {company['url']}",
        f"- Freshness: {company['freshness']['status']}",
        f"- Last run: {company['last_run_at'] or 'none'}",
        f"- Retention: {company['retention']['policy']}",
        "",
        "## Run History",
        "",
    ]
    run_history = payload["run_history"]
    if run_history:
        for pointer in run_history:
            lines.append(
                f"- {pointer['run_id']} [{pointer['status']}] recorded {pointer['recorded_at']}"
            )
            if pointer.get("manifest_path"):
                lines.append(f"  - Manifest: {pointer['manifest_path']}")
            for artifact in pointer.get("artifacts", []):
                lines.append(f"  - Artifact: {artifact}")
    else:
        lines.append("- No run-history pointers found.")

    lines.extend(
        [
            "",
            "## Hypotheses",
            "",
        ]
    )
    hypotheses = payload["hypotheses"]
    if hypotheses:
        for hypothesis in hypotheses:
            confidence = hypothesis.get("confidence", "untested")
            claim = hypothesis.get("claim", "")
            topic = hypothesis.get("topic") or "uncategorized"
            lines.append(f"- [{confidence}] {claim} (topic: {topic})")
    else:
        lines.append("- No persisted hypotheses found.")

    lines.extend(["", "## Flagged Gaps", ""])
    for gap in payload["flagged_gaps"]:
        lines.append(f"- {gap['id']}: {gap['status']} - {gap['reason']}")

    return "\n".join(lines) + "\n"


def _yaml_string(value: str) -> str:
    return json.dumps(value)


def _atomic_write_text(path: Path, content: str) -> None:
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    atomic_replace(tmp_path, path)


def _raise_if_secret_payload(value: Any, path: str = "profile") -> None:
    if isinstance(value, str):
        if mask_sensitive_data(value) != value:
            raise InputValidationError(
                "company_profile",
                f"Profile contains a secret-like value at {path}",
            )
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _raise_if_secret_payload(item, f"{path}.{key}")
        return
    if isinstance(value, list | tuple):
        for index, item in enumerate(value):
            _raise_if_secret_payload(item, f"{path}[{index}]")


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
