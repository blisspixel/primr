"""Shared Chromium launch configuration for browser scraping tiers."""

from __future__ import annotations

import os

SANDBOX_OPT_OUT = os.getenv("PRIMR_DISABLE_CHROMIUM_SANDBOX", "").strip().lower() in {
    "1",
    "true",
    "yes",
}

# Primr renders arbitrary third-party company websites, i.e. attacker-
# controlled JavaScript. The Chromium sandbox is the primary containment
# boundary for renderer compromise, so the previous unconditional
# --no-sandbox / --disable-setuid-sandbox flags removed our last line of
# defense and were a regression. Sandbox is now on by default and only disabled
# when an operator explicitly opts in via PRIMR_DISABLE_CHROMIUM_SANDBOX=1.
SANDBOX_ARGS = ["--no-sandbox", "--disable-setuid-sandbox"] if SANDBOX_OPT_OUT else []

BROWSER_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-http2",
    *SANDBOX_ARGS,
    "--disable-dev-shm-usage",
    "--disable-infobars",
    "--disable-background-networking",
    "--disable-breakpad",
    "--disable-component-update",
    "--disable-domain-reliability",
    "--disable-features=AudioServiceOutOfProcess,IsolateOrigins,site-per-process",
    "--disable-hang-monitor",
    "--disable-ipc-flooding-protection",
    "--disable-popup-blocking",
    "--disable-prompt-on-repost",
    "--disable-renderer-backgrounding",
    "--disable-sync",
    "--force-color-profile=srgb",
    "--metrics-recording-only",
    "--no-first-run",
    "--password-store=basic",
    "--use-mock-keychain",
    "--export-tagged-pdf",
]
