#!/usr/bin/env python
"""
Test external source relevance validation.

This tests our actual scrape_external_sources_validated() function
to verify it correctly identifies articles about the target company
and rejects articles about different companies with similar names.

Usage:
    python tests/manual/test_external_source_relevance.py "Company Name" "https://website.com"

Examples:
    python tests/manual/test_external_source_relevance.py "Softchoice" "https://www.softchoice.com"
    python tests/manual/test_external_source_relevance.py "EverTrue" "https://www.evertrue.com"
"""

import sys

sys.path.insert(0, "src")

from urllib.parse import urlparse

from primr.data.scrape import scrape_external_sources_validated
from primr.data.search_utils import search_google


def test_relevance(company_name: str, website: str):
    """Test external source relevance validation using our actual code."""

    target_domain = urlparse(website).netloc.lower().replace("www.", "")

    print(f"{'=' * 60}")
    print("EXTERNAL SOURCE RELEVANCE TEST")
    print(f"{'=' * 60}")
    print(f"Company: {company_name}")
    print(f"Website: {website}")
    print(f"Domain:  {target_domain}")
    print()

    # Use business news focused query like production code
    query = "news OR press release OR announcement"
    print(f"Search query param: {query}")
    print()

    # Get search results using production function
    results = search_google(query, company_name, website)

    if not results:
        print("No search results found.")
        return

    print(f"Google returned {len(results)} results:")
    for i, r in enumerate(results, 1):
        url = r.get("url", "")
        title = r.get("title", "")[:60]
        print(f"  {i}. {title}...")
        print(f"     {url}")
    print()

    # Filter out company's MAIN site only (exact domain match)
    # Keep subdomains like investors.company.com, blog.company.com
    filtered = []
    for r in results:
        url = r.get("url", "")
        source_domain = urlparse(url).netloc.lower().replace("www.", "")
        # Only skip exact match to main domain
        if source_domain == target_domain:
            continue
        filtered.append(r)

    print(f"After filtering own site: {len(filtered)} candidates")
    print()

    # Run our actual validation function
    print(f"{'=' * 60}")
    print("RUNNING scrape_external_sources_validated()...")
    print(f"{'=' * 60}")
    print()

    validated = scrape_external_sources_validated(
        filtered, company_name=company_name, website=website, max_sources=3
    )

    print()
    print(f"{'=' * 60}")
    print("RESULTS")
    print(f"{'=' * 60}")

    if validated:
        print(f"✓ Validated {len(validated)} source(s):")
        for url, content in validated.items():
            print(f"  • {url}")
            print(f"    ({len(content)} chars)")
    else:
        print("✗ No sources passed validation")

    print()
    print("Check logs/research_*.log for detailed validation decisions")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    company = sys.argv[1]
    website = sys.argv[2]

    if not website.startswith("http"):
        website = f"https://{website}"

    test_relevance(company, website)
