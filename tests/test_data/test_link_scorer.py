"""
Tests for the link scorer module.

Tests link scoring, categorization, and filtering.
"""

from primr.data.link_scorer import (
    HIGH_VALUE_PATTERNS,
    LOW_VALUE_PATTERNS,
    LinkInfo,
    LinkScorer,
    ScoredLink,
    get_best_links,
    get_link_scorer,
    reset_link_scorer,
    score_links,
)

# =============================================================================
# SCORED LINK TESTS
# =============================================================================

class TestScoredLink:
    """Tests for ScoredLink dataclass."""

    def test_creation(self):
        """Test creating a scored link."""
        link = ScoredLink(
            url="https://example.com/about",
            text="About Us",
            score=0.9,
            reasons=["High-value pattern"]
        )

        assert link.url == "https://example.com/about"
        assert link.score == 0.9

    def test_sorting(self):
        """Test that scored links sort by score descending."""
        links = [
            ScoredLink(url="low", text="", score=0.3),
            ScoredLink(url="high", text="", score=0.9),
            ScoredLink(url="mid", text="", score=0.6),
        ]

        sorted_links = sorted(links)

        assert sorted_links[0].url == "high"
        assert sorted_links[1].url == "mid"
        assert sorted_links[2].url == "low"


# =============================================================================
# LINK SCORER TESTS
# =============================================================================

class TestLinkScorer:
    """Tests for LinkScorer class."""

    def test_initialization(self):
        """Test scorer initialization."""
        scorer = LinkScorer()
        assert scorer is not None

    def test_score_about_page(self):
        """Test scoring an about page."""
        scorer = LinkScorer()
        link = LinkInfo(url="https://example.com/about", text="About Us")

        scored = scorer.score_link(link)

        assert scored.score > 0.8
        assert any("High-value" in r for r in scored.reasons)

    def test_score_login_page(self):
        """Test scoring a login page (low value)."""
        scorer = LinkScorer()
        link = LinkInfo(url="https://example.com/login", text="Login")

        scored = scorer.score_link(link)

        assert scored.score < 0.3
        assert any("Low-value" in r for r in scored.reasons)

    def test_score_leadership_page(self):
        """Test scoring a leadership page."""
        scorer = LinkScorer()
        link = LinkInfo(url="https://example.com/leadership", text="Our Team")

        scored = scorer.score_link(link)

        assert scored.score > 0.8

    def test_score_products_page(self):
        """Test scoring a products page."""
        scorer = LinkScorer()
        link = LinkInfo(url="https://example.com/products", text="Products")

        scored = scorer.score_link(link)

        assert scored.score > 0.7

    def test_score_investors_page(self):
        """Test scoring an investors page."""
        scorer = LinkScorer()
        link = LinkInfo(url="https://example.com/investor-relations", text="Investors")

        scored = scorer.score_link(link)

        assert scored.score > 0.8

    def test_skip_pdf_extension(self):
        """Test that PDF files are skipped."""
        scorer = LinkScorer()
        link = LinkInfo(url="https://example.com/report.pdf", text="Annual Report")

        scored = scorer.score_link(link)

        assert scored.score == 0.0
        assert any("Skipped extension" in r for r in scored.reasons)

    def test_skip_image_extension(self):
        """Test that image files are skipped."""
        scorer = LinkScorer()
        link = LinkInfo(url="https://example.com/logo.png", text="Logo")

        scored = scorer.score_link(link)

        assert scored.score == 0.0

    def test_company_name_boost(self):
        """Test boost for company name in link text."""
        scorer = LinkScorer()
        link = LinkInfo(url="https://example.com/page", text="About Acme Corp")

        scored = scorer.score_link(link, company_name="Acme Corp")

        assert any("Company name" in r for r in scored.reasons)

    def test_same_domain_boost(self):
        """Test boost for same domain links."""
        scorer = LinkScorer()
        link = LinkInfo(url="https://example.com/page", text="Page")

        scored = scorer.score_link(link, base_domain="example.com")

        assert any("Same domain" in r for r in scored.reasons)

    def test_long_url_penalty(self):
        """Test penalty for very long URLs."""
        scorer = LinkScorer()
        long_url = "https://example.com/" + "a" * 200
        link = LinkInfo(url=long_url, text="Page")

        scored = scorer.score_link(link)

        assert any("Long URL" in r for r in scored.reasons)

    def test_deep_path_penalty(self):
        """Test penalty for deep paths."""
        scorer = LinkScorer()
        link = LinkInfo(
            url="https://example.com/a/b/c/d/e/f/page",
            text="Deep Page"
        )

        scored = scorer.score_link(link)

        assert any("Deep path" in r for r in scored.reasons)

    def test_score_links_batch(self):
        """Test scoring multiple links."""
        scorer = LinkScorer()
        links = [
            LinkInfo(url="https://example.com/about", text="About"),
            LinkInfo(url="https://example.com/login", text="Login"),
            LinkInfo(url="https://example.com/products", text="Products"),
        ]

        scored = scorer.score_links(links)

        assert len(scored) == 3
        # Should be sorted by score
        assert scored[0].score >= scored[1].score >= scored[2].score

    def test_get_top_links(self):
        """Test getting top links."""
        scorer = LinkScorer()
        links = [
            LinkInfo(url="https://example.com/about", text="About"),
            LinkInfo(url="https://example.com/login", text="Login"),
            LinkInfo(url="https://example.com/products", text="Products"),
            LinkInfo(url="https://example.com/team", text="Team"),
        ]

        scored = scorer.score_links(links)
        top = scorer.get_top_links(scored, limit=2)

        assert len(top) == 2
        assert all(link.score >= 0.3 for link in top)

    def test_get_top_links_min_score(self):
        """Test minimum score filtering."""
        scorer = LinkScorer()
        links = [
            LinkInfo(url="https://example.com/login", text="Login"),
            LinkInfo(url="https://example.com/signup", text="Signup"),
        ]

        scored = scorer.score_links(links)
        top = scorer.get_top_links(scored, min_score=0.5)

        # Both should be filtered out due to low scores
        assert len(top) == 0


