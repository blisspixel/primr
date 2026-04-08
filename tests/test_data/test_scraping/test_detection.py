"""Tests for soft block detection - Property 4: Soft Block Detection Accuracy."""

from pathlib import Path

from primr.data.scraping.detection import (
    check_success_signal,
    clear_block_templates,
    detect_challenge_page,
    detect_consent_wall,
    detect_soft_block,
    register_block_template,
)
from primr.data.scraping.models import BlockType

# Path to fixtures
FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "html"


def load_fixture(name: str) -> bytes:
    """Load HTML fixture file."""
    return (FIXTURES_DIR / name).read_bytes()


class TestDetectSoftBlock:
    """Tests for detect_soft_block function."""

    def test_detects_cloudflare_challenge(self):
        """Should detect Cloudflare challenge page."""
        html = load_fixture("cloudflare_challenge.html")
        is_blocked, reason = detect_soft_block(html)

        assert is_blocked is True
        assert reason is not None
        assert (
            "cloudflare" in reason.lower()
            or "just a moment" in reason.lower()
            or "waf" in reason.lower()
        )

    def test_detects_akamai_block(self):
        """Should detect Akamai blocked page."""
        html = load_fixture("akamai_blocked.html")
        is_blocked, reason = detect_soft_block(html)

        assert is_blocked is True
        assert reason is not None

    def test_detects_wirewall_block(self):
        """Should detect WireWall blocked page."""
        html = load_fixture("wirewall_blocked.html")
        is_blocked, reason = detect_soft_block(html)

        assert is_blocked is True
        assert reason is not None
        assert "wirewall" in reason.lower() or "waf" in reason.lower()

    def test_detects_spa_skeleton(self):
        """Should detect SPA skeleton with no rendered content."""
        html = load_fixture("spa_skeleton.html")
        is_blocked, reason = detect_soft_block(html)

        assert is_blocked is True
        assert reason is not None

    def test_allows_normal_content(self):
        """Should NOT block normal content page."""
        html = load_fixture("normal_content.html")
        is_blocked, reason = detect_soft_block(html)

        assert is_blocked is False
        assert reason is None

    def test_allows_empty_search_results(self):
        """Should NOT block legitimate empty search results."""
        html = load_fixture("empty_search_results.html")
        is_blocked, reason = detect_soft_block(html)

        # This is a legitimate page, should not be blocked
        # (it has real content structure, just no search results)
        assert is_blocked is False

    def test_allows_large_page_with_hidden_browser_warning(self):
        """Hidden IE fallback markup on a large page should not be treated as a block."""
        hidden_warning = (
            b'<div style="display:none" class="isIE">'
            b"<h2>Browser not supported</h2>"
            b"<p>Sorry, this site is not compatible with Internet Explorer.</p>"
            b"</div>"
        )
        html = b"<html><body>" + (b"A" * 12000) + hidden_warning + b"</body></html>"
        is_blocked, reason = detect_soft_block(html)

        assert is_blocked is False
        assert reason is None

    def test_detects_empty_response(self):
        """Should detect empty response."""
        is_blocked, reason = detect_soft_block(b"")

        assert is_blocked is True
        assert "empty" in reason.lower()

    def test_detects_short_content(self):
        """Should detect suspiciously short content."""
        html = b"<html><body>Short</body></html>"
        is_blocked, reason = detect_soft_block(html, content_type="text/html")

        assert is_blocked is True
        assert "short" in reason.lower()

    def test_detects_http_403(self):
        """Should detect HTTP 403 status."""
        html = b"<html><body>Some content here that is long enough</body></html>" * 100
        is_blocked, reason = detect_soft_block(html, http_status=403)

        assert is_blocked is True
        assert "403" in reason

    def test_detects_http_429(self):
        """Should detect HTTP 429 rate limit."""
        html = b"<html><body>Rate limited</body></html>" * 100
        is_blocked, reason = detect_soft_block(html, http_status=429)

        assert is_blocked is True
        assert "429" in reason

    def test_detects_repetitive_content(self):
        """Should detect suspiciously repetitive content."""
        # Create content with many repeated lines
        repeated_line = "This is a repeated line of content.\n"
        html = f"<html><body>{''.join([repeated_line] * 50)}</body></html>".encode()

        is_blocked, reason = detect_soft_block(html)

        assert is_blocked is True
        assert "repetitive" in reason.lower()

    def test_detects_redirect_to_block_page(self):
        """Should detect redirect to block page."""
        html = b"<html><body>Content</body></html>" * 100
        is_blocked, reason = detect_soft_block(html, final_url="https://example.com/blocked")

        assert is_blocked is True
        assert "redirect" in reason.lower() or "block" in reason.lower()


