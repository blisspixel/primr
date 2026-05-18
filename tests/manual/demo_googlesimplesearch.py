"""
Simple Google Search API test - moved from root.
"""

import json
from pathlib import Path
import sys
import time

from colorama import Fore, Style
from dotenv import load_dotenv
import requests

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from primr.config.config import SEARCH_API_KEY, SEARCH_ENGINE_ID

load_dotenv()

if not SEARCH_API_KEY or not SEARCH_ENGINE_ID:
    print(
        Fore.RED + "[ERROR] Missing API Key or Search Engine ID! Check .env file." + Style.RESET_ALL
    )
    exit(1)

EXCLUDED_SITES = [
    "reddit.com",
    "quora.com",
    "facebook.com",
    "twitter.com",
    "pinterest.com",
    "tiktok.com",
    "tumblr.com",
    "instagram.com",
    "zoominfo.com",
]


def run_google_search(query, retries=3, retry_delay=5, max_results=30):
    """Tests Google Custom Search API for a given query with detailed debugging."""

    print(Fore.YELLOW + f"\n[INFO] Searching Google API for: {query}" + Style.RESET_ALL)

    search_url = "https://www.googleapis.com/customsearch/v1"
    structured_results = []

    for start_index in range(1, max_results, 10):
        params = {
            "q": query,
            "key": SEARCH_API_KEY,
            "cx": SEARCH_ENGINE_ID,
            "num": 10,
            "start": start_index,
        }

        for attempt in range(1, retries + 1):
            print(
                Fore.CYAN
                + f"[DEBUG] Attempt {attempt}/{retries}: Sending API request (Start Index: {start_index})..."
                + Style.RESET_ALL
            )

            try:
                response = requests.get(search_url, params=params, timeout=15)
                response.raise_for_status()
                search_results = response.json()

                print(Fore.BLUE + "[DEBUG] Raw API Response:" + Style.RESET_ALL)
                print(json.dumps(search_results, indent=2))

                search_results.get("searchInformation", {}).get("totalResults", "0")

                if "items" not in search_results or not search_results["items"]:
                    print(
                        Fore.RED
                        + f"[ERROR] No 'items' in API response (Attempt {attempt}/{retries})."
                        + Style.RESET_ALL
                    )
                    time.sleep(retry_delay)
                    continue

                for item in search_results["items"]:
                    url = item.get("link", "").strip()
                    title = item.get("title", "No Title").strip()

                    if any(site in url.lower() for site in EXCLUDED_SITES):
                        print(
                            Fore.YELLOW
                            + f"[INFO] Skipping (Excluded Site): {url}"
                            + Style.RESET_ALL
                        )
                        continue

                    structured_results.append({"title": title, "url": url})

                if len(structured_results) >= max_results:
                    break

                time.sleep(1)

            except requests.exceptions.RequestException as e:
                print(
                    Fore.RED
                    + f"[ERROR] API request failed (Attempt {attempt}/{retries}): {e}"
                    + Style.RESET_ALL
                )
                time.sleep(retry_delay)

    if structured_results:
        print(
            Fore.GREEN
            + f"[INFO] Found {len(structured_results)} valid search results."
            + Style.RESET_ALL
        )
        for i, result in enumerate(structured_results, 1):
            print(f"{i}. {result['title']} - {result['url']}")
        return structured_results
    else:
        print(Fore.RED + "[ERROR] No valid results found after filtering!" + Style.RESET_ALL)
        return None


if __name__ == "__main__":
    test_queries = ['"Brightview Senior Living"']

    for query in test_queries:
        print("\n" + "-" * 60)
        run_google_search(query)
