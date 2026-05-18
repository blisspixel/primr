"""
Queryable interface to ROADMAP.md.

This module provides a structured API for querying roadmap data,
transforming the markdown document into a queryable data structure.
It supports:

- Version and feature status queries
- Dependency graph analysis
- Blocker identification
- JSON serialization for MCP exposure
- Automatic cache invalidation on file changes

The parser handles the specific markdown format used in primr's
ROADMAP.md, extracting version sections, feature lists, and status
indicators.

Example:
    from primr.agentic.roadmap_api import RoadmapAPI, VersionStatus

    api = RoadmapAPI()

    # Get a specific version
    v170 = api.get_version("1.7.0")

    # List planned versions
    planned = api.list_by_status(VersionStatus.PLANNED)

    # Get blockers for a version
    blockers = api.get_blockers("1.7.0")

    # Get dependency graph
    graph = api.get_dependency_graph()
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from primr.agentic.errors import RoadmapParseError
from primr.agentic.models import Feature, Version, VersionStatus

logger = logging.getLogger(__name__)


class RoadmapAPI:
    """
    Queryable interface to ROADMAP.md content.

    RoadmapAPI parses the roadmap markdown file into structured data
    and provides query methods for version information, dependencies,
    and blockers. It automatically reloads when the file changes.

    Attributes:
        roadmap_path: Path to the ROADMAP.md file

    Example:
        api = RoadmapAPI()

        # Query version status
        version = api.get_version("1.7.0")
        if version and version.status == VersionStatus.PLANNED:
            print(f"v{version.number} is planned: {version.title}")

        # Check for blockers
        blockers = api.get_blockers("1.7.0")
        if blockers:
            print(f"Blocked by: {', '.join(blockers)}")
    """

    # Regex patterns for parsing
    VERSION_HEADER_PATTERN = re.compile(
        r"^###?\s+v?(\d+\.\d+(?:\.\d+)?)\s*[-–—]\s*(.+?)(?:\s*\(([^)]+)\))?\s*$",
        re.IGNORECASE,
    )
    FEATURE_PATTERN = re.compile(
        r"^[-*]\s+\*?\*?(.+?)\*?\*?(?::\s*(.+))?$",
    )
    STATUS_KEYWORDS = {
        "complete": VersionStatus.COMPLETED,
        "completed": VersionStatus.COMPLETED,
        "done": VersionStatus.COMPLETED,
        "in progress": VersionStatus.IN_PROGRESS,
        "in-progress": VersionStatus.IN_PROGRESS,
        "current": VersionStatus.IN_PROGRESS,
        "planned": VersionStatus.PLANNED,
        "upcoming": VersionStatus.PLANNED,
        "deferred": VersionStatus.DEFERRED,
        "postponed": VersionStatus.DEFERRED,
    }

    def __init__(self, roadmap_path: Path | str | None = None):
        """
        Initialize the RoadmapAPI.

        Args:
            roadmap_path: Path to ROADMAP.md (default: ROADMAP.md in cwd)
        """
        if roadmap_path is None:
            roadmap_path = Path("ROADMAP.md")
        elif isinstance(roadmap_path, str):
            roadmap_path = Path(roadmap_path)

        self._path = roadmap_path
        self._versions: dict[str, Version] = {}
        self._last_modified: float = 0.0
        self._parse_errors: list[str] = []

    @property
    def roadmap_path(self) -> Path:
        """Get the roadmap file path."""
        return self._path

    @property
    def parse_errors(self) -> list[str]:
        """Get any parse errors from the last load."""
        self._ensure_loaded()
        return list(self._parse_errors)

    def _ensure_loaded(self) -> None:
        """Reload if file changed since last load."""
        if not self._path.exists():
            logger.warning(f"Roadmap file not found: {self._path}")
            self._versions = {}
            return

        try:
            mtime = self._path.stat().st_mtime
            if mtime > self._last_modified:
                self._parse_roadmap()
                self._last_modified = mtime
        except OSError as e:
            logger.error(f"Cannot access roadmap file: {e}")
            raise RoadmapParseError(
                message=f"Cannot access roadmap file: {e}",
                line=0,
                cause=e,
            ) from e

    def _parse_roadmap(self) -> None:
        """
        Parse ROADMAP.md into structured data.

        This method handles the specific markdown format used in primr's
        roadmap, extracting version sections and their features.
        """
        self._versions = {}
        self._parse_errors = []

        try:
            content = self._path.read_text(encoding="utf-8")
        except OSError as e:
            raise RoadmapParseError(
                message=f"Cannot read roadmap file: {e}",
                line=0,
                cause=e,
            ) from e

        lines = content.split("\n")
        current_version: Version | None = None
        current_section: str = ""
        line_num = 0

        for line in lines:
            line_num += 1
            stripped = line.strip()

            # Skip empty lines
            if not stripped:
                continue

            # Check for version header
            version_match = self.VERSION_HEADER_PATTERN.match(stripped)
            if version_match:
                # Save previous version
                if current_version:
                    self._versions[current_version.number] = current_version

                version_num = version_match.group(1)
                title = version_match.group(2).strip()
                status_hint = version_match.group(3)

                # Determine status from hint or title
                status = self._parse_status(status_hint or title)

                current_version = Version(
                    number=version_num,
                    title=title,
                    status=status,
                )
                current_section = ""
                continue

            # Check for section headers within a version
            if stripped.startswith("**") and stripped.endswith("**"):
                current_section = stripped.strip("*").lower()
                continue

            # Check for feature items
            if current_version and (stripped.startswith(("-", "*"))):
                feature = self._parse_feature(stripped, current_section)
                if feature:
                    current_version.features.append(feature)

            # Check for "Completed Work" or similar section headers
            if "completed" in stripped.lower() and "###" in line:
                current_section = "completed"

            # Check for "Planned" or "Near-Term" sections
            if any(kw in stripped.lower() for kw in ["planned", "near-term", "roadmap"]):
                if "###" in line or "##" in line:
                    current_section = "planned"

        # Save last version
        if current_version:
            self._versions[current_version.number] = current_version

        # Infer dependencies from version numbers
        self._infer_dependencies()

        logger.debug(f"Parsed {len(self._versions)} versions from roadmap")

    def _parse_status(self, text: str) -> VersionStatus:
        """
        Parse status from text.

        Args:
            text: Text that may contain status keywords

        Returns:
            Parsed VersionStatus (defaults to PLANNED)
        """
        text_lower = text.lower()
        for keyword, status in self.STATUS_KEYWORDS.items():
            if keyword in text_lower:
                return status
        return VersionStatus.PLANNED

    def _parse_feature(self, line: str, section: str) -> Feature | None:
        """
        Parse a feature from a list item.

        Args:
            line: The list item line
            section: Current section context

        Returns:
            Feature instance or None if not parseable
        """
        # Remove list marker
        text = re.sub(r"^[-*]\s+", "", line).strip()

        if not text:
            return None

        # Check for bold feature name
        bold_match = re.match(r"\*\*(.+?)\*\*(?::\s*(.+))?", text)
        if bold_match:
            name = bold_match.group(1)
            description = bold_match.group(2) or ""
        else:
            # Simple feature
            parts = text.split(":", 1)
            name = parts[0].strip()
            description = parts[1].strip() if len(parts) > 1 else ""

        # Determine status from section context
        if section == "completed":
            status = VersionStatus.COMPLETED
        elif section == "planned":
            status = VersionStatus.PLANNED
        else:
            status = VersionStatus.PLANNED

        return Feature(
            name=name,
            description=description,
            status=status,
        )

    def _infer_dependencies(self) -> None:
        """
        Infer version dependencies from version numbers.

        Assumes sequential versioning where v1.7.0 depends on v1.6.0.
        """
        sorted_versions = sorted(
            self._versions.keys(),
            key=lambda v: [int(x) for x in v.split(".")],
        )

        for i, version_num in enumerate(sorted_versions):
            if i > 0:
                prev_version = sorted_versions[i - 1]
                self._versions[version_num].dependencies = [prev_version]

    def get_version(self, version: str) -> Version | None:
        """
        Get version details by number.

        Args:
            version: Version number (e.g., "1.7.0")

        Returns:
            Version instance or None if not found
        """
        self._ensure_loaded()

        # Normalize version number
        if not version.startswith("v"):
            normalized = version
        else:
            normalized = version[1:]

        return self._versions.get(normalized)

    def get_blockers(self, version: str) -> list[str]:
        """
        Get blockers for a specific version.

        Blockers include:
        - Incomplete dependencies
        - Features with explicit blockers

        Args:
            version: Version number

        Returns:
            List of blocker descriptions
        """
        self._ensure_loaded()

        v = self.get_version(version)
        if not v:
            return []

        blockers = []

        # Check dependencies
        for dep in v.dependencies:
            dep_version = self._versions.get(dep)
            if dep_version and dep_version.status != VersionStatus.COMPLETED:
                blockers.append(f"Depends on v{dep} ({dep_version.status.value})")

        # Check feature blockers
        for feature in v.features:
            blockers.extend(feature.blockers)

        return blockers

    def list_by_status(self, status: VersionStatus) -> list[Version]:
        """
        List versions by status.

        Args:
            status: Status to filter by

        Returns:
            List of versions with the specified status
        """
        self._ensure_loaded()
        return [v for v in self._versions.values() if v.status == status]

    def list_all_versions(self) -> list[Version]:
        """
        List all versions.

        Returns:
            List of all versions sorted by version number
        """
        self._ensure_loaded()
        return sorted(
            self._versions.values(),
            key=lambda v: [int(x) for x in v.number.split(".")],
        )

    def get_dependency_graph(self) -> dict[str, list[str]]:
        """
        Return version dependency graph.

        Returns:
            Dictionary mapping version numbers to their dependencies
        """
        self._ensure_loaded()
        return {v.number: v.dependencies for v in self._versions.values()}

    def get_next_version(self) -> Version | None:
        """
        Get the next planned version.

        Returns:
            The first planned version, or None if none planned
        """
        planned = self.list_by_status(VersionStatus.PLANNED)
        if not planned:
            return None

        # Sort by version number and return first
        return sorted(
            planned,
            key=lambda v: [int(x) for x in v.number.split(".")],
        )[0]

    def get_current_version(self) -> Version | None:
        """
        Get the current in-progress version.

        Returns:
            The in-progress version, or None if none in progress
        """
        in_progress = self.list_by_status(VersionStatus.IN_PROGRESS)
        return in_progress[0] if in_progress else None

    def to_json(self) -> str:
        """
        Serialize to JSON for MCP resource.

        Returns:
            JSON string representation of the roadmap
        """
        self._ensure_loaded()

        current = self.get_current_version()
        next_ver = self.get_next_version()

        return json.dumps(
            {
                "versions": [v.to_dict() for v in self.list_all_versions()],
                "dependency_graph": self.get_dependency_graph(),
                "current_version": current.number if current else None,
                "next_version": next_ver.number if next_ver else None,
            },
            indent=2,
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize to dictionary.

        Returns:
            Dictionary representation of the roadmap
        """
        self._ensure_loaded()

        return {
            "versions": {v.number: v.to_dict() for v in self._versions.values()},
            "dependency_graph": self.get_dependency_graph(),
        }

    def reload(self) -> None:
        """Force reload of the roadmap file."""
        self._last_modified = 0.0
        self._ensure_loaded()
