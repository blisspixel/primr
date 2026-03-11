"""Tests for content validation."""


from primr.data.scraping.validation import (
    clear_seen_templates,
    detect_duplicate_template,
    estimate_content_quality,
    is_nav_only_page,
    validate_content,
    validate_content_density,
)


class TestValidateContent:
    """Tests for validate_content function."""

    def setup_method(self):
        """Clear seen templates before each test."""
        clear_seen_templates()

    def test_valid_content(self):
        """Should validate good content."""
        text = """
        About Our Company

        We are a leading provider of innovative solutions.
        Our team of experts has over 20 years of experience.
        We serve customers in 50 countries worldwide.

        Our mission is to empower businesses with technology.
        We believe in quality, integrity, and customer focus.

        Contact us today to learn more about our services.
        """

        result = validate_content(text, "https://example.com/about")

        assert result.valid is True
        assert result.content_density > 0.5
        assert result.is_duplicate_template is False

    def test_invalid_empty_content(self):
        """Should invalidate empty content."""
        result = validate_content("", "https://example.com")

        assert result.valid is False
        assert "no extracted text" in result.reason.lower()

    def test_invalid_short_content(self):
        """Should invalidate very short content."""
        result = validate_content("Short", "https://example.com")

        assert result.valid is False
        assert "short" in result.reason.lower()

    def test_structured_short_contact_page_is_valid(self):
        """Short contact-style pages should be preserved."""
        text = """
        Contact Us
        Office of Citizen Services
        501 South Calhoun Street
        Tallahassee, Florida 32399-2500
        850-488-7052
        """

        result = validate_content(text, "https://example.com/contact-us")

        assert result.valid is True
        assert result.content_class == "structured_short"
        assert result.counts_as_full_page is False

    def test_invalid_low_density(self):
        """Should invalidate content with low density."""
        # Create content with many repeated lines
        repeated = "Same line repeated.\n" * 50

        result = validate_content(repeated, "https://example.com")

        assert result.valid is False
        assert "density" in result.reason.lower()

    def test_detects_duplicate_template(self):
        """Should detect duplicate templates."""
        text = """
        This is a template page with some content.
        It has multiple lines of text.
        And some more content here.
        """

        # First occurrence should be valid
        result1 = validate_content(text, "https://example.com/page1")
        assert result1.valid is True
        assert result1.is_duplicate_template is False

        # Second occurrence should be detected as duplicate
        result2 = validate_content(text, "https://example.com/page2")
        assert result2.valid is False
        assert result2.is_duplicate_template is True


class TestValidateContentDensity:
    """Tests for validate_content_density function."""

    def test_high_density_unique_content(self):
        """Unique content should have high density."""
        text = """
        Line one with unique content.
        Line two with different content.
        Line three is also unique.
        Line four continues the pattern.
        Line five wraps it up.
        """

        density = validate_content_density(text)
        assert density > 0.9

    def test_low_density_repeated_content(self):
        """Repeated content should have low density."""
        text = "Same line.\n" * 20

        density = validate_content_density(text)
        assert density < 0.1

    def test_empty_content_zero_density(self):
        """Empty content should have zero density."""
        assert validate_content_density("") == 0.0
        assert validate_content_density("   ") == 0.0


class TestDetectDuplicateTemplate:
    """Tests for detect_duplicate_template function."""

    def setup_method(self):
        """Clear seen templates before each test."""
        clear_seen_templates()

    def test_first_occurrence_not_duplicate(self):
        """First occurrence should not be duplicate."""
        text = "Unique content for this test."

        assert detect_duplicate_template(text) is False

    def test_second_occurrence_is_duplicate(self):
        """Second occurrence should be duplicate."""
        text = "Content that will be seen twice."

        detect_duplicate_template(text)  # First time
        assert detect_duplicate_template(text) is True  # Second time

    def test_different_content_not_duplicate(self):
        """Different content should not be duplicate."""
        detect_duplicate_template("First unique content.")
        assert detect_duplicate_template("Second different content.") is False

    def test_empty_content_not_duplicate(self):
        """Empty content should not be duplicate."""
        assert detect_duplicate_template("") is False


class TestIsNavOnlyPage:
    """Tests for is_nav_only_page function."""

    def test_nav_only_short_content(self):
        """Very short content is nav-only."""
        assert is_nav_only_page("Home About Contact") is True

    def test_nav_only_few_lines(self):
        """Few short lines is nav-only."""
        text = "Home\nAbout\nContact\nProducts"
        assert is_nav_only_page(text) is True

    def test_real_content_not_nav_only(self):
        """Real content with paragraphs is not nav-only."""
        text = """
        About Our Company

        We are a leading provider of innovative solutions that help businesses grow.
        Our team of experts has over 20 years of experience in the industry.
        We serve customers in 50 countries worldwide with dedication and excellence.

        Our mission is to empower businesses with cutting-edge technology solutions.
        """
        assert is_nav_only_page(text) is False

    def test_empty_is_nav_only(self):
        """Empty content is nav-only."""
        assert is_nav_only_page("") is True


class TestEstimateContentQuality:
    """Tests for estimate_content_quality function."""

    def test_high_quality_content(self):
        """Good content should have high quality score."""
        text = """
        About Our Company

        We are a leading provider of innovative solutions that help businesses grow and succeed in today's competitive market.
        Our team of experts has over 20 years of experience in the industry, delivering exceptional results for our clients.
        We serve customers in 50 countries worldwide with dedication, excellence, and a commitment to quality.

        Our mission is to empower businesses with cutting-edge technology solutions that drive growth and efficiency.
        We believe in quality, integrity, and putting our customers first in everything we do.

        Contact us today to learn more about how we can help your business succeed.
        """

        quality = estimate_content_quality(text)

        assert quality["length"] > 500
        assert quality["density"] > 0.5
        assert quality["has_paragraphs"] is True
        assert quality["quality_score"] > 50

    def test_low_quality_content(self):
        """Poor content should have low quality score."""
        text = "Short.\nVery short."

        quality = estimate_content_quality(text)

        assert quality["length"] < 50
        assert quality["quality_score"] < 20

    def test_empty_content_zero_quality(self):
        """Empty content should have zero quality."""
        quality = estimate_content_quality("")

        assert quality["length"] == 0
        assert quality["quality_score"] == 0.0
