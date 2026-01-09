"""Tests for structured content extraction and boilerplate filtering."""

import pytest
from primr.data.scraping.structured_content import (
    BoilerplateFilter,
    remove_duplicate_lines,
)
from primr.data.scraping.net import is_in_scope


class TestBoilerplateFilter:
    """Tests for BoilerplateFilter class."""
    
    def test_removes_repeated_lines_across_pages(self):
        """Lines appearing in >30% of pages should be removed."""
        bp = BoilerplateFilter()
        
        # Add 5 pages with common boilerplate
        for i in range(5):
            bp.add_page(f"""
            Welcome to our site
            Request a demo
            Page {i} unique content
            Contact us today
            © 2026 Company Inc
            """)
        
        bp.compute_boilerplate(threshold=0.3)
        
        # These should be detected as boilerplate (appear in all 5 pages)
        assert "welcome to our site" in bp.boilerplate_lines or \
               any("welcome" in line for line in bp.boilerplate_lines)
        assert "request a demo" in bp.boilerplate_lines or \
               any("request" in line and "demo" in line for line in bp.boilerplate_lines)
    
    def test_preserves_unique_content(self):
        """Unique content should not be removed."""
        bp = BoilerplateFilter()
        
        bp.add_page("Common header\nUnique content page 1\nCommon footer")
        bp.add_page("Common header\nUnique content page 2\nCommon footer")
        bp.add_page("Common header\nUnique content page 3\nCommon footer")
        
        bp.compute_boilerplate(threshold=0.3)
        
        # Unique content should not be in boilerplate
        assert "unique content page 1" not in bp.boilerplate_lines
        assert "unique content page 2" not in bp.boilerplate_lines
    
    def test_removes_cta_patterns(self):
        """Common CTA patterns should be detected as boilerplate."""
        bp = BoilerplateFilter()
        
        for i in range(4):
            bp.add_page(f"""
            Product info {i}
            Request a demo
            Get started today
            Sign up for free
            """)
        
        bp.compute_boilerplate(threshold=0.3)
        
        # Check that CTA-like patterns are detected
        boilerplate_text = " ".join(bp.boilerplate_lines)
        assert "request" in boilerplate_text or "demo" in boilerplate_text or \
               "get started" in boilerplate_text or "sign up" in boilerplate_text
    
    def test_threshold_affects_detection(self):
        """Higher threshold should detect fewer boilerplate lines."""
        bp_low = BoilerplateFilter()
        bp_high = BoilerplateFilter()
        
        # Add pages where some lines appear in 50% of pages
        pages = [
            "Header\nContent A\nFooter",
            "Header\nContent B\nFooter",
            "Different header\nContent C\nDifferent footer",
            "Different header\nContent D\nDifferent footer",
        ]
        
        for page in pages:
            bp_low.add_page(page)
            bp_high.add_page(page)
        
        bp_low.compute_boilerplate(threshold=0.3)
        bp_high.compute_boilerplate(threshold=0.6)
        
        # Lower threshold should detect more boilerplate
        assert len(bp_low.boilerplate_lines) >= len(bp_high.boilerplate_lines)


class TestWithinPageDeduplication:
    """Tests for within-page duplicate line removal."""
    
    def test_removes_adjacent_duplicates(self):
        """Adjacent duplicate lines should be removed."""
        text = "Line 1\nLine 2\nLine 2\nLine 3"
        cleaned, ratio = remove_duplicate_lines(text)
        
        assert "Line 2\nLine 2" not in cleaned
        assert ratio > 0
    
    def test_preserves_non_adjacent_duplicates(self):
        """Non-adjacent duplicates should be preserved."""
        text = "Line 1\nLine 2\nLine 3\nLine 2"
        cleaned, ratio = remove_duplicate_lines(text)
        
        # Both occurrences of Line 2 should remain
        assert cleaned.count("Line 2") == 2
    
    def test_handles_empty_text(self):
        """Empty text should return empty string."""
        cleaned, ratio = remove_duplicate_lines("")
        assert cleaned == ""
        assert ratio == 0.0


class TestScopePolicy:
    """Tests for is_in_scope function."""
    
    def test_same_domain_is_in_scope(self):
        """Same domain should be in scope."""
        assert is_in_scope(
            "https://example.com/about",
            "https://example.com"
        )
    
    def test_subdomain_is_in_scope(self):
        """Subdomains should be in scope."""
        assert is_in_scope(
            "https://docs.example.com/guide",
            "https://example.com"
        )
        assert is_in_scope(
            "https://blog.example.com/post",
            "https://example.com"
        )
        assert is_in_scope(
            "https://investors.example.com/reports",
            "https://example.com"
        )
    
    def test_external_domain_is_out_of_scope(self):
        """External domains should be out of scope."""
        assert not is_in_scope(
            "https://linkedin.com/company/example",
            "https://example.com"
        )
        assert not is_in_scope(
            "https://techcrunch.com/article",
            "https://example.com"
        )
    
    def test_www_prefix_handled(self):
        """www prefix should be handled correctly."""
        assert is_in_scope(
            "https://www.example.com/page",
            "https://example.com"
        )
        assert is_in_scope(
            "https://example.com/page",
            "https://www.example.com"
        )
    
    def test_similar_domain_is_out_of_scope(self):
        """Similar but different domains should be out of scope."""
        assert not is_in_scope(
            "https://example-corp.com/page",
            "https://example.com"
        )
        assert not is_in_scope(
            "https://myexample.com/page",
            "https://example.com"
        )