# =============================================================================
# DEDUPLICATION TESTS
# =============================================================================

class TestDeduplication:
    """Tests for link deduplication."""

    def test_deduplicate_exact_duplicates(self):
        """Test removing exact duplicate URLs."""
        scorer = LinkScorer()
        links = [
            LinkInfo(url="https://example.com/page", text="Page 1"),
            LinkInfo(url="https://example.com/page", text="Page 2"),
            LinkInfo(url="https://example.com/other", text="Other"),
        ]

        unique = scorer.deduplicate_links(links)

        assert len(unique) == 2

    def test_deduplicate_trailing_slash(self):
        """Test that trailing slashes are normalized."""
        scorer = LinkScorer()
        links = [
            LinkInfo(url="https://example.com/page/", text="Page 1"),
            LinkInfo(url="https://example.com/page", text="Page 2"),
        ]

        unique = scorer.deduplicate_links(links)

        assert len(unique) == 1

    def test_deduplicate_case_insensitive(self):
        """Test case-insensitive deduplication."""
        scorer = LinkScorer()
        links = [
            LinkInfo(url="https://Example.com/Page", text="Page 1"),
            LinkInfo(url="https://example.com/page", text="Page 2"),
        ]

        unique = scorer.deduplicate_links(links)

        assert len(unique) == 1


# =============================================================================
# DOMAIN FILTERING TESTS
# =============================================================================

class TestDomainFiltering:
    """Tests for domain filtering."""

    def test_filter_same_domain(self):
        """Test filtering to same domain."""
        scorer = LinkScorer()
        links = [
            LinkInfo(url="https://example.com/page1", text="Page 1"),
            LinkInfo(url="https://other.com/page2", text="Page 2"),
            LinkInfo(url="https://example.com/page3", text="Page 3"),
        ]

        filtered = scorer.filter_same_domain(links, "https://example.com")

        assert len(filtered) == 2
        assert all("example.com" in link.url for link in filtered)


# =============================================================================
# CATEGORIZATION TESTS
# =============================================================================

