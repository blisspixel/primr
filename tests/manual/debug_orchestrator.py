"""Debug orchestrator behavior on Stripe pricing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from primr.data.scrape import get_orchestrator

# Get orchestrator
orchestrator = get_orchestrator(enable_vision=False, use_cache=False)

# Scrape Stripe pricing
print("Scraping https://stripe.com/pricing via orchestrator...")
result = orchestrator.scrape_url('https://stripe.com/pricing')

print("\nResult:")
print(f"  Success: {result.success}")
print(f"  Tier: {result.tier}")
print(f"  Error: {result.error}")
print(f"  Error type: {result.error_type}")
print(f"  Attempts: {len(result.attempts) if result.attempts else 0}")

if result.attempts:
    print("\nAttempts:")
    for i, attempt in enumerate(result.attempts, 1):
        print(f"  {i}. {attempt.tier}: {attempt.success} - {attempt.error}")

if result.success and result.extracted_text:
    print(f"\nExtracted text: {len(result.extracted_text)} chars")
    print(f"Preview: {result.extracted_text[:200]}")
