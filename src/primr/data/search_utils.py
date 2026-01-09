"""
Google Search API integration and AI-driven query generation.
"""

import time
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

from primr.ai.llm import llm
from primr.config.config import (
    INITIAL_RETRY_DELAY,
    MAX_RETRIES,
    NUM_SEARCH_RESULTS,
    SEARCH_API_KEY,
    SEARCH_ENGINE_ID,
)
from primr.utils.circuit_breaker import CircuitBreaker
from primr.utils.logging_config import get_logger

load_dotenv()

logger = get_logger("search")

# Circuit breaker for Google Search API
_search_circuit = CircuitBreaker(
    name="google_search",
    failure_threshold=3,
    reset_timeout=60
)

# Ensure API keys are set
if not SEARCH_API_KEY or not SEARCH_ENGINE_ID:
    logger.error("Missing API Key or Search Engine ID! Check .env file.")
    exit(1)

# User-Agent Rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_5 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Version/15.5 Mobile/15E148 Safari/537.36",
]

# Sites to exclude after search (low value for business research)
EXCLUDED_SITES = [
    # Social media
    "reddit.com", "quora.com", "facebook.com", "twitter.com", "x.com",
    "pinterest.com", "tiktok.com", "tumblr.com", "instagram.com",
    "youtube.com", "linkedin.com",
    # Job/review sites
    "glassdoor.com", "indeed.com", "yelp.com", "tripadvisor.com",
    # Reference (often outdated)
    "wikipedia.org",
    # Support/forums (not news)
    "support.", "help.", "community.", "forum.", "answers.",
]


def generate_search_queries(company_name, website, section_name, context_snippet=None):
    """
    Uses LLM to generate search queries for business research.
    """
    context_text = f"Here's what we already know:\n{context_snippet}" if context_snippet else ""

    prompt = f"""
You are assisting in researching {company_name} for a professional business report.

We need more information on: {section_name}.

{context_text}

- Keep the search queries concise and effective.
- Do NOT use quotes or OR statements.
- Just return a list of three plain, direct Google-style search queries.
"""

    response = llm(prompt.strip(), model_type="research", streaming=False).strip()
    raw_queries = [line.strip("1234567890.- ") for line in response.split("\n") if line.strip()]

    cleaned_queries = []
    for q in raw_queries:
        q = q.replace('"', '')
        if " OR " in q.upper():
            parts = [part.strip() for part in q.split(" OR ")]
            cleaned_queries.extend(parts)
        else:
            cleaned_queries.append(q.strip())

    if not any("news" in q.lower() for q in cleaned_queries):
        cleaned_queries.append(f"{company_name} news")

    return cleaned_queries[:3] if cleaned_queries else [f"{company_name} {section_name} insights"]


def search_google(query, company_name, website, num_results=NUM_SEARCH_RESULTS):
    """Performs a structured Google search using the Custom Search API."""

    # Check circuit breaker before making request
    if not _search_circuit.can_execute():
        logger.warning("Search API circuit breaker open, skipping search")
        return []

    formatted_query = f"{company_name} {query}".strip()
    if website:
        # Extract domain from website URL for -site: filter
        domain = urlparse(website).netloc.lower().replace("www.", "")
        if domain:
            formatted_query += f" -site:{domain}"

    search_url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "q": formatted_query,
        "key": SEARCH_API_KEY,
        "cx": SEARCH_ENGINE_ID,
        "num": min(num_results, 10),
    }

    retry_delay = INITIAL_RETRY_DELAY
    attempt = 0

    while attempt < MAX_RETRIES:
        try:
            response = requests.get(search_url, params=params, timeout=15)
            response.raise_for_status()
            search_results = response.json()

            if "items" not in search_results or not search_results["items"]:
                logger.debug("No items in API response, retrying with fallback")
                fallback_query = f"{company_name} {query}".replace('"', '').replace(" OR ", " ")
                params["q"] = fallback_query
                attempt += 1
                time.sleep(retry_delay)
                retry_delay *= 2
                continue

            structured_results = []
            for item in search_results["items"]:
                url = item.get("link", "").strip()
                title = item.get("title", "No Title").strip()

                if any(site in url.lower() for site in EXCLUDED_SITES):
                    continue

                structured_results.append({"title": title, "url": url})

            if structured_results:
                logger.debug(f"Found {len(structured_results)} search results")
                _search_circuit.record_success()
                return structured_results

        except requests.exceptions.RequestException as e:
            logger.warning(f"API request failed: {e}")
            _search_circuit.record_failure()
            time.sleep(retry_delay)
            retry_delay *= 2

        attempt += 1

    logger.debug("All searches failed")
    _search_circuit.record_failure()
    return []


if __name__ == "__main__":
    # CLI Testing Mode
    company = input("\nEnter company name: ").strip()
    website = input("Enter company website (optional): ").strip()
    report_section = input("Enter research focus: ").strip()

    if not company or not report_section:
        print("Missing input. Exiting.")
        exit(1)

    queries = generate_search_queries(company, website, report_section)

    for query in queries:
        print(f"\nQuery: {query}")
        results = search_google(query, company, website)

        if results:
            print("Results:")
            for i, result in enumerate(results, 1):
                print(f"  {i}. {result['title']} - {result['url']}")
        else:
            print("No results found.")
