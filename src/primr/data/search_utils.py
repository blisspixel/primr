"""
Web search integration and AI-driven query generation.

Supports DuckDuckGo (default, no API key needed) and Google Custom Search (optional).
Set SEARCH_PROVIDER env var to control: "auto" (default=DDG), "ddg", or "google".
"""

import os
import time
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

from primr.ai.llm import llm
from primr.config.config import (
    INITIAL_RETRY_DELAY,
    MAX_EXTERNAL_SEARCH_QUERIES,
    MAX_RETRIES,
    NUM_SEARCH_RESULTS,
    SEARCH_API_KEY,
    SEARCH_ENGINE_ID,
)
from primr.utils.circuit_breaker import CircuitBreaker
from primr.utils.logging_config import get_logger

load_dotenv()

logger = get_logger("search")

# Circuit breaker for web search
_search_circuit = CircuitBreaker(
    name="web_search",
    failure_threshold=3,
    reset_timeout=60
)

# --- Provider detection ---
SEARCH_PROVIDER = os.environ.get("SEARCH_PROVIDER", "auto").lower().strip()

# Google keys available?
_google_api_available = bool(SEARCH_API_KEY and SEARCH_ENGINE_ID)

if SEARCH_PROVIDER == "google" and not _google_api_available:
    logger.warning(
        "SEARCH_PROVIDER=google but missing SEARCH_API_KEY or SEARCH_ENGINE_ID — falling back to DuckDuckGo"
    )


def _get_active_provider() -> str:
    """Return the active search provider name: 'ddg' or 'google'."""
    if SEARCH_PROVIDER == "google" and _google_api_available:
        return "google"
    # auto, ddg, or google-without-keys all use DDG
    return "ddg"


# User-Agent Rotation (used by Google path)
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


def generate_external_search_queries(
    company_name: str,
    website: str | None = None,
    max_queries: int = MAX_EXTERNAL_SEARCH_QUERIES,
) -> list[str]:
    """Generate diverse search queries for external company intelligence.

    Unlike generate_search_queries() which targets a specific report section,
    this generates broad queries covering multiple angles of company research
    for the scrape phase's external source gathering.

    Args:
        company_name: Name of the company to research.
        website: Optional company website URL for context.

    Returns:
        List of up to max_queries search queries covering news, funding, tech,
        leadership, competitive landscape, industry analysis, and financials.
    """
    domain_hint = ""
    if website:
        domain = urlparse(website).netloc.replace("www.", "")
        domain_hint = f"\nTheir website is: {domain}"

    max_queries = max(1, max_queries)
    prompt = f"""Generate {max_queries} web search queries to research {company_name} for a business intelligence brief.{domain_hint}

Cover these angles:
- Recent news, press releases, announcements
- Funding, acquisitions, partnerships
- Technology stack, digital transformation, IT strategy
- Leadership team, CEO, executive bios, board of directors
- Competitive landscape, market position
- Industry analysis, analyst coverage, industry outlook and trends
- Financial performance, revenue, earnings, investor relations
- Industry regulatory changes upcoming legislation affecting their sector
- Executive interviews, conference presentations, earnings calls

Rules:
- One query per line, no numbering
- Plain Google-style queries, no quotes or OR operators
- Include the company name in each query
- Make queries specific enough to find high-quality sources
- Include at least 2 queries specifically about industry trends and outlook
- Include at least 1 query about executives, board members, or leadership team"""

    try:
        response = llm(prompt.strip(), model_type="fast", streaming=False).strip()
        queries = [line.strip() for line in response.split("\n") if line.strip() and len(line.strip()) > 5]
    except Exception as e:
        logger.warning(f"LLM query generation failed: {e}")
        queries = []

    # Ensure minimum coverage with fallbacks
    if len(queries) < 3:
        queries = [
            f"{company_name} news announcements",
            f"{company_name} technology strategy",
            f"{company_name} leadership executive team",
        ]

    return queries[:max_queries]


# =============================================================================
# DuckDuckGo search (default provider)
# =============================================================================

def _search_ddg(query, company_name, website, num_results=NUM_SEARCH_RESULTS):
    """Search using DuckDuckGo via the ddgs library."""
    from ddgs import DDGS
    from ddgs.exceptions import DDGSException, RatelimitException, TimeoutException

    if not _search_circuit.can_execute():
        logger.warning("Search circuit breaker open, skipping search")
        return []

    formatted_query = f"{company_name} {query}".strip()

    # Extract company domain for post-filtering (DDG has no -site: operator)
    company_domain = None
    if website:
        company_domain = urlparse(website).netloc.lower().replace("www.", "")

    try:
        # Small delay to be polite to DDG
        time.sleep(0.5)

        results = DDGS().text(formatted_query, max_results=min(num_results + 5, 20))

        structured_results = []
        for item in results:
            url = item.get("href", "").strip()
            title = item.get("title", "No Title").strip()

            # Exclude low-value sites
            if any(site in url.lower() for site in EXCLUDED_SITES):
                continue

            # Exclude company's own domain
            if company_domain and company_domain in urlparse(url).netloc.lower():
                continue

            structured_results.append({"title": title, "url": url})

            if len(structured_results) >= num_results:
                break

        # Record success even with empty results — the API call worked fine,
        # we just got no matches. Don't penalize the circuit for that.
        _search_circuit.record_success()
        if structured_results:
            logger.debug(f"DDG: Found {len(structured_results)} results for '{formatted_query[:50]}'")

        return structured_results

    except RatelimitException:
        logger.warning("DuckDuckGo rate limited, backing off")
        _search_circuit.record_failure()
        return []
    except TimeoutException:
        logger.warning("DuckDuckGo search timed out")
        _search_circuit.record_failure()
        return []
    except DDGSException as e:
        logger.warning(f"DuckDuckGo search error: {e}")
        _search_circuit.record_failure()
        return []


