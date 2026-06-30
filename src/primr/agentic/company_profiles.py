"""Filesystem-backed tracked-company profiles for research memory layer 1."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
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


def get_default_company_profile_path() -> Path:
    """Return the default durable tracked-company profile directory."""
    return get_user_data_subdir("company_profiles")


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
    run_pointers: tuple[str, ...] = ()
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
            "run_pointers": list(self.run_pointers),
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
            run_pointers=tuple(str(item) for item in run_pointers),
            retention_policy=str(retention.get("policy", "keep_until_cleared")),
            classification=str(data.get("classification", "operator_data_third_party_profile")),
        )


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
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        atomic_replace(tmp_path, path)

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
