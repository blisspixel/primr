"""Debug what's being extracted from Stripe pages."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from primr.data.scraping import extract_main_content, scrape_with_requests
from primr.data.scraping.content import is_quality_content

# Scrape Stripe pricing
print("Scraping Stripe pricing page...")
result = scrape_with_requests("https://stripe.com/pricing", 10)
print(f"Success: {result.success}")
print(f"Content length: {len(result.raw_content or b'')} bytes\n")

if result.success and result.raw_content:
    # Extract text
    print("Extracting text...")
    extracted = extract_main_content(result.raw_content)
    print(f"Extracted length: {len(extracted)} chars")
    print(f"Word count: {len(extracted.split())}")
    print(f"Preview:\n{extracted[:500]}\n")

    # Check quality
    is_quality, reason = is_quality_content(extracted)
    print(f"Quality check: {is_quality}")
    print(f"Reason: {reason}")