# =============================================================================
# Google Custom Search (optional provider)
# =============================================================================

def _search_google(query, company_name, website, num_results=NUM_SEARCH_RESULTS):
    """Performs a structured Google search using the Custom Search API."""
    if not _google_api_available:
        logger.error("Google Search API not available - missing SEARCH_API_KEY or SEARCH_ENGINE_ID")
        return []

    if not _search_circuit.can_execute():
        logger.warning("Search circuit breaker open, skipping search")
        return []

    formatted_query = f"{company_name} {query}".strip()
    if website:
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
            time.sleep(retry_delay)
            retry_delay *= 2

        attempt += 1

    # Only record a single failure after exhausting all retries
    logger.debug("All searches failed")
    _search_circuit.record_failure()
    return []


# =============================================================================
# Public API — dispatches to active provider
# =============================================================================

def search_web(query, company_name, website, num_results=NUM_SEARCH_RESULTS):
    """
    Search the web using the active provider.

    Returns list of dicts with 'title' and 'url' keys.
    Provider is determined by SEARCH_PROVIDER env var:
      - "auto" (default) or "ddg": DuckDuckGo (no API key needed)
      - "google": Google Custom Search (requires SEARCH_API_KEY + SEARCH_ENGINE_ID)
    """
    provider = _get_active_provider()
    if provider == "google":
        return _search_google(query, company_name, website, num_results)
    return _search_ddg(query, company_name, website, num_results)


# Backward compatibility alias
search_google = search_web


def lookup_company_website(company_name: str, context: dict | None = None) -> str | None:
    """
    Search DDG for a company, then use an LLM to pick the correct homepage URL.

    DDG provides candidate results; the LLM identifies which domain is the
    company's actual website using the company name plus any extra context
    (industry, revenue, location, etc.) to disambiguate.

    Args:
        company_name: Name of the company to look up
        context: Optional dict of extra info about the company from the
                 source spreadsheet (e.g. {"industry": "Utilities",
                 "Annual Revenue": "$2B"})

    Returns:
        Root domain URL (e.g. https://enbridge.com/) or None
    """
    from ddgs import DDGS
    from ddgs.exceptions import DDGSException

    # Build context hint from spreadsheet columns.
    # The caller already filters to only useful context columns (via _ColumnMap),
    # so we pass everything we receive.
    context_hint = ""
    context_for_query = ""

    # Keywords in column names that help narrow the DDG search
    _query_keywords = {"industry", "sector", "region", "country", "state", "location"}

    if context:
        query_parts = []
        llm_parts = []
        for k, v in context.items():
            if not v or str(v).lower() == "nan":
                continue
            llm_parts.append(f"{k}: {v}")
            if any(kw in k.lower() for kw in _query_keywords):
                query_parts.append(str(v))

        if query_parts:
            context_for_query = " " + " ".join(query_parts)
        if llm_parts:
            context_hint = "\nAdditional info about the company:\n" + "\n".join(f"  - {p}" for p in llm_parts)

    try:
        time.sleep(0.5)
        query = f"{company_name}{context_for_query} official website"
        results = list(DDGS().text(query, max_results=10))

        # Build a numbered list of search results for the LLM
        result_lines = []
        for i, item in enumerate(results or [], 1):
            title = item.get("title", "").strip()
            url = item.get("href", "").strip()
            if url:
                result_lines.append(f"{i}. {title} — {url}")

        results_text = "\n".join(result_lines) if result_lines else "(no search results)"

        prompt = f"""What is the official corporate website for "{company_name}"?
{context_hint}

Here are web search results that may help:
{results_text}

Instructions:
- Return ONLY the root domain URL (e.g. https://example.com/).
- If the company has rebranded (e.g. TransCanada → TC Energy), return the CURRENT website.
- You may use your own knowledge if the search results don't contain the right website.
- Do not return news sites, directories, government pages, or social media.
- If you truly cannot determine the website, return NONE.
- Return only the URL, nothing else."""

        response = llm(prompt, model_type="fast", streaming=False).strip()

        # Validate the response looks like a URL
        if response.upper() == "NONE" or not response.startswith("http"):
            return None

        # Normalize to root domain
        parsed = urlparse(response)
        if parsed.netloc:
            url = f"{parsed.scheme}://{parsed.netloc}/"
            logger.debug(f"LLM identified website for '{company_name}': {url}")
            return url

        return None

    except DDGSException as e:
        logger.warning(f"DDG lookup failed for '{company_name}': {e}")
    except Exception as e:
        logger.warning(f"Website lookup failed for '{company_name}': {e}")

    return None


if __name__ == "__main__":
    # CLI Testing Mode
    company = input("\nEnter company name: ").strip()
    website = input("Enter company website (optional): ").strip()
    report_section = input("Enter research focus: ").strip()

    if not company or not report_section:
        print("Missing input. Exiting.")
        exit(1)

    print(f"\nUsing search provider: {_get_active_provider()}")
    queries = generate_search_queries(company, website, report_section)

    for query in queries:
        print(f"\nQuery: {query}")
        results = search_web(query, company, website)

        if results:
            print("Results:")
            for i, result in enumerate(results, 1):
                print(f"  {i}. {result['title']} - {result['url']}")
        else:
            print("No results found.")
