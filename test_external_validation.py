#!/usr/bin/env python
"""
Test script for external source validation.

Tests the Google search + LLM validation flow to ensure we correctly
reject articles about wrong companies with similar names.

Usage:
    python test_external_validation.py "EverTrue" "https://www.evertrue.com"
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from urllib.parse import urlparse
from primr.data.search_utils import search_google
from primr.data.scrape import scrape_external_sources_validated, get_orchestrator
from primr.utils.console import console


def test_external_validation(company_name: str, website: str):
    """Test the external source validation flow."""
    
    console.banner(f"External Source Validation Test")
    console.info(f"Company: {company_name}")
    console.info(f"Website: {website}")
    console.blank()
    
    # Extract domain for search
    domain = urlparse(website).netloc.replace("www.", "")
    
    # Test queries - one with domain, one without
    queries = [
        f'"{company_name}" "{domain}" news',
        f'"{company_name}" news',
    ]
    
    for query in queries:
        console.step(f"Search: {query}")
        
        results = search_google(query, company_name, website)
        
        if not results:
            console.warn("No search results")
            continue
        
        console.info(f"Found {len(results)} results")
        
        # Show what we found
        for i, r in enumerate(results[:5], 1):
            url = r.get("url", "")
            title = r.get("title", "")[:50]
            console.info(f"  {i}. {title}...")
            console.info(f"     {url}")
        
        # Filter out company's own site
        filtered = [
            r for r in results[:5]
            if website.lower() not in r.get("url", "").lower()
        ]
        
        if not filtered:
            console.info("All results were from company's own site")
            continue
        
        console.blank()
        console.step("Validating sources with LLM...")
        
        # Run validation
        validated = scrape_external_sources_validated(
            filtered,
            company_name=company_name,
            website=website,
            max_sources=3
        )
        
        console.blank()
        if validated:
            console.ok(f"Validated {len(validated)} sources:")
            for url in validated.keys():
                console.info(f"  ✓ {url}")
        else:
            console.warn("No sources passed validation")
        
        console.blank()
    
    console.success_box("Test Complete", f"Check logs for validation decisions")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python test_external_validation.py \"Company Name\" \"https://website.com\"")
        print()
        print("Example:")
        print("  python test_external_validation.py \"EverTrue\" \"https://www.evertrue.com\"")
        sys.exit(1)
    
    company = sys.argv[1]
    website = sys.argv[2]
    
    # Ensure website has scheme
    if not website.startswith("http"):
        website = f"https://{website}"
    
    test_external_validation(company, website)