class TestCategorization:
    """Tests for link categorization."""

    def test_categorize_links(self):
        """Test categorizing links by type."""
        scorer = LinkScorer()
        scored_links = [
            ScoredLink(url="https://example.com/about", text="About", score=0.9),
            ScoredLink(url="https://example.com/team", text="Team", score=0.85),
            ScoredLink(url="https://example.com/products", text="Products", score=0.8),
            ScoredLink(url="https://example.com/news", text="News", score=0.7),
            ScoredLink(url="https://example.com/random", text="Random", score=0.5),
        ]

        categories = scorer.categorize_links(scored_links)

        assert "about" in categories
        assert "leadership" in categories
        assert "products" in categories
        assert "news" in categories
        assert "other" in categories

    def test_get_diverse_links(self):
        """Test getting diverse links from categories."""
        scorer = LinkScorer()
        scored_links = [
            ScoredLink(url="https://example.com/about", text="About", score=0.9),
            ScoredLink(url="https://example.com/about-us", text="About Us", score=0.85),
            ScoredLink(url="https://example.com/team", text="Team", score=0.85),
            ScoredLink(url="https://example.com/leadership", text="Leadership", score=0.8),
            ScoredLink(url="https://example.com/products", text="Products", score=0.8),
            ScoredLink(url="https://example.com/services", text="Services", score=0.75),
        ]

        diverse = scorer.get_diverse_links(scored_links, per_category=1, total_limit=4)

        # Should get one from each category
        assert len(diverse) <= 4
        # Should have variety
        urls = [link.url for link in diverse]
        assert len(set(urls)) == len(urls)  # No duplicates


# =============================================================================
# SINGLETON TESTS
# =============================================================================

class TestSingleton:
    """Tests for singleton access."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_link_scorer()

    def teardown_method(self):
        """Clean up after each test."""
        reset_link_scorer()

    def test_get_link_scorer_singleton(self):
        """Test that get_link_scorer returns singleton."""
        scorer1 = get_link_scorer()
        scorer2 = get_link_scorer()

        assert scorer1 is scorer2

    def test_reset_link_scorer(self):
        """Test resetting the singleton."""
        scorer1 = get_link_scorer()
        reset_link_scorer()
        scorer2 = get_link_scorer()

        assert scorer1 is not scorer2


# =============================================================================
# CONVENIENCE FUNCTION TESTS
# =============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_link_scorer()

    def test_score_links_function(self):
        """Test score_links convenience function."""
        links = [
            LinkInfo(url="https://example.com/about", text="About"),
            LinkInfo(url="https://example.com/login", text="Login"),
        ]

        scored = score_links(links)

        assert len(scored) == 2
        assert scored[0].score > scored[1].score

    def test_get_best_links_function(self):
        """Test get_best_links convenience function."""
        links = [
            LinkInfo(url="https://example.com/about", text="About"),
            LinkInfo(url="https://example.com/team", text="Team"),
            LinkInfo(url="https://example.com/login", text="Login"),
        ]

        best = get_best_links(links, limit=2)

        assert len(best) == 2
        assert all(link.score >= 0.3 for link in best)


# =============================================================================
# PATTERN TESTS
# =============================================================================

class TestPatterns:
    """Tests for URL patterns."""

    def test_high_value_patterns_exist(self):
        """Test that high-value patterns are defined."""
        assert len(HIGH_VALUE_PATTERNS) > 0
        assert '/about' in HIGH_VALUE_PATTERNS
        assert '/leadership' in HIGH_VALUE_PATTERNS

    def test_low_value_patterns_exist(self):
        """Test that low-value patterns are defined."""
        assert len(LOW_VALUE_PATTERNS) > 0
        assert '/login' in LOW_VALUE_PATTERNS
        assert '/cart' in LOW_VALUE_PATTERNS

    def test_custom_patterns(self):
        """Test using custom patterns."""
        custom_high = {'/custom-page': 0.95}
        custom_low = {'/bad-page': -0.8}

        scorer = LinkScorer(
            high_value_patterns=custom_high,
            low_value_patterns=custom_low
        )

        high_link = LinkInfo(url="https://example.com/custom-page", text="Custom")
        low_link = LinkInfo(url="https://example.com/bad-page", text="Bad")

        high_scored = scorer.score_link(high_link)
        low_scored = scorer.score_link(low_link)

        assert high_scored.score > low_scored.score
