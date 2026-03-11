"""
Google Search API test - moved from root.
"""

import csv
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from colorama import Fore, Style
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from primr.config.config import OUTPUT_DIR, SEARCH_API_KEY, SEARCH_ENGINE_ID

load_dotenv()

if not SEARCH_API_KEY or not SEARCH_ENGINE_ID:
    print(
        Fore.RED + "[ERROR] Missing API Key or Search Engine ID! Check .env file." + Style.RESET_ALL
    )
    exit(1)

EXCLUDED_SITES = {
    "reddit.com",
    "quora.com",
    "facebook.com",
    "twitter.com",
    "pinterest.com",
    "tiktok.com",
    "tumblr.com",
    "instagram.com",
}

CURRENT_YEAR = datetime.now().year
os.makedirs(OUTPUT_DIR, exist_ok=True)


def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name)[:100]


def export_results_to_csv(query, results):
    filename = sanitize_filename(query) + ".csv"
    filepath = os.path.join(OUTPUT_DIR, filename)

    with open(filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["query", "title", "url"])
        writer.writeheader()
        for row in results:
            writer.writerow({"query": query, "title": row["title"], "url": row["url"]})

    print(Fore.GREEN + f"[INFO] Results saved to: {filepath}" + Style.RESET_ALL)


def test_google_search(
    query, max_results=5, verbose=False, output_to_csv=True, retry_attempts=3, retry_delay=5
):  # noqa: PT028
    print(Fore.YELLOW + f"\n[INFO] Searching Google API for: {query}" + Style.RESET_ALL)

    search_url = "https://www.googleapis.com/customsearch/v1"
    results = []
    unique_urls = set()
    start_index = 1

    while len(results) < max_results:
        params = {
            "q": query,
            "key": SEARCH_API_KEY,
            "cx": SEARCH_ENGINE_ID,
            "num": min(10, max_results - len(results)),
            "start": start_index,
        }

        for attempt in range(1, retry_attempts + 1):
            print(
                Fore.CYAN
                + f"[DEBUG] Attempt {attempt}/{retry_attempts} (Start Index: {start_index})..."
                + Style.RESET_ALL
            )

            try:
                response = requests.get(search_url, params=params, timeout=15)
                response.raise_for_status()
                data = response.json()

                total_results = data.get("searchInformation", {}).get("totalResults", "0")
                print(
                    Fore.MAGENTA
                    + f"[INFO] Google reports {total_results} total results."
                    + Style.RESET_ALL
                )

                if verbose:
                    print(Fore.BLUE + "[DEBUG] Raw API Response:" + Style.RESET_ALL)
                    print(json.dumps(data, indent=2))

                if "items" not in data or not data["items"]:
                    print(
                        Fore.RED
                        + f"[WARN] No results in this batch. Retrying in {retry_delay}s..."
                        + Style.RESET_ALL
                    )
                    time.sleep(retry_delay)
                    continue

                for item in data["items"]:
                    url = item.get("link", "").strip()
                    title = item.get("title", "No Title").strip()

                    if any(site in url.lower() for site in EXCLUDED_SITES):
                        if verbose:
                            print(
                                Fore.YELLOW
                                + f"[INFO] Skipping (Excluded Site): {url}"
                                + Style.RESET_ALL
                            )
                        continue

                    if url not in unique_urls:
                        unique_urls.add(url)
                        results.append({"title": title, "url": url})

                        if len(results) >= max_results:
                            break

                if "queries" in data and "nextPage" in data["queries"]:
                    start_index = data["queries"]["nextPage"][0]["startIndex"]
                else:
                    break

                time.sleep(1)

            except requests.exceptions.RequestException as e:
                print(
                    Fore.RED
                    + f"[ERROR] API request failed (Attempt {attempt}): {e}"
                    + Style.RESET_ALL
                )
                time.sleep(retry_delay)
                continue

            break

    if results:
        print(
            Fore.GREEN
            + f"\n[INFO] Showing top {len(results)} results for query: {query}"
            + Style.RESET_ALL
        )
        for i, result in enumerate(results, 1):
            print(f"{i}. {result['title']}")
            print(f"   {result['url']}")

        if output_to_csv:
            export_results_to_csv(query, results)
    else:
        print(Fore.RED + "[ERROR] No valid results found after filtering." + Style.RESET_ALL)

    return results


if __name__ == "__main__":
    company_name = "Brightview Senior Living"

    test_queries = [
        f'"{company_name}" site:brightviewseniorliving.com',
        f'"{company_name}" "annual revenue"',
    ]

    for query in test_queries:
        print("\n" + "-" * 80)
        test_google_search(query, max_results=5, verbose=False, output_to_csv=True)