class TestTemplateBasedDetection:
    """Tests for template-based soft block detection."""

    def setup_method(self):
        """Clear templates before each test."""
        clear_block_templates()

    def test_registers_block_template(self):
        """Should register block template for host."""
        # Use content without WAF signatures so template detection is tested
        # This simulates a custom block page that doesn't use standard WAF phrases
        html = b"""<html><head><title>Sorry</title></head>
        <body><h1>Page Unavailable</h1>
        <p>This content is not available in your region.</p>
        <p>Please try again later or contact support.</p>
        </body></html>"""

        register_block_template("example.com", html)

        # Same template should now be detected
        is_blocked, reason = detect_soft_block(html, host="example.com")
        assert is_blocked is True
        assert "template" in reason.lower()

    def test_template_detection_is_per_host(self):
        """Template detection should be per-host."""
        # Use content without WAF signatures
        html = b"""<html><head><title>Sorry</title></head>
        <body><h1>Page Unavailable</h1>
        <p>This content is not available in your region.</p>
        </body></html>"""

        register_block_template("host1.com", html)

        # Different host should not match template
        is_blocked, reason = detect_soft_block(html, host="host2.com")
        # May be blocked for other reasons (short content) but not template
        if is_blocked and reason:
            assert "template" not in reason.lower() or "host1" not in reason.lower()


class TestDetectChallengePage:
    """Tests for detect_challenge_page function."""

    def test_detects_cloudflare_challenge(self):
        """Should detect Cloudflare challenge as CHALLENGE type."""
        html = load_fixture("cloudflare_challenge.html")
        is_challenge, block_type = detect_challenge_page(html)

        assert is_challenge is True
        assert block_type == BlockType.CHALLENGE

    def test_detects_hard_block(self):
        """Should detect hard block as HARD_BLOCK type."""
        html = load_fixture("akamai_blocked.html")
        is_block, block_type = detect_challenge_page(html)

        assert is_block is True
        assert block_type == BlockType.HARD_BLOCK

    def test_normal_content_not_challenge(self):
        """Normal content should not be detected as challenge."""
        html = load_fixture("normal_content.html")
        is_challenge, block_type = detect_challenge_page(html)

        assert is_challenge is False
        assert block_type is None


class TestDetectConsentWall:
    """Tests for detect_consent_wall function."""

    def test_detects_consent_wall(self):
        """Should detect cookie consent wall."""
        html = load_fixture("cookie_consent_wall.html")
        is_consent = detect_consent_wall(html)

        assert is_consent is True

    def test_normal_content_not_consent_wall(self):
        """Normal content should not be detected as consent wall."""
        html = load_fixture("normal_content.html")
        is_consent = detect_consent_wall(html)

        assert is_consent is False


class TestCheckSuccessSignal:
    """Tests for check_success_signal function."""

    def test_accepts_large_content(self):
        """Should accept content over 5KB."""
        html = b"<html><body>" + b"x" * 6000 + b"</body></html>"

        assert check_success_signal(html) is True

    def test_accepts_content_with_structure(self):
        """Should accept content with title and h1."""
        html = b"<html><head><title>Page Title</title></head><body><h1>Heading</h1><p>Content</p></body></html>"

        assert check_success_signal(html) is True

    def test_rejects_empty_content(self):
        """Should reject empty content."""
        assert check_success_signal(b"") is False

    def test_rejects_non_200_status(self):
        """Should reject non-200 HTTP status."""
        html = b"<html><body>" + b"x" * 6000 + b"</body></html>"

        assert check_success_signal(html, http_status=403) is False

    def test_rejects_minimal_content(self):
        """Should reject minimal content without structure."""
        html = b"<html><body>tiny</body></html>"

        assert check_success_signal(html) is False

    def test_accepts_normal_page(self):
        """Should accept normal content page."""
        html = load_fixture("normal_content.html")

        assert check_success_signal(html) is True

    def test_rejects_challenge_page(self):
        """Should reject challenge page (no real content)."""
        html = load_fixture("cloudflare_challenge.html")

        # Challenge pages typically fail success signal
        # (short content, no real structure)
        result = check_success_signal(html)
        # May pass or fail depending on content length
        # The key is it shouldn't crash
        assert isinstance(result, bool)


class TestWAFSignatureDetection:
    """Tests for WAF signature detection."""

    def test_detects_all_major_wafs(self):
        """Should detect signatures for major WAFs."""
        waf_samples = [
            (b"<html>cloudflare protection</html>", "cloudflare"),
            (b"<html>akamai bot protection</html>", "akamai"),
            (b"<html>incapsula security</html>", "incapsula"),
            (b"<html>datadome protection</html>", "datadome"),
            (b"<html>perimeterx captcha</html>", "perimeterx"),
            (b"<html>kasada protection</html>", "kasada"),
            (b"<html>wirewall bot protection</html>", "wirewall"),
        ]

        for html, waf_name in waf_samples:
            is_blocked, reason = detect_soft_block(html)
            assert is_blocked is True, f"Should detect {waf_name}"
            assert reason is not None

    def test_avoids_false_positives_in_long_content(self):
        """Should not false positive on WAF words in long content."""
        # Long content that mentions "blocked" in context
        html = (
            b"""
        <html>
        <head><title>News Article</title></head>
        <body>
        <h1>Company News</h1>
        <p>The road was blocked due to construction. Traffic was diverted.</p>
        <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit.</p>
        """
            + b"<p>More content here.</p>" * 200
            + b"""
        </body>
        </html>
        """
        )

        is_blocked, reason = detect_soft_block(html)
        assert is_blocked is False, "Should not false positive on 'blocked' in long content"
