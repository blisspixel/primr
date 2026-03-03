"""Debug why Stripe pages are failing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from primr.data.scraping import scrape_with_playwright, scrape_with_requests

# Test with playwright
print("Testing Stripe pricing page with playwright...")
result = scrape_with_playwright('https://stripe.com/pricing', 30)
print(f"Success: {result.success}")
print(f"Error: {result.error}")
print(f"Error type: {result.error_type}")
print(f"HTTP status: {result.http_status}")
print(f"Content length: {len(result.raw_content or b'')} bytes")

if result.raw_content:
    text = result.raw_content.decode('utf-8', errors='ignore')[:500]
    print(f"Content preview: {text}")

print("\n" + "="*60 + "\n")

# Test with simple requests
print("Testing with requests...")
result2 = scrape_with_requests('https://stripe.com/pricing', 10)
print(f"Success: {result2.success}")
print(f"Error: {result2.error}")
print(f"Content length: {len(result2.raw_content or b'')} bytes")
