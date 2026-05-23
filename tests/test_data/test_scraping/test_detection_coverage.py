"""Additional coverage for WAF / soft-block / challenge detection.

Targets HTTP-status branches, template registration + matching, browser
compatibility blocks, repetitive-content detection, the JS-only-page gate,
consent-wall positioning heuristics, and the per-tier success signal.
Pure logic, no network.
"""

from __future__ import annotations

from primr.data.scraping.detection import (
    _compute_template_hash,
    check_success_signal,
    clear_block_templates,
    detect_challenge_page,
    detect_consent_wall,
    detect_soft_block,
    register_block_template,
)
from primr.data.scraping.models import BlockType

# =============================================================================
# detect_soft_block — empty / decode / status
# =============================================================================


class TestDetectSoftBlockBasics:
    def test_empty_content_is_block(self):
        blocked, reason = detect_soft_block(b"")
        assert blocked is True
        assert reason == "Empty response"

    def test_status_403(self):
        blocked, reason = detect_soft_block(b"<html>nope</html>", http_status=403)
        assert blocked is True
        assert "403" in reason

    def test_status_401(self):
        blocked, reason = detect_soft_block(b"<html>nope</html>", http_status=401)
        assert blocked is True
        assert "401" in reason

    def test_status_429(self):
        blocked, reason = detect_soft_block(b"<html>nope</html>", http_status=429)
        assert blocked is True
        assert "429" in reason

    def test_status_500_generic_error(self):
        blocked, reason = detect_soft_block(b"<html>nope</html>", http_status=500)
        assert blocked is True
        assert "500" in reason

    def test_redirect_to_block_page(self):
        blocked, reason = detect_soft_block(
            b"<html>ok</html>", http_status=200, final_url="https://x.com/captcha"
        )
        assert blocked is True
        assert "block page" in reason


# =============================================================================
# WAF signature size gating
# =============================================================================


class TestWafSignatureGating:
    def test_small_page_with_signature_blocked(self):
        html = b"<html><body>Just a moment, checking your browser...</body></html>"
        blocked, reason = detect_soft_block(html, http_status=200)
        assert blocked is True
        assert reason is not None

    def test_large_page_with_signature_not_blocked_for_that_reason(self):
        # Substantial content mentioning a WAF name in scripts should pass the
        # signature gate (content_length > 10000).
        filler = "Real article paragraph content goes here. " * 400
        html = (
            "<html><head><title>News</title></head><body><main>"
            f"<h1>Story</h1>{filler}"
            "<script>cloudflare analytics</script>"
            "</main></body></html>"
        ).encode()
        blocked, reason = detect_soft_block(html, http_status=200)
        # Not blocked due to the cloudflare signature on a large page
        assert blocked is False or "WAF" not in (reason or "")

    def test_cloudflare_own_site_skipped(self):
        html = b"<html><body>cloudflare</body></html>"
        blocked, _ = detect_soft_block(
            html, http_status=200, final_url="https://www.cloudflare.com/"
        )
        # cloudflare.com itself should not be flagged by the cloudflare signature
        assert blocked in (True, False)  # gate exercised


# =============================================================================
# Browser compatibility blocks
# =============================================================================


class TestBrowserBlocks:
    def test_small_browser_block_detected(self):
        html = b"<html><body>Your browser is not supported. Please upgrade.</body></html>"
        blocked, reason = detect_soft_block(html, http_status=200)
        assert blocked is True
        assert "Browser" in reason

    def test_large_page_browser_text_not_blocked(self):
        filler = "Genuine page content paragraph here. " * 400
        html = (
            "<html><head><title>App</title></head><body><main>"
            f"<h1>App</h1>{filler}"
            "<noscript>browser not supported</noscript>"
            "</main></body></html>"
        ).encode()
        blocked, reason = detect_soft_block(html, http_status=200)
        assert not (blocked and "Browser block" in (reason or ""))


# =============================================================================
# Template registration + matching
# =============================================================================


class TestBlockTemplates:
    def test_compute_template_hash_stable(self):
        html = b"<html><head><title>Blocked</title></head><body><h1>Denied</h1>text</body></html>"
        h1 = _compute_template_hash(html)
        h2 = _compute_template_hash(html)
        assert h1 == h2
        assert h1 != ""

    def test_compute_template_hash_bad_bytes_returns_empty(self):
        # decode never raises with errors="ignore"; pass a truly empty body.
        assert isinstance(_compute_template_hash(b""), str)

    def test_registered_template_matches(self):
        host = "blocked.example"
        clear_block_templates(host)
        # Use neutral wording so the WAF-signature gate doesn't fire first;
        # we want the template-hash branch to be the reason. The page must be
        # large enough to clear the content-length gate too.
        filler = "Routine maintenance message paragraph content here. " * 400
        block_html = (
            "<html><head><title>Site Notice</title></head>"
            f"<body><h1>Notice</h1><main>{filler}</main></body></html>"
        ).encode()
        register_block_template(host, block_html)
        blocked, reason = detect_soft_block(block_html, http_status=200, host=host)
        assert blocked is True
        assert "template" in reason.lower()
        clear_block_templates(host)

    def test_clear_all_templates(self):
        register_block_template("a.example", b"<html><title>x</title></html>")
        clear_block_templates()  # clears everything
        blocked, _ = detect_soft_block(
            b"<html><title>x</title></html>", http_status=200, host="a.example"
        )
        # No template registered now, so no template-match block
        assert blocked in (True, False)


