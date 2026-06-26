"""Vision fallback browser tier."""

from __future__ import annotations

import base64
import logging
import time
from typing import Any

from primr.ai.genai_factory import default_genai_http_options

from .browser_egress import (
    browser_launch_args,
    install_playwright_egress_guard,
    plan_browser_egress,
)
from .chromium_config import SANDBOX_ARGS
from .config import DEFAULT_TIMEOUT_VISION
from .models import Attempt, ErrorType, ScrapeResult

logger = logging.getLogger(__name__)


def scrape_with_vision(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_VISION,
) -> ScrapeResult:
    """
    Scrape URL using vision model (screenshot + LLM extraction).

    Tier 6: Vision fallback for image-heavy or heavily protected sites.
    Takes a screenshot and uses Gemini to extract text content.

    This is the nuclear option - costs ~$0.01-0.02 per page but works on
    almost anything that renders in a browser.

    Args:
        url: URL to scrape
        timeout: Timeout in seconds

    Returns:
        ScrapeResult with extracted_text from vision, raw_content=screenshot bytes
    """
    from primr.utils.validators import validate_url_for_request

    is_valid, normalized_url, error = validate_url_for_request(url)
    if not is_valid:
        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error=f"Invalid URL: {error}",
            tier="vision",
            elapsed_ms=0,
            attempts=[],
        )

    url = normalized_url
    egress_plan, egress_error = plan_browser_egress(url)
    if egress_error:
        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error=f"Invalid URL: {egress_error}",
            tier="vision",
            elapsed_ms=0,
            attempts=[],
        )

    tier_name = "vision"
    start_time = time.time()

    try:
        from google import genai
        from playwright.sync_api import sync_playwright

        from primr.config.settings import get_settings

        settings = get_settings()

        if not settings.api.gemini_key:
            return ScrapeResult(
                url=url,
                success=False,
                error_type=ErrorType.NETWORK_ERROR,
                error="Vision tier requires GEMINI_API_KEY",
                tier=tier_name,
                attempts=[],
            )

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=browser_launch_args(
                    [
                        "--disable-blink-features=AutomationControlled",
                        "--disable-http2",
                        *SANDBOX_ARGS,
                        "--disable-dev-shm-usage",
                    ],
                    egress_plan,
                ),
            )

            from .profiles import get_stealth_script

            context = browser.new_context(
                viewport={"width": 1280, "height": 1024},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                service_workers="block",
            )

            stealth_script = get_stealth_script()
            if stealth_script:
                context.add_init_script(stealth_script)
            install_playwright_egress_guard(context, tier_name)
            page = context.new_page()

            page.goto(url, timeout=int(timeout * 1000), wait_until="networkidle")
            page.wait_for_timeout(2000)

            final_url = page.url
            from primr.utils.security import validate_final_url_after_redirect

            is_safe, ssrf_error = validate_final_url_after_redirect(final_url)
            if not is_safe:
                page.close()
                context.close()
                browser.close()
                elapsed_ms = (time.time() - start_time) * 1000
                return ScrapeResult(
                    url=url,
                    success=False,
                    error_type=ErrorType.NETWORK_ERROR,
                    error=f"Redirect SSRF blocked: {ssrf_error}",
                    tier=tier_name,
                    elapsed_ms=elapsed_ms,
                    attempts=[
                        Attempt(
                            tier=tier_name,
                            success=False,
                            error=f"Redirect SSRF: {ssrf_error}",
                            elapsed_ms=elapsed_ms,
                        )
                    ],
                )

            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            page.wait_for_timeout(1000)

            screenshot_bytes = page.screenshot(full_page=True, type="png")

            browser.close()

        client = genai.Client(
            api_key=settings.api.gemini_key,
            http_options=default_genai_http_options(),
        )

        screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

        prompt = """Extract all readable text content from this webpage screenshot.
Focus on:
- Main headings and titles
- Body text and paragraphs
- Key facts, numbers, and statistics
- Product/service descriptions
- Company information

Ignore:
- Navigation menus
- Footer links
- Cookie banners
- Advertisements

Return the extracted text in a clean, readable format with proper paragraph breaks."""

        contents: list[Any] = [
            {"text": prompt},
            {"inline_data": {"mime_type": "image/png", "data": screenshot_b64}},
        ]

        response = client.models.generate_content(
            model=settings.ai.flash_model,
            contents=contents,
        )

        extracted_text = response.text.strip() if response.text else ""
        elapsed_ms = (time.time() - start_time) * 1000

        if not extracted_text or len(extracted_text) < 100:
            return ScrapeResult(
                url=url,
                success=False,
                error_type=ErrorType.EMPTY_CONTENT,
                error="Vision extraction returned insufficient content",
                tier=tier_name,
                raw_content=screenshot_bytes,
                elapsed_ms=elapsed_ms,
                attempts=[
                    Attempt(
                        tier=tier_name,
                        success=False,
                        error="Insufficient content",
                        elapsed_ms=elapsed_ms,
                    )
                ],
            )

        return ScrapeResult(
            url=url,
            success=True,
            raw_content=screenshot_bytes,
            extracted_text=extracted_text,
            tier=tier_name,
            content_type="vision_text",
            http_status=200,
            elapsed_ms=elapsed_ms,
            attempts=[Attempt(tier=tier_name, success=True, elapsed_ms=elapsed_ms)],
        )

    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.debug("Vision tier failed for %s: %s", url, e)
        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error=str(e),
            tier=tier_name,
            elapsed_ms=elapsed_ms,
            attempts=[Attempt(tier=tier_name, success=False, error=str(e), elapsed_ms=elapsed_ms)],
        )
