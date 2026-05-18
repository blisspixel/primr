"""
Persistent research memory for cross-session state.

This module implements the Research Memory system that enables primr to
maintain state across research sessions. It provides:

- Hypothesis persistence with confidence tracking
- Scraping pattern learning for company types
- Company-specific memory with YAML storage
- Query filtering by confidence, topic, and expiration

The memory system follows a file-per-company storage pattern, making it
easy to inspect, backup, and version control research state.

Storage Format:
    .primr/memory/
    ├── acme_corp.yaml
    ├── exampleco.yaml
    └── ...

Example:
    from primr.agentic.memory import ResearchMemory, ConfidenceLevel

    memory = ResearchMemory()

    # Load prior hypotheses
    hypotheses = memory.get_hypotheses("Acme Corp")

    # Save new hypotheses
    memory.save_hypotheses("Acme Corp", new_hypotheses)

    # Update confidence
    memory.update_hypothesis(
        "Acme Corp",
        "h_001",
        ConfidenceLevel.VALIDATED,
        "CTO confirmed in interview"
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from typing import Any

import yaml  # type: ignore[import-untyped]

from primr.agentic.errors import MemoryError
from primr.agentic.models import ConfidenceLevel, Hypothesis

logger = logging.getLogger(__name__)


# =============================================================================
# SCRAPE PATTERN
# =============================================================================


@dataclass
class ScrapePattern:
    """
    A scraping pattern that works for specific company types.

    Scrape patterns capture institutional knowledge about which scraping
    tiers work well for different types of companies. This enables the
    system to make smarter tier selection decisions over time.

    Attributes:
        pattern_id: Unique identifier
        company_type: Type of company (e.g., "enterprise", "startup")
        industry: Industry sector
        effective_tiers: List of tiers that work well
        success_rate: Historical success rate (0.0-1.0)
        sample_size: Number of scrapes this pattern is based on
        last_updated: When the pattern was last updated
    """

    pattern_id: str
    company_type: str
    industry: str
    effective_tiers: list[str] = field(default_factory=list)
    success_rate: float = 0.0
    sample_size: int = 0
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "pattern_id": self.pattern_id,
            "company_type": self.company_type,
            "industry": self.industry,
            "effective_tiers": self.effective_tiers,
            "success_rate": self.success_rate,
            "sample_size": self.sample_size,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScrapePattern:
        """Deserialize from dictionary."""
        return cls(
            pattern_id=data.get("pattern_id", ""),
            company_type=data.get("company_type", ""),
            industry=data.get("industry", ""),
            effective_tiers=data.get("effective_tiers", []),
            success_rate=data.get("success_rate", 0.0),
            sample_size=data.get("sample_size", 0),
            last_updated=(
                datetime.fromisoformat(data["last_updated"])
                if "last_updated" in data
                else datetime.now(timezone.utc)
            ),
        )


# =============================================================================
# COMPANY MEMORY
# =============================================================================


@dataclass
class CompanyMemory:
    """
    Memory state for a specific company.

    CompanyMemory is the aggregate root for all research state related
    to a single company. It contains hypotheses, scraping patterns,
    and research notes.

    Attributes:
        company_name: Name of the company
        hypotheses: List of research hypotheses
        scrape_patterns: List of effective scraping patterns
        research_notes: Free-form research notes
        last_researched: When the company was last researched
    """

    company_name: str
    hypotheses: list[Hypothesis] = field(default_factory=list)
    scrape_patterns: list[ScrapePattern] = field(default_factory=list)
    research_notes: list[str] = field(default_factory=list)
    last_researched: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "company_name": self.company_name,
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "scrape_patterns": [p.to_dict() for p in self.scrape_patterns],
            "research_notes": self.research_notes,
            "last_researched": (self.last_researched.isoformat() if self.last_researched else None),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompanyMemory:
        """Deserialize from dictionary."""
        return cls(
            company_name=data["company_name"],
            hypotheses=[Hypothesis.from_dict(h) for h in data.get("hypotheses", [])],
            scrape_patterns=[ScrapePattern.from_dict(p) for p in data.get("scrape_patterns", [])],
            research_notes=data.get("research_notes", []),
            last_researched=(
                datetime.fromisoformat(data["last_researched"])
                if data.get("last_researched")
                else None
            ),
        )


# =============================================================================
# RESEARCH MEMORY
# =============================================================================


class ResearchMemory:
    """
    Persistent cross-session research memory.

    ResearchMemory provides the primary interface for storing and
    retrieving research state. It uses a file-per-company storage
    pattern with YAML serialization for human readability.

    The memory system supports:
    - Hypothesis persistence with merge logic
    - Query filtering by confidence, topic, and expiration
    - Scraping pattern storage
    - JSON serialization for MCP resource exposure

    Attributes:
        storage_path: Path to the memory storage directory

    Example:
        memory = ResearchMemory()

        # Get hypotheses with filtering
        validated = memory.get_hypotheses(
            "Acme Corp",
            confidence=ConfidenceLevel.VALIDATED
        )

        # Save new hypotheses (merges with existing)
        memory.save_hypotheses("Acme Corp", new_hypotheses)

        # Update a specific hypothesis
        memory.update_hypothesis(
            "Acme Corp",
            "h_001",
            ConfidenceLevel.CONFIRMED,
            "Multiple sources confirm"
        )
    """

    def __init__(self, storage_path: Path | str | None = None):
        """
        Initialize research memory.

        Args:
            storage_path: Path to storage directory (default: .primr/memory)
        """
        if storage_path is None:
            storage_path = Path(".primr/memory")
        elif isinstance(storage_path, str):
            storage_path = Path(storage_path)

        self._storage_path = storage_path
        self._storage_path.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, CompanyMemory] = {}

    @property
    def storage_path(self) -> Path:
        """Get the storage path."""
        return self._storage_path

    def _sanitize_filename(self, company: str) -> str:
        """
        Convert company name to safe filename.

        Args:
            company: Company name

        Returns:
            Safe filename string
        """
        # Convert to lowercase, replace spaces and special chars
        safe = company.lower()
        safe = re.sub(r"[^\w\s-]", "", safe)
        safe = re.sub(r"[\s]+", "_", safe)
        return safe

    def _company_path(self, company: str) -> Path:
        """
        Get storage path for a company.

        Args:
            company: Company name

        Returns:
            Path to the company's memory file
        """
        safe_name = self._sanitize_filename(company)
        return self._storage_path / f"{safe_name}.yaml"

    def _load_company(self, company: str) -> CompanyMemory:
        """
        Load company memory from disk.

        Args:
            company: Company name

        Returns:
            CompanyMemory instance (empty if file doesn't exist)

        Raises:
            MemoryError: If file exists but cannot be parsed
        """
        # Check cache first
        cache_key = self._sanitize_filename(company)
        if cache_key in self._cache:
            return self._cache[cache_key]

        path = self._company_path(company)

        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data is None:
                        data = {"company_name": company}
                    memory = CompanyMemory.from_dict(data)
            except yaml.YAMLError as e:
                raise MemoryError(
                    message=f"Invalid YAML in memory file: {e}",
                    operation="load",
                    company=company,
                    file_path=str(path),
                    cause=e,
                ) from e
            except (KeyError, ValueError, TypeError) as e:
                raise MemoryError(
                    message=f"Invalid memory data structure: {e}",
                    operation="load",
                    company=company,
                    file_path=str(path),
                    cause=e,
                ) from e
        else:
            memory = CompanyMemory(company_name=company)

        self._cache[cache_key] = memory
        return memory

    def _save_company(self, memory: CompanyMemory) -> None:
        """
        Save company memory to disk.

        Args:
            memory: CompanyMemory to save

        Raises:
            MemoryError: If file cannot be written
        """
        path = self._company_path(memory.company_name)

        try:
            data = memory.to_dict()
            # Atomic write: write to temp file then rename, preventing corruption on crash
            tmp_path = path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    data,
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                )
            tmp_path.replace(path)
        except OSError as e:
            raise MemoryError(
                message=f"Cannot write memory file: {e}",
                operation="save",
                company=memory.company_name,
                file_path=str(path),
                cause=e,
            ) from e

        # Update cache
        cache_key = self._sanitize_filename(memory.company_name)
        self._cache[cache_key] = memory

    def get_hypotheses(
        self,
        company: str,
        confidence: ConfidenceLevel | None = None,
        topic: str | None = None,
        include_expired: bool = False,
    ) -> list[Hypothesis]:
        """
        Get hypotheses for a company with optional filtering.

        Args:
            company: Company name
            confidence: Filter by confidence level
            topic: Filter by topic (case-insensitive substring match)
            include_expired: Include expired hypotheses

        Returns:
            List of matching hypotheses
        """
        memory = self._load_company(company)
        hypotheses = list(memory.hypotheses)

        # Filter expired
        if not include_expired:
            hypotheses = [h for h in hypotheses if not h.is_expired()]

        # Filter by confidence
        if confidence is not None:
            hypotheses = [h for h in hypotheses if h.confidence == confidence]

        # Filter by topic
        if topic is not None:
            topic_lower = topic.lower()
            hypotheses = [h for h in hypotheses if topic_lower in h.topic.lower()]

        return hypotheses

    def save_hypotheses(
        self,
        company: str,
        hypotheses: list[Hypothesis],
    ) -> None:
        """
        Save hypotheses for a company with merge logic.

        Existing hypotheses with matching IDs are updated; new hypotheses
        are appended. This enables incremental updates without losing
        prior state.

        Args:
            company: Company name
            hypotheses: List of hypotheses to save
        """
        memory = self._load_company(company)

        # Build index of existing hypotheses
        existing_by_id = {h.id: i for i, h in enumerate(memory.hypotheses)}

        for h in hypotheses:
            if h.id in existing_by_id:
                # Update existing hypothesis
                idx = existing_by_id[h.id]
                memory.hypotheses[idx] = h
            else:
                # Add new hypothesis
                memory.hypotheses.append(h)
                existing_by_id[h.id] = len(memory.hypotheses) - 1

        memory.last_researched = datetime.now(timezone.utc)
        self._save_company(memory)

    def update_hypothesis(
        self,
        company: str,
        hypothesis_id: str,
        confidence: ConfidenceLevel,
        evidence: str,
    ) -> bool:
        """
        Update a specific hypothesis with new confidence and evidence.

        Args:
            company: Company name
            hypothesis_id: ID of the hypothesis to update
            confidence: New confidence level
            evidence: Evidence supporting the confidence change

        Returns:
            True if hypothesis was found and updated, False otherwise
        """
        memory = self._load_company(company)

        for h in memory.hypotheses:
            if h.id == hypothesis_id:
                if confidence == ConfidenceLevel.VALIDATED:
                    h.validate(evidence)
                elif confidence == ConfidenceLevel.INVALIDATED:
                    h.invalidate(evidence)
                elif confidence == ConfidenceLevel.CONFIRMED:
                    h.confirm(evidence)
                else:
                    # For UNTESTED, just update the confidence
                    h.confidence = confidence
                    h.updated_at = datetime.now(timezone.utc)

                self._save_company(memory)
                return True

        return False

    def add_research_note(self, company: str, note: str) -> None:
        """
        Add a research note for a company.

        Args:
            company: Company name
            note: Note to add
        """
        memory = self._load_company(company)
        memory.research_notes.append(note)
        self._save_company(memory)

    def get_scrape_patterns(
        self,
        company: str,
        company_type: str | None = None,
        industry: str | None = None,
    ) -> list[ScrapePattern]:
        """
        Get scraping patterns for a company.

        Args:
            company: Company name
            company_type: Filter by company type
            industry: Filter by industry

        Returns:
            List of matching scrape patterns
        """
        memory = self._load_company(company)
        patterns = list(memory.scrape_patterns)

        if company_type is not None:
            patterns = [p for p in patterns if p.company_type == company_type]

        if industry is not None:
            patterns = [p for p in patterns if p.industry == industry]

        return patterns

    def save_scrape_pattern(self, company: str, pattern: ScrapePattern) -> None:
        """
        Save a scraping pattern for a company.

        Args:
            company: Company name
            pattern: Pattern to save
        """
        memory = self._load_company(company)

        # Update existing or append
        existing_idx = None
        for i, p in enumerate(memory.scrape_patterns):
            if p.pattern_id == pattern.pattern_id:
                existing_idx = i
                break

        if existing_idx is not None:
            memory.scrape_patterns[existing_idx] = pattern
        else:
            memory.scrape_patterns.append(pattern)

        self._save_company(memory)

    def to_json(self, company: str) -> str:
        """
        Serialize company memory to JSON for MCP resource.

        Args:
            company: Company name

        Returns:
            JSON string representation
        """
        memory = self._load_company(company)

        # Filter expired hypotheses for JSON output
        active_hypotheses = [h.to_dict() for h in memory.hypotheses if not h.is_expired()]

        return json.dumps(
            {
                "company_name": memory.company_name,
                "hypotheses": active_hypotheses,
                "scrape_patterns": [p.to_dict() for p in memory.scrape_patterns],
                "research_notes": memory.research_notes,
                "last_researched": (
                    memory.last_researched.isoformat() if memory.last_researched else None
                ),
            },
            indent=2,
        )

    def clear_cache(self) -> None:
        """Clear the in-memory cache."""
        self._cache.clear()

    def delete_company(self, company: str) -> bool:
        """
        Delete all memory for a company.

        Args:
            company: Company name

        Returns:
            True if memory was deleted, False if it didn't exist
        """
        path = self._company_path(company)
        cache_key = self._sanitize_filename(company)

        # Remove from cache
        self._cache.pop(cache_key, None)

        # Remove file
        if path.exists():
            path.unlink()
            return True

        return False

    def list_companies(self) -> list[str]:
        """
        List all companies with research memory.

        Returns:
            List of company names with stored memory
        """
        companies = []
        for path in self._storage_path.glob("*.yaml"):
            try:
                with open(path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data and "company_name" in data:
                        companies.append(data["company_name"])
            except (yaml.YAMLError, OSError):
                # Skip invalid files
                continue
        return companies
