"""
Manual test to verify scraping patience improvements.
Tests that scraping waits for quality data and provides detailed diagnostics.
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from primr.data.scrape import fetch_web_content


def test_scraping_patience():
    """Test scraping with 3 pages to verify patience and diagnostics."""

    print("\n" + "=" * 60)
    print("Testing Scraping Patience - 3 Pages Max")
    print("=" * 60 + "\n")

    # Test with a real site
    website = "https://stripe.com"
    company_name = "Stripe Test"

    print(f"Target: {website}")
    print("Max pages: 3")
    print("Expected: Patient scraping with detailed diagnostics\n")

    start = time.time()

    # Scrape with max 3 pages
    scraped_content = fetch_web_content(
        website=website,
        company_name=company_name,
        max_pages=3,
        use_vision=False,  # Disable vision for faster test
    )

    elapsed = time.time() - start

    print("\n" + "=" * 60)
    print("Results")
    print("=" * 60)
    print(f"Pages scraped: {len(scraped_content)}")
    print(f"Time elapsed: {elapsed:.1f}s")
    print(f"Avg per page: {elapsed / max(len(scraped_content), 1):.1f}s")

    # Show sample content
    if scraped_content:
        first_url = next(iter(scraped_content.keys()))
        first_content = scraped_content[first_url]
        print(f"\nSample content from {first_url}:")
        print(f"  Length: {len(first_content)} chars")
        print(f"  Preview: {first_content[:200]}...")

    print("\n" + "=" * 60)
    print("Verification")
    print("=" * 60)

    # Verify we got content
    assert len(scraped_content) > 0, "Should have scraped at least 1 page"
    assert len(scraped_content) <= 3, "Should not exceed max_pages"

    # Verify content quality
    for url, content in scraped_content.items():
        assert len(content) > 100, f"Content too short for {url}"
        print(f"+ {url}: {len(content)} chars")

    print("\nTest PASSED - Scraping works with patience and quality")
    print("Check logs/research_*.log for detailed diagnostics")


if __name__ == "__main__":
    test_scraping_patience()
