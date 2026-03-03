"""
5-Site Validation Test

Tests scraping success rate on real company websites.
Goal: 90%+ success rate (pages scraped / pages attempted)

Usage:
    python tests/manual/test_5_site_validation.py
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from primr.data.scrape import fetch_web_content


def test_site(website: str, company_name: str, max_pages: int = 5):
    """Test scraping a single site."""
    print(f"\n{'='*70}")
    print(f"Testing: {company_name} ({website})")
    print(f"{'='*70}\n")

    start = time.time()

    try:
        scraped_content = fetch_web_content(
            website=website,
            company_name=company_name,
            max_pages=max_pages,
            use_vision=True,  # Enable vision tier - we need the content
        )

        elapsed = time.time() - start

        # Calculate success rate
        pages_scraped = len(scraped_content)
        success_rate = (pages_scraped / max_pages) * 100 if max_pages > 0 else 0

        print(f"\n{'='*70}")
        print(f"Results: {company_name}")
        print(f"{'='*70}")
        print(f"Pages scraped: {pages_scraped}/{max_pages} ({success_rate:.0f}%)")
        print(f"Time elapsed: {elapsed:.1f}s")
        print(f"Avg per page: {elapsed/max(pages_scraped, 1):.1f}s")

        # Show content samples
        if scraped_content:
            print("\nContent samples:")
            for url, content in list(scraped_content.items())[:3]:
                print(f"  + {url}")
                print(f"    Length: {len(content)} chars")
                print(f"    Preview: {content[:100].replace(chr(10), ' ')}...")

        return {
            'company': company_name,
            'website': website,
            'pages_scraped': pages_scraped,
            'pages_attempted': max_pages,
            'success_rate': success_rate,
            'elapsed': elapsed,
            'avg_per_page': elapsed / max(pages_scraped, 1),
        }

    except Exception as e:
        print(f"\nERROR: {e}")
        return {
            'company': company_name,
            'website': website,
            'pages_scraped': 0,
            'pages_attempted': max_pages,
            'success_rate': 0,
            'elapsed': time.time() - start,
            'error': str(e),
        }


def main():
    """Run 5-site validation."""
    print("\n" + "="*70)
    print("5-SITE VALIDATION TEST")
    print("="*70)
    print("\nGoal: 90%+ success rate across diverse company sites")
    print("Testing: Link discovery -> Scrape first 5 pages -> Verify content\n")

    # Test sites - diverse industries
    test_sites = [
        ("https://www.nintendo.com", "Nintendo"),
        ("https://www.basecamp.com", "Basecamp"),
        ("https://www.cloudflare.com", "Cloudflare"),
        ("https://www.patagonia.com", "Patagonia"),
        ("https://www.mailchimp.com", "Mailchimp"),
    ]

    results = []

    for website, company_name in test_sites:
        result = test_site(website, company_name, max_pages=5)
        results.append(result)
        time.sleep(2)  # Brief pause between sites

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}\n")

    total_attempted = sum(r['pages_attempted'] for r in results)
    total_scraped = sum(r['pages_scraped'] for r in results)
    overall_success = (total_scraped / total_attempted * 100) if total_attempted > 0 else 0

    print(f"{'Company':<20} {'Success Rate':<15} {'Time':<10} {'Avg/Page'}")
    print("-" * 70)

    for r in results:
        if 'error' in r:
            print(f"{r['company']:<20} ERROR: {r['error'][:30]}")
        else:
            print(f"{r['company']:<20} {r['success_rate']:>5.0f}% ({r['pages_scraped']}/{r['pages_attempted']})      "
                  f"{r['elapsed']:>6.1f}s    {r['avg_per_page']:>5.1f}s")

    print("-" * 70)
    print(f"{'OVERALL':<20} {overall_success:>5.0f}% ({total_scraped}/{total_attempted})")
    print()

    # Verdict
    if overall_success >= 90:
        print("PASS - Success rate >= 90%")
    elif overall_success >= 80:
        print("MARGINAL - Success rate 80-89% (needs improvement)")
    else:
        print("FAIL - Success rate < 80% (unacceptable for company research)")

    print("\nTarget: 90%+ success rate")
    print(f"Actual: {overall_success:.0f}%")
    print()


if __name__ == "__main__":
    main()
