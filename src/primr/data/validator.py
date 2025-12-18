"""
Cross-reference validation for company research data.

This module provides:
- Fact validation across multiple sources
- Confidence scoring for claims
- Inconsistency detection and flagging
- Information freshness tracking
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from urllib.parse import urlparse

from primr.utils.logging_config import get_logger

logger = get_logger("data.validator")


class ConfidenceLevel(Enum):
    """Confidence levels for validated facts."""

    VERY_HIGH = "very_high"  # 90%+ - Multiple authoritative sources agree
    HIGH = "high"            # 75-89% - Multiple sources agree
    MEDIUM = "medium"        # 50-74% - Some corroboration
    LOW = "low"              # 25-49% - Single source or conflicts
    VERY_LOW = "very_low"    # <25% - Unverified or contradicted


class FactType(Enum):
    """Types of facts that can be validated."""

    COMPANY_NAME = "company_name"
    FOUNDING_DATE = "founding_date"
    HEADQUARTERS = "headquarters"
    EMPLOYEE_COUNT = "employee_count"
    REVENUE = "revenue"
    CEO = "ceo"
    INDUSTRY = "industry"
    STOCK_TICKER = "stock_ticker"
    WEBSITE = "website"
    PHONE = "phone"
    ADDRESS = "address"
    PRODUCT = "product"
    ACQUISITION = "acquisition"
    PARTNERSHIP = "partnership"
    CUSTOM = "custom"


@dataclass
class SourceInfo:
    """Information about a data source."""

    url: str
    domain: str = ""
    title: str = ""
    scraped_at: datetime | None = None
    authority_score: float = 0.5  # 0-1, higher = more authoritative

    def __post_init__(self):
        if not self.domain:
            parsed = urlparse(self.url)
            self.domain = parsed.netloc.lower()
        if self.scraped_at is None:
            self.scraped_at = datetime.now()


@dataclass
class Fact:
    """A single fact extracted from sources."""

    fact_type: FactType
    value: str
    normalized_value: str = ""
    sources: list[SourceInfo] = field(default_factory=list)
    extracted_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        if not self.normalized_value:
            self.normalized_value = self._normalize(self.value)

    def _normalize(self, value: str) -> str:
        """Normalize value for comparison."""
        # Lowercase, strip whitespace, remove extra spaces
        normalized = value.lower().strip()
        normalized = re.sub(r'\s+', ' ', normalized)
        # Remove common suffixes for company names
        normalized = re.sub(r'\s*(inc\.?|llc\.?|ltd\.?|corp\.?|co\.?)$', '', normalized, flags=re.I)
        return normalized

    @property
    def source_count(self) -> int:
        """Number of sources for this fact."""
        return len(self.sources)

    @property
    def unique_domains(self) -> set[str]:
        """Unique domains that reported this fact."""
        return {s.domain for s in self.sources}

    @property
    def avg_authority(self) -> float:
        """Average authority score of sources."""
        if not self.sources:
            return 0.0
        return sum(s.authority_score for s in self.sources) / len(self.sources)


@dataclass
class ValidationResult:
    """Result of validating a fact."""

    fact: Fact
    confidence: ConfidenceLevel
    confidence_score: float  # 0-100
    is_consistent: bool
    conflicts: list["FactConflict"] = field(default_factory=list)
    freshness_days: int = 0
    notes: list[str] = field(default_factory=list)


@dataclass
class FactConflict:
    """A conflict between two facts."""

    fact1: Fact
    fact2: Fact
    conflict_type: str  # "value_mismatch", "date_conflict", etc.
    severity: str  # "minor", "major", "critical"
    description: str = ""


class FactValidator:
    """
    Validates facts by cross-referencing multiple sources.

    Example:
        validator = FactValidator()

        # Add facts from different sources
        validator.add_fact(FactType.CEO, "John Smith", source1)
        validator.add_fact(FactType.CEO, "John D. Smith", source2)
        validator.add_fact(FactType.CEO, "Jane Doe", source3)

        # Validate
        results = validator.validate_all()
        for result in results:
            print(f"{result.fact.fact_type}: {result.confidence}")
    """

    # Authority scores for known domains
    AUTHORITY_SCORES: dict[str, float] = {
        # Official/Government
        "sec.gov": 0.95,
        "edgar-online.com": 0.90,
        # Business databases
        "bloomberg.com": 0.90,
        "reuters.com": 0.90,
        "crunchbase.com": 0.85,
        "linkedin.com": 0.80,
        "dnb.com": 0.85,
        "zoominfo.com": 0.80,
        # News
        "wsj.com": 0.85,
        "ft.com": 0.85,
        "nytimes.com": 0.80,
        "forbes.com": 0.75,
        # General
        "wikipedia.org": 0.70,
        "glassdoor.com": 0.65,
    }

    def __init__(self, similarity_threshold: float = 0.85):
        """
        Initialize the validator.

        Args:
            similarity_threshold: Threshold for considering values similar (0-1)
        """
        self._facts: dict[FactType, list[Fact]] = {}
        self._similarity_threshold = similarity_threshold
        logger.debug("FactValidator initialized")

    def add_fact(
        self,
        fact_type: FactType,
        value: str,
        source: SourceInfo,
    ) -> Fact:
        """
        Add a fact from a source.

        Args:
            fact_type: Type of fact
            value: The fact value
            source: Source information

        Returns:
            The created or updated Fact
        """
        # Set authority score if known domain
        if source.domain in self.AUTHORITY_SCORES:
            source.authority_score = self.AUTHORITY_SCORES[source.domain]

        # Check if we have a similar fact already
        if fact_type not in self._facts:
            self._facts[fact_type] = []

        normalized = Fact(fact_type, value).normalized_value

        for existing in self._facts[fact_type]:
            if self._are_similar(existing.normalized_value, normalized):
                # Add source to existing fact
                existing.sources.append(source)
                logger.debug(f"Added source to existing fact: {fact_type.value}={value}")
                return existing

        # Create new fact
        fact = Fact(fact_type=fact_type, value=value, sources=[source])
        self._facts[fact_type].append(fact)
        logger.debug(f"Added new fact: {fact_type.value}={value}")
        return fact

    def add_facts_from_content(
        self,
        content: str,
        source: SourceInfo,
        company_name: str = "",
    ) -> list[Fact]:
        """
        Extract and add facts from content.

        Args:
            content: Text content to extract from
            source: Source information
            company_name: Company name for context

        Returns:
            List of extracted facts
        """
        facts = []

        # Extract CEO/leadership
        ceo_patterns = [
            r'(?:CEO|Chief Executive Officer)[:\s]+([A-Z][a-z]+ [A-Z][a-z]+)',
            r'([A-Z][a-z]+ [A-Z][a-z]+)(?:\s+is|\s+serves as)?\s+(?:the\s+)?CEO',
        ]
        for pattern in ceo_patterns:
            match = re.search(pattern, content)
            if match:
                facts.append(self.add_fact(FactType.CEO, match.group(1), source))
                break

        # Extract founding date
        founding_patterns = [
            r'[Ff]ounded\s+(?:in\s+)?(\d{4})',
            r'[Ee]stablished\s+(?:in\s+)?(\d{4})',
            r'[Ss]ince\s+(\d{4})',
        ]
        for pattern in founding_patterns:
            match = re.search(pattern, content)
            if match:
                facts.append(self.add_fact(FactType.FOUNDING_DATE, match.group(1), source))
                break

        # Extract employee count
        employee_patterns = [
            r'(\d{1,3}(?:,\d{3})*)\s+employees',
            r'(?:employs?|workforce of)\s+(\d{1,3}(?:,\d{3})*)',
            r'(\d+(?:\.\d+)?[KkMm]?)\s+employees',
        ]
        for pattern in employee_patterns:
            match = re.search(pattern, content)
            if match:
                facts.append(self.add_fact(FactType.EMPLOYEE_COUNT, match.group(1), source))
                break

        # Extract headquarters
        hq_patterns = [
            r'[Hh]eadquartered\s+in\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,\s*[A-Z]{2})',
            r'[Hh]eadquarters?\s+(?:in|:)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'[Bb]ased\s+in\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,\s*[A-Z]{2})',
        ]
        for pattern in hq_patterns:
            match = re.search(pattern, content)
            if match:
                facts.append(self.add_fact(FactType.HEADQUARTERS, match.group(1), source))
                break

        # Extract revenue
        revenue_patterns = [
            r'\$(\d+(?:\.\d+)?)\s*([BMKbmk](?:illion)?)\s+(?:in\s+)?revenue',
            r'revenue\s+(?:of\s+)?\$(\d+(?:\.\d+)?)\s*([BMKbmk](?:illion)?)',
        ]
        for pattern in revenue_patterns:
            match = re.search(pattern, content)
            if match:
                value = f"${match.group(1)}{match.group(2)}"
                facts.append(self.add_fact(FactType.REVENUE, value, source))
                break

        return facts

    def validate_fact(self, fact: Fact) -> ValidationResult:
        """
        Validate a single fact.

        Args:
            fact: The fact to validate

        Returns:
            ValidationResult with confidence and conflicts
        """
        # Calculate confidence based on sources
        source_count = fact.source_count
        unique_domains = len(fact.unique_domains)
        avg_authority = fact.avg_authority

        # Base score from source count
        if source_count >= 5:
            base_score = 80
        elif source_count >= 3:
            base_score = 60
        elif source_count >= 2:
            base_score = 40
        else:
            base_score = 20

        # Bonus for unique domains
        domain_bonus = min(unique_domains * 5, 15)

        # Authority bonus
        authority_bonus = avg_authority * 10

        # Calculate final score
        confidence_score = min(base_score + domain_bonus + authority_bonus, 100)

        # Determine confidence level
        if confidence_score >= 90:
            confidence = ConfidenceLevel.VERY_HIGH
        elif confidence_score >= 75:
            confidence = ConfidenceLevel.HIGH
        elif confidence_score >= 50:
            confidence = ConfidenceLevel.MEDIUM
        elif confidence_score >= 25:
            confidence = ConfidenceLevel.LOW
        else:
            confidence = ConfidenceLevel.VERY_LOW

        # Check for conflicts with other facts of same type
        conflicts = self._find_conflicts(fact)
        is_consistent = len(conflicts) == 0

        # Adjust confidence if conflicts exist
        if conflicts:
            # Reduce confidence based on conflict severity
            for conflict in conflicts:
                if conflict.severity == "critical":
                    confidence_score *= 0.5
                elif conflict.severity == "major":
                    confidence_score *= 0.7
                else:
                    confidence_score *= 0.9

        # Calculate freshness
        freshness_days = 0
        if fact.sources:
            oldest = min(s.scraped_at for s in fact.sources if s.scraped_at)
            freshness_days = (datetime.now() - oldest).days

        notes = []
        if source_count == 1:
            notes.append("Single source - consider verification")
        if freshness_days > 365:
            notes.append(f"Data is {freshness_days} days old")
        if conflicts:
            notes.append(f"{len(conflicts)} conflicting value(s) found")

        return ValidationResult(
            fact=fact,
            confidence=confidence,
            confidence_score=confidence_score,
            is_consistent=is_consistent,
            conflicts=conflicts,
            freshness_days=freshness_days,
            notes=notes,
        )

    def validate_all(self) -> list[ValidationResult]:
        """
        Validate all facts.

        Returns:
            List of ValidationResult for each fact
        """
        results = []
        for _fact_type, facts in self._facts.items():
            for fact in facts:
                results.append(self.validate_fact(fact))
        return results

    def get_facts(self, fact_type: FactType | None = None) -> list[Fact]:
        """
        Get facts, optionally filtered by type.

        Args:
            fact_type: Optional type filter

        Returns:
            List of facts
        """
        if fact_type:
            return self._facts.get(fact_type, [])

        all_facts = []
        for facts in self._facts.values():
            all_facts.extend(facts)
        return all_facts

    def get_best_value(self, fact_type: FactType) -> tuple[str, float] | None:
        """
        Get the most confident value for a fact type.

        Args:
            fact_type: Type of fact

        Returns:
            Tuple of (value, confidence_score) or None
        """
        facts = self._facts.get(fact_type, [])
        if not facts:
            return None

        best_fact = None
        best_score = 0.0

        for fact in facts:
            result = self.validate_fact(fact)
            if result.confidence_score > best_score:
                best_score = result.confidence_score
                best_fact = fact

        if best_fact:
            return (best_fact.value, best_score)
        return None

    def get_conflicts(self) -> list[FactConflict]:
        """
        Get all conflicts across all facts.

        Returns:
            List of all conflicts
        """
        conflicts = []
        for _fact_type, facts in self._facts.items():
            if len(facts) > 1:
                for i, fact1 in enumerate(facts):
                    for fact2 in facts[i+1:]:
                        if not self._are_similar(fact1.normalized_value, fact2.normalized_value):
                            conflicts.append(self._create_conflict(fact1, fact2))
        return conflicts

    def clear(self) -> None:
        """Clear all facts."""
        self._facts.clear()

    def _are_similar(self, value1: str, value2: str) -> bool:
        """Check if two values are similar enough to be the same fact."""
        if value1 == value2:
            return True

        # Check if one contains the other
        if value1 in value2 or value2 in value1:
            return True

        # Calculate similarity ratio
        similarity = self._calculate_similarity(value1, value2)
        return similarity >= self._similarity_threshold

    def _calculate_similarity(self, s1: str, s2: str) -> float:
        """Calculate similarity between two strings (0-1)."""
        if not s1 or not s2:
            return 0.0

        # Simple Jaccard similarity on words
        words1 = set(s1.split())
        words2 = set(s2.split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def _find_conflicts(self, fact: Fact) -> list[FactConflict]:
        """Find conflicts for a fact."""
        conflicts = []
        other_facts = self._facts.get(fact.fact_type, [])

        for other in other_facts:
            if other is fact:
                continue
            if not self._are_similar(fact.normalized_value, other.normalized_value):
                conflicts.append(self._create_conflict(fact, other))

        return conflicts

    def _create_conflict(self, fact1: Fact, fact2: Fact) -> FactConflict:
        """Create a conflict between two facts."""
        # Determine severity based on fact type and difference
        if fact1.fact_type in (FactType.CEO, FactType.REVENUE, FactType.EMPLOYEE_COUNT):
            severity = "major"
        elif fact1.fact_type in (FactType.FOUNDING_DATE, FactType.HEADQUARTERS):
            severity = "major"
        else:
            severity = "minor"

        return FactConflict(
            fact1=fact1,
            fact2=fact2,
            conflict_type="value_mismatch",
            severity=severity,
            description=f"'{fact1.value}' vs '{fact2.value}'",
        )



# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_validator: FactValidator | None = None


def get_validator() -> FactValidator:
    """
    Get the global validator instance.

    Returns:
        FactValidator instance
    """
    global _validator
    if _validator is None:
        _validator = FactValidator()
    return _validator


def reset_validator() -> None:
    """Reset the global validator (useful for testing)."""
    global _validator
    _validator = None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def validate_fact(
    fact_type: FactType,
    value: str,
    source_url: str,
    source_title: str = "",
) -> ValidationResult:
    """
    Add and validate a single fact.

    Args:
        fact_type: Type of fact
        value: The fact value
        source_url: URL of the source
        source_title: Optional title of the source

    Returns:
        ValidationResult for the fact
    """
    validator = get_validator()
    source = SourceInfo(url=source_url, title=source_title)
    fact = validator.add_fact(fact_type, value, source)
    return validator.validate_fact(fact)


def validate_content(
    content: str,
    source_url: str,
    company_name: str = "",
) -> list[ValidationResult]:
    """
    Extract and validate facts from content.

    Args:
        content: Text content to extract from
        source_url: URL of the source
        company_name: Company name for context

    Returns:
        List of ValidationResult for extracted facts
    """
    validator = get_validator()
    source = SourceInfo(url=source_url)
    facts = validator.add_facts_from_content(content, source, company_name)
    return [validator.validate_fact(f) for f in facts]


def get_validated_facts() -> dict[str, tuple[str, float]]:
    """
    Get all validated facts with their best values.

    Returns:
        Dict mapping fact type name to (value, confidence_score)
    """
    validator = get_validator()
    result = {}

    for fact_type in FactType:
        best = validator.get_best_value(fact_type)
        if best:
            result[fact_type.value] = best

    return result


def get_all_conflicts() -> list[FactConflict]:
    """
    Get all conflicts across all facts.

    Returns:
        List of all conflicts
    """
    return get_validator().get_conflicts()
