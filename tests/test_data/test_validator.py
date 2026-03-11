"""
Tests for the cross-reference validation module.
"""

from datetime import datetime, timedelta

import pytest

from primr.data.validator import (
    ConfidenceLevel,
    Fact,
    FactType,
    FactValidator,
    SourceInfo,
    ValidationResult,
    get_all_conflicts,
    get_validated_facts,
    get_validator,
    reset_validator,
    validate_content,
    validate_fact,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton before each test."""
    reset_validator()
    yield
    reset_validator()


@pytest.fixture
def validator():
    """Create a fresh validator."""
    return FactValidator()


@pytest.fixture
def source1():
    """Create a test source."""
    return SourceInfo(
        url="https://example.com/about",
        title="About Us",
    )


@pytest.fixture
def source2():
    """Create another test source."""
    return SourceInfo(
        url="https://bloomberg.com/company",
        title="Company Profile",
    )


@pytest.fixture
def source3():
    """Create a third test source."""
    return SourceInfo(
        url="https://reuters.com/company",
        title="Company Info",
    )


# =============================================================================
# SOURCE INFO TESTS
# =============================================================================


class TestSourceInfo:
    """Tests for SourceInfo dataclass."""

    def test_domain_extraction(self):
        """Test domain is extracted from URL."""
        source = SourceInfo(url="https://www.example.com/page")
        assert source.domain == "www.example.com"

    def test_domain_lowercase(self):
        """Test domain is lowercased."""
        source = SourceInfo(url="https://WWW.EXAMPLE.COM/page")
        assert source.domain == "www.example.com"

    def test_scraped_at_default(self):
        """Test scraped_at defaults to now."""
        source = SourceInfo(url="https://example.com")
        assert source.scraped_at is not None
        assert (datetime.now() - source.scraped_at).seconds < 5

    def test_custom_authority_score(self):
        """Test custom authority score."""
        source = SourceInfo(url="https://example.com", authority_score=0.9)
        assert source.authority_score == 0.9


# =============================================================================
# FACT TESTS
# =============================================================================


class TestFact:
    """Tests for Fact dataclass."""

    def test_normalization_lowercase(self):
        """Test value is lowercased."""
        fact = Fact(FactType.COMPANY_NAME, "ACME Corporation")
        assert "acme" in fact.normalized_value

    def test_normalization_strips_whitespace(self):
        """Test whitespace is stripped."""
        fact = Fact(FactType.COMPANY_NAME, "  Acme Corp  ")
        assert fact.normalized_value == "acme"

    def test_normalization_removes_suffixes(self):
        """Test company suffixes are removed."""
        fact = Fact(FactType.COMPANY_NAME, "Acme Inc.")
        assert fact.normalized_value == "acme"

        fact2 = Fact(FactType.COMPANY_NAME, "Beta LLC")
        assert fact2.normalized_value == "beta"

    def test_source_count(self):
        """Test source count property."""
        source1 = SourceInfo(url="https://a.com")
        source2 = SourceInfo(url="https://b.com")
        fact = Fact(FactType.CEO, "John Smith", sources=[source1, source2])
        assert fact.source_count == 2

    def test_unique_domains(self):
        """Test unique domains property."""
        source1 = SourceInfo(url="https://a.com/page1")
        source2 = SourceInfo(url="https://a.com/page2")
        source3 = SourceInfo(url="https://b.com")
        fact = Fact(FactType.CEO, "John Smith", sources=[source1, source2, source3])
        assert fact.unique_domains == {"a.com", "b.com"}

    def test_avg_authority(self):
        """Test average authority calculation."""
        source1 = SourceInfo(url="https://a.com", authority_score=0.8)
        source2 = SourceInfo(url="https://b.com", authority_score=0.6)
        fact = Fact(FactType.CEO, "John Smith", sources=[source1, source2])
        assert fact.avg_authority == 0.7

    def test_avg_authority_empty(self):
        """Test average authority with no sources."""
        fact = Fact(FactType.CEO, "John Smith")
        assert fact.avg_authority == 0.0


# =============================================================================
# FACT VALIDATOR TESTS
# =============================================================================


class TestFactValidator:
    """Tests for FactValidator class."""

    def test_add_fact(self, validator, source1):
        """Test adding a fact."""
        fact = validator.add_fact(FactType.CEO, "John Smith", source1)
        assert fact.value == "John Smith"
        assert fact.source_count == 1

    def test_add_similar_fact_merges(self, validator, source1, source2):
        """Test similar facts are merged."""
        validator.add_fact(FactType.CEO, "John Smith", source1)
        fact = validator.add_fact(FactType.CEO, "john smith", source2)

        # Should be same fact with 2 sources
        assert fact.source_count == 2
        facts = validator.get_facts(FactType.CEO)
        assert len(facts) == 1

    def test_add_different_fact_creates_new(self, validator, source1, source2):
        """Test different facts create separate entries."""
        validator.add_fact(FactType.CEO, "John Smith", source1)
        validator.add_fact(FactType.CEO, "Jane Doe", source2)

        facts = validator.get_facts(FactType.CEO)
        assert len(facts) == 2

    def test_authority_score_from_known_domain(self, validator):
        """Test authority score is set for known domains."""
        source = SourceInfo(url="https://bloomberg.com/company")
        validator.add_fact(FactType.CEO, "John Smith", source)

        facts = validator.get_facts(FactType.CEO)
        assert facts[0].sources[0].authority_score == 0.90

    def test_get_facts_all(self, validator, source1):
        """Test getting all facts."""
        validator.add_fact(FactType.CEO, "John Smith", source1)
        validator.add_fact(FactType.HEADQUARTERS, "New York", source1)

        all_facts = validator.get_facts()
        assert len(all_facts) == 2

    def test_get_facts_by_type(self, validator, source1):
        """Test getting facts by type."""
        validator.add_fact(FactType.CEO, "John Smith", source1)
        validator.add_fact(FactType.HEADQUARTERS, "New York", source1)

        ceo_facts = validator.get_facts(FactType.CEO)
        assert len(ceo_facts) == 1
        assert ceo_facts[0].value == "John Smith"

    def test_clear(self, validator, source1):
        """Test clearing all facts."""
        validator.add_fact(FactType.CEO, "John Smith", source1)
        validator.clear()

        assert len(validator.get_facts()) == 0


# =============================================================================
# VALIDATION TESTS
# =============================================================================


class TestValidation:
    """Tests for fact validation."""

    def test_single_source_low_confidence(self, validator, source1):
        """Test single source gives low confidence."""
        fact = validator.add_fact(FactType.CEO, "John Smith", source1)
        result = validator.validate_fact(fact)

        assert result.confidence in (ConfidenceLevel.LOW, ConfidenceLevel.VERY_LOW)
        assert result.confidence_score < 50

    def test_multiple_sources_higher_confidence(self, validator, source1, source2, source3):
        """Test multiple sources increase confidence."""
        validator.add_fact(FactType.CEO, "John Smith", source1)
        validator.add_fact(FactType.CEO, "John Smith", source2)
        fact = validator.add_fact(FactType.CEO, "John Smith", source3)

        result = validator.validate_fact(fact)
        assert result.confidence_score >= 50

    def test_authoritative_source_bonus(self, validator):
        """Test authoritative sources increase confidence."""
        source = SourceInfo(url="https://sec.gov/filing")
        fact = validator.add_fact(FactType.REVENUE, "$1B", source)

        result = validator.validate_fact(fact)
        # Should have authority bonus
        assert result.confidence_score > 20

    def test_conflict_detection(self, validator, source1, source2):
        """Test conflicts are detected."""
        validator.add_fact(FactType.CEO, "John Smith", source1)
        fact2 = validator.add_fact(FactType.CEO, "Jane Doe", source2)

        result = validator.validate_fact(fact2)
        assert not result.is_consistent
        assert len(result.conflicts) == 1

    def test_conflict_reduces_confidence(self, validator, source1, source2):
        """Test conflicts reduce confidence."""
        fact1 = validator.add_fact(FactType.CEO, "John Smith", source1)
        validator.add_fact(FactType.CEO, "Jane Doe", source2)

        result = validator.validate_fact(fact1)
        # Confidence should be reduced due to conflict
        assert result.confidence_score < 40

    def test_freshness_tracking(self, validator):
        """Test freshness is tracked."""
        old_date = datetime.now() - timedelta(days=400)
        source = SourceInfo(url="https://example.com", scraped_at=old_date)
        fact = validator.add_fact(FactType.CEO, "John Smith", source)

        result = validator.validate_fact(fact)
        assert result.freshness_days >= 400
        assert any("days old" in note for note in result.notes)

    def test_validate_all(self, validator, source1, source2):
        """Test validating all facts."""
        validator.add_fact(FactType.CEO, "John Smith", source1)
        validator.add_fact(FactType.HEADQUARTERS, "New York", source2)

        results = validator.validate_all()
        assert len(results) == 2


# =============================================================================
# BEST VALUE TESTS
# =============================================================================


class TestBestValue:
    """Tests for getting best values."""

    def test_get_best_value_single(self, validator, source1):
        """Test getting best value with single fact."""
        validator.add_fact(FactType.CEO, "John Smith", source1)

        result = validator.get_best_value(FactType.CEO)
        assert result is not None
        assert result[0] == "John Smith"

    def test_get_best_value_multiple(self, validator, source1, source2, source3):
        """Test getting best value with multiple facts."""
        # Add fact with more sources
        validator.add_fact(FactType.CEO, "John Smith", source1)
        validator.add_fact(FactType.CEO, "John Smith", source2)
        validator.add_fact(FactType.CEO, "John Smith", source3)

        # Add conflicting fact with fewer sources
        validator.add_fact(FactType.CEO, "Jane Doe", SourceInfo(url="https://random.com"))

        result = validator.get_best_value(FactType.CEO)
        assert result is not None
        assert result[0] == "John Smith"

    def test_get_best_value_none(self, validator):
        """Test getting best value when none exist."""
        result = validator.get_best_value(FactType.CEO)
        assert result is None


# =============================================================================
# CONFLICT TESTS
# =============================================================================


class TestConflicts:
    """Tests for conflict detection."""

    def test_get_conflicts_none(self, validator, source1):
        """Test no conflicts when facts agree."""
        validator.add_fact(FactType.CEO, "John Smith", source1)

        conflicts = validator.get_conflicts()
        assert len(conflicts) == 0

    def test_get_conflicts_found(self, validator, source1, source2):
        """Test conflicts are found."""
        validator.add_fact(FactType.CEO, "John Smith", source1)
        validator.add_fact(FactType.CEO, "Jane Doe", source2)

        conflicts = validator.get_conflicts()
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == "value_mismatch"

    def test_conflict_severity_major(self, validator, source1, source2):
        """Test major severity for important facts."""
        validator.add_fact(FactType.CEO, "John Smith", source1)
        validator.add_fact(FactType.CEO, "Jane Doe", source2)

        conflicts = validator.get_conflicts()
        assert conflicts[0].severity == "major"

    def test_conflict_description(self, validator, source1, source2):
        """Test conflict description."""
        validator.add_fact(FactType.CEO, "John Smith", source1)
        validator.add_fact(FactType.CEO, "Jane Doe", source2)

        conflicts = validator.get_conflicts()
        assert "John Smith" in conflicts[0].description
        assert "Jane Doe" in conflicts[0].description


# =============================================================================
# CONTENT EXTRACTION TESTS
# =============================================================================


class TestContentExtraction:
    """Tests for extracting facts from content."""

    def test_extract_ceo(self, validator, source1):
        """Test CEO extraction."""
        content = "The company is led by CEO John Smith who joined in 2020."
        facts = validator.add_facts_from_content(content, source1)

        ceo_facts = [f for f in facts if f.fact_type == FactType.CEO]
        assert len(ceo_facts) == 1
        assert "John Smith" in ceo_facts[0].value

    def test_extract_founding_date(self, validator, source1):
        """Test founding date extraction."""
        content = "Acme Corp was founded in 1995 by entrepreneurs."
        facts = validator.add_facts_from_content(content, source1)

        date_facts = [f for f in facts if f.fact_type == FactType.FOUNDING_DATE]
        assert len(date_facts) == 1
        assert date_facts[0].value == "1995"

    def test_extract_employee_count(self, validator, source1):
        """Test employee count extraction."""
        content = "The company has 5,000 employees worldwide."
        facts = validator.add_facts_from_content(content, source1)

        emp_facts = [f for f in facts if f.fact_type == FactType.EMPLOYEE_COUNT]
        assert len(emp_facts) == 1
        assert "5,000" in emp_facts[0].value

    def test_extract_headquarters(self, validator, source1):
        """Test headquarters extraction."""
        content = "Acme Corp is headquartered in San Francisco, CA."
        facts = validator.add_facts_from_content(content, source1)

        hq_facts = [f for f in facts if f.fact_type == FactType.HEADQUARTERS]
        assert len(hq_facts) == 1
        assert "San Francisco" in hq_facts[0].value

    def test_extract_revenue(self, validator, source1):
        """Test revenue extraction."""
        content = "The company reported $2.5B in revenue last year."
        facts = validator.add_facts_from_content(content, source1)

        rev_facts = [f for f in facts if f.fact_type == FactType.REVENUE]
        assert len(rev_facts) == 1
        assert "$2.5B" in rev_facts[0].value

    def test_extract_multiple(self, validator, source1):
        """Test extracting multiple facts."""
        content = """
        Acme Corp was founded in 2010 and is headquartered in Boston, MA.
        CEO Jane Doe leads a team of 1,500 employees.
        """
        facts = validator.add_facts_from_content(content, source1)

        assert len(facts) >= 3


# =============================================================================
# SINGLETON TESTS
# =============================================================================


class TestSingleton:
    """Tests for singleton access."""

    def test_get_validator_returns_same(self):
        """Test get_validator returns same instance."""
        v1 = get_validator()
        v2 = get_validator()
        assert v1 is v2

    def test_reset_validator(self):
        """Test reset creates new instance."""
        v1 = get_validator()
        reset_validator()
        v2 = get_validator()
        assert v1 is not v2


# =============================================================================
# CONVENIENCE FUNCTION TESTS
# =============================================================================


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_validate_fact_function(self):
        """Test validate_fact convenience function."""
        result = validate_fact(
            FactType.CEO,
            "John Smith",
            "https://example.com/about",
        )
        assert isinstance(result, ValidationResult)
        assert result.fact.value == "John Smith"

    def test_validate_content_function(self):
        """Test validate_content convenience function."""
        content = "Founded in 2015, the company has 500 employees."
        results = validate_content(content, "https://example.com")

        assert len(results) >= 1

    def test_get_validated_facts_function(self):
        """Test get_validated_facts convenience function."""
        validate_fact(FactType.CEO, "John Smith", "https://a.com")
        validate_fact(FactType.HEADQUARTERS, "New York", "https://b.com")

        facts = get_validated_facts()
        assert "ceo" in facts
        assert "headquarters" in facts

    def test_get_all_conflicts_function(self):
        """Test get_all_conflicts convenience function."""
        validate_fact(FactType.CEO, "John Smith", "https://a.com")
        validate_fact(FactType.CEO, "Jane Doe", "https://b.com")

        conflicts = get_all_conflicts()
        assert len(conflicts) == 1


# =============================================================================
# CONFIDENCE LEVEL TESTS
# =============================================================================


class TestConfidenceLevels:
    """Tests for confidence level determination."""

    def test_very_high_confidence(self, validator):
        """Test very high confidence with many authoritative sources."""
        for i in range(5):
            source = SourceInfo(url=f"https://bloomberg.com/page{i}", authority_score=0.9)
            validator.add_fact(FactType.CEO, "John Smith", source)

        facts = validator.get_facts(FactType.CEO)
        result = validator.validate_fact(facts[0])
        assert result.confidence == ConfidenceLevel.VERY_HIGH

    def test_very_low_confidence(self, validator):
        """Test very low confidence with single low-authority source."""
        source = SourceInfo(url="https://random-blog.com", authority_score=0.1)
        fact = validator.add_fact(FactType.CEO, "John Smith", source)

        result = validator.validate_fact(fact)
        assert result.confidence in (ConfidenceLevel.LOW, ConfidenceLevel.VERY_LOW)