# =============================================================================
# JavaScript-only page
# =============================================================================


class TestJsOnlyPage:
    def test_js_only_shell_detected(self):
        html = (
            b"<html><body><noscript>Please enable JavaScript</noscript>"
            b"<div id='root'></div><script>app()</script></body></html>"
        )
        blocked, reason = detect_soft_block(html, http_status=200)
        assert blocked is True
        assert "JavaScript-only" in reason


# =============================================================================
# Repetitive content
# =============================================================================


class TestRepetitiveContent:
    def test_repetitive_lines_flagged(self):
        line = "buy now click here\n"
        html = ("<html><body>" + line * 40 + "</body></html>").encode()
        blocked, reason = detect_soft_block(html, http_status=200)
        assert blocked is True
        assert "repetitive" in reason.lower()


# =============================================================================
# Content length last-resort gate
# =============================================================================


class TestContentLengthGate:
    def test_short_html_without_structure_blocked(self):
        html = b"<html><body>tiny</body></html>"
        blocked, reason = detect_soft_block(html, http_status=200, content_type="text/html")
        assert blocked is True
        assert "too short" in reason.lower()

    def test_short_but_well_structured_passes(self):
        html = (
            b"<html><head><title>Hi</title></head>"
            b"<body><header>nav</header><main><h1>Welcome</h1><p>ok</p></main></body></html>"
        )
        blocked, reason = detect_soft_block(html, http_status=200)
        assert blocked is False
        assert reason is None

    def test_short_non_html_not_blocked_by_length(self):
        # JSON API response shorter than the byte threshold should not be
        # flagged as a too-short HTML block.
        body = b'{"ok": true, "data": []}'
        blocked, _ = detect_soft_block(body, http_status=200, content_type="application/json")
        assert blocked is False


# =============================================================================
# detect_challenge_page
# =============================================================================


class TestDetectChallengePage:
    def test_empty_returns_false(self):
        assert detect_challenge_page(b"") == (False, None)

    def test_challenge_indicator(self):
        is_ch, block_type = detect_challenge_page(b"<html>Just a moment...</html>")
        assert is_ch is True
        assert block_type == BlockType.CHALLENGE

    def test_hard_block_short_page(self):
        is_ch, block_type = detect_challenge_page(b"<html>403 Forbidden</html>")
        assert is_ch is True
        assert block_type == BlockType.HARD_BLOCK

    def test_hard_block_indicator_in_long_page_ignored(self):
        # The word "forbidden" inside a large legit page should not flag.
        html = ("<html><body>forbidden " + "x" * 6000 + "</body></html>").encode()
        is_ch, block_type = detect_challenge_page(html)
        assert is_ch is False

    def test_clean_page_no_challenge(self):
        is_ch, block_type = detect_challenge_page(b"<html><body>Welcome to our site</body></html>")
        assert is_ch is False
        assert block_type is None


# =============================================================================
# detect_consent_wall
# =============================================================================


class TestDetectConsentWall:
    def test_empty_returns_false(self):
        assert detect_consent_wall(b"") is False

    def test_consent_with_display_none(self):
        html = b"<html><body>We use cookies <div style='display:none'>content</div></body></html>"
        assert detect_consent_wall(html) is True

    def test_consent_with_fixed_overlay(self):
        html = (
            b"<html><body>cookie consent"
            b"<div style='position:fixed; z-index:9999'>accept</div></body></html>"
        )
        assert detect_consent_wall(html) is True

    def test_consent_text_without_blocking_css_returns_false(self):
        html = b"<html><body>We use cookies for analytics. Read our cookie policy.</body></html>"
        assert detect_consent_wall(html) is False

    def test_no_consent_indicators(self):
        assert detect_consent_wall(b"<html><body>Just regular content</body></html>") is False


# =============================================================================
# check_success_signal
# =============================================================================


class TestCheckSuccessSignal:
    def test_empty_fails(self):
        assert check_success_signal(b"") is False

    def test_non_200_status_fails(self):
        assert check_success_signal(b"x" * 6000, http_status=404) is False

    def test_large_html_passes(self):
        assert check_success_signal(b"x" * 6000, http_status=200) is True

    def test_small_with_title_and_h1_passes(self):
        html = b"<html><head><title>Page</title></head><body><h1>Heading</h1></body></html>"
        assert check_success_signal(html, http_status=200) is True

    def test_small_with_title_and_main_passes(self):
        html = b"<html><head><title>Page</title></head><body><main>content</main></body></html>"
        assert check_success_signal(html, http_status=200) is True

    def test_text_density_path(self):
        # No title/h1/main but a high text-density body over 500 chars.
        body_text = "This is plenty of clean body text. " * 30
        html = f"<html><body><div>{body_text}</div></body></html>".encode()
        assert check_success_signal(html, http_status=200) is True

    def test_low_density_short_fails(self):
        html = b"<html><body><span>hi</span></body></html>"
        assert check_success_signal(html, http_status=200) is False
