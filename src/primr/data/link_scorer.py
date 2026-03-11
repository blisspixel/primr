"""
Link relevance scoring for smart link selection.

This module provides:
- Relevance scoring for discovered links
- Prioritization of high-value pages
- Duplicate content detection
- URL pattern analysis

Usage:
    scorer = LinkScorer()
    scored_links = scorer.score_links(links, company_name)
    best_links = scorer.get_top_links(scored_links, limit=10)
"""

import contextlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from urllib.parse import urlparse

from primr.utils.logging_config import get_logger

logger = get_logger("link_scorer")


# =============================================================================
# HIGH-VALUE PAGE PATTERNS
# =============================================================================

# Pages that typically contain valuable company information
HIGH_VALUE_PATTERNS = {
    # About pages
    r"/about": 0.9,
    r"/about-us": 0.9,
    r"/company": 0.85,
    r"/who-we-are": 0.85,
    r"/our-story": 0.8,
    r"/history": 0.75,
    # Leadership/Team
    r"/team": 0.85,
    r"/leadership": 0.9,
    r"/management": 0.85,
    r"/executives": 0.85,
    r"/board": 0.8,
    r"/people": 0.7,
    # Products/Services
    r"/products": 0.85,
    r"/services": 0.85,
    r"/solutions": 0.8,
    r"/offerings": 0.75,
    r"/what-we-do": 0.8,
    r"/capabilities": 0.75,
    # Investors/Financial
    r"/investors": 0.9,
    r"/investor-relations": 0.9,
    r"/financials": 0.85,
    r"/annual-report": 0.85,
    r"/sec-filings": 0.8,
    # News/Press
    r"/news": 0.7,
    r"/press": 0.75,
    r"/media": 0.7,
    r"/newsroom": 0.75,
    r"/press-releases": 0.7,
    # Careers (indicates company size/culture)
    r"/careers": 0.6,
    r"/jobs": 0.55,
    r"/join": 0.5,
    # Contact (basic info)
    r"/contact": 0.5,
    r"/locations": 0.6,
}

# Pages to avoid (low value or problematic)
LOW_VALUE_PATTERNS = {
    r"/login": -0.9,
    r"/signin": -0.9,
    r"/signup": -0.9,
    r"/register": -0.9,
    r"/cart": -0.9,
    r"/checkout": -0.9,
    r"/account": -0.8,
    r"/privacy": -0.5,
    r"/terms": -0.5,
    r"/cookie": -0.5,
    r"/legal": -0.4,
    r"/sitemap": -0.3,
    r"/search": -0.6,
    r"/tag/": -0.4,
    r"/category/": -0.3,
    r"/page/\d+": -0.5,
    r"\?.*page=": -0.4,
}

# File extensions to avoid
SKIP_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".zip",
    ".rar",
    ".tar",
    ".gz",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".mp3",
    ".mp4",
    ".avi",
    ".mov",
    ".wmv",
    ".css",
    ".js",
    ".json",
    ".xml",
}


@dataclass
class ScoredLink:
    """A link with relevance score."""

    url: str
    text: str
    score: float
    reasons: list[str] = field(default_factory=list)

    def __lt__(self, other: "ScoredLink") -> bool:
        """Enable sorting by score (descending)."""
        return self.score > other.score


@dataclass
class LinkInfo:
    """Information about a discovered link."""

    url: str
    text: str
    source_url: str | None = None


class LinkScorer:
    """
    Scores links by relevance for company research.

    Features:
    - Pattern-based scoring for high-value pages
    - Keyword matching in link text
    - Duplicate detection
    - Domain filtering

    Example:
        scorer = LinkScorer()

        links = [
            LinkInfo(url="https://example.com/about", text="About Us"),
            LinkInfo(url="https://example.com/login", text="Login"),
        ]

        scored = scorer.score_links(links, "Example Corp")
        top_links = scorer.get_top_links(scored, limit=5)
    """

    def __init__(
        self,
        high_value_patterns: dict[str, float] | None = None,
        low_value_patterns: dict[str, float] | None = None,
        skip_extensions: set[str] | None = None,
    ):
        """
        Initialize the link scorer.

        Args:
            high_value_patterns: Custom high-value URL patterns
            low_value_patterns: Custom low-value URL patterns
            skip_extensions: File extensions to skip
        """
        self._high_value = high_value_patterns or HIGH_VALUE_PATTERNS
        self._low_value = low_value_patterns or LOW_VALUE_PATTERNS
        self._skip_extensions = skip_extensions or SKIP_EXTENSIONS
        self._seen_urls: set[str] = set()
        self._seen_content_hashes: set[str] = set()

    def score_link(
        self, link: LinkInfo, company_name: str | None = None, base_domain: str | None = None
    ) -> ScoredLink:
        """
        Score a single link.

        Args:
            link: Link to score
            company_name: Company name for keyword matching
            base_domain: Base domain to prefer same-domain links

        Returns:
            ScoredLink with score and reasons
        """
        score = 0.5  # Base score
        reasons = []

        link.url.lower()
        text = link.text.lower() if link.text else ""

        # Parse URL
        try:
            parsed = urlparse(link.url)
            path = parsed.path.lower()
            domain = parsed.netloc.lower()
        except ValueError:
            return ScoredLink(url=link.url, text=link.text, score=0.0, reasons=["Invalid URL"])

        # Check for skip extensions
        for ext in self._skip_extensions:
            if path.endswith(ext):
                return ScoredLink(
                    url=link.url, text=link.text, score=0.0, reasons=[f"Skipped extension: {ext}"]
                )

        # Check high-value patterns
        for pattern, boost in self._high_value.items():
            if re.search(pattern, path):
                score += boost
                reasons.append(f"High-value pattern: {pattern}")
                break  # Only count one pattern

        # Check low-value patterns
        for pattern, penalty in self._low_value.items():
            if re.search(pattern, path):
                score += penalty  # penalty is negative
                reasons.append(f"Low-value pattern: {pattern}")
                break

        # Keyword matching in link text
        if company_name:
            company_lower = company_name.lower()
            if company_lower in text:
                score += 0.2
                reasons.append("Company name in link text")

        # Valuable keywords in link text
        valuable_keywords = [
            "about",
            "team",
            "leadership",
            "products",
            "services",
            "investors",
            "news",
            "press",
            "contact",
            "history",
        ]
        for keyword in valuable_keywords:
            if keyword in text:
                score += 0.15
                reasons.append(f"Valuable keyword: {keyword}")
                break

        # Same domain preference
        if base_domain and domain == base_domain:
            score += 0.1
            reasons.append("Same domain")

        # Penalize very long URLs (often dynamic/filtered pages)
        if len(link.url) > 150:
            score -= 0.2
            reasons.append("Long URL")

        # Penalize URLs with many query parameters
        if parsed.query and parsed.query.count("&") > 2:
            score -= 0.15
            reasons.append("Many query parameters")

        # Penalize deep paths
        path_depth = path.count("/") - 1
        if path_depth > 4:
            score -= 0.1 * (path_depth - 4)
            reasons.append(f"Deep path: {path_depth} levels")

        # Clamp score
        score = max(0.0, min(1.0, score))

        return ScoredLink(url=link.url, text=link.text, score=score, reasons=reasons)

    def score_links(
        self, links: list[LinkInfo], company_name: str | None = None, base_url: str | None = None
    ) -> list[ScoredLink]:
        """
        Score multiple links.

        Args:
            links: Links to score
            company_name: Company name for keyword matching
            base_url: Base URL to extract domain

        Returns:
            List of ScoredLink objects, sorted by score
        """
        base_domain = None
        if base_url:
            with contextlib.suppress(Exception):
                base_domain = urlparse(base_url).netloc.lower()

        scored = []
        for link in links:
            scored_link = self.score_link(link, company_name, base_domain)
            scored.append(scored_link)

        # Sort by score (descending)
        scored.sort()

        return scored

    def get_top_links(
        self, scored_links: list[ScoredLink], limit: int = 10, min_score: float = 0.3
    ) -> list[ScoredLink]:
        """
        Get top-scoring links.

        Args:
            scored_links: Scored links to filter
            limit: Maximum number of links to return
            min_score: Minimum score threshold

        Returns:
            Top links meeting criteria
        """
        filtered = [link for link in scored_links if link.score >= min_score]
        return filtered[:limit]

    def deduplicate_links(self, links: list[LinkInfo]) -> list[LinkInfo]:
        """
        Remove duplicate links.

        Args:
            links: Links to deduplicate

        Returns:
            Deduplicated links
        """
        seen = set()
        unique = []

        for link in links:
            # Normalize URL
            normalized = self._normalize_url(link.url)

            if normalized not in seen:
                seen.add(normalized)
                unique.append(link)

        return unique

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for deduplication."""
        try:
            parsed = urlparse(url)
            # Remove trailing slash, fragment, and common tracking params
            path = parsed.path.rstrip("/")
            normalized = f"{parsed.scheme}://{parsed.netloc}{path}"
            return normalized.lower()
        except ValueError:
            return url.lower()

    def filter_same_domain(self, links: list[LinkInfo], base_url: str) -> list[LinkInfo]:
        """
        Filter links to same domain only.

        Args:
            links: Links to filter
            base_url: Base URL to match domain

        Returns:
            Links from same domain
        """
        try:
            base_domain = urlparse(base_url).netloc.lower()
        except ValueError:
            return links

        return [link for link in links if urlparse(link.url).netloc.lower() == base_domain]

    def categorize_links(self, scored_links: list[ScoredLink]) -> dict[str, list[ScoredLink]]:
        """
        Categorize links by type.

        Args:
            scored_links: Scored links to categorize

        Returns:
            Dictionary of category -> links
        """
        categories = defaultdict(list)

        for link in scored_links:
            path = urlparse(link.url).path.lower()

            if any(p in path for p in ["/about", "/company", "/who-we-are"]):
                categories["about"].append(link)
            elif any(p in path for p in ["/team", "/leadership", "/management"]):
                categories["leadership"].append(link)
            elif any(p in path for p in ["/products", "/services", "/solutions"]):
                categories["products"].append(link)
            elif any(p in path for p in ["/investors", "/financials"]):
                categories["investors"].append(link)
            elif any(p in path for p in ["/news", "/press", "/media"]):
                categories["news"].append(link)
            elif any(p in path for p in ["/careers", "/jobs"]):
                categories["careers"].append(link)
            elif any(p in path for p in ["/contact", "/locations"]):
                categories["contact"].append(link)
            else:
                categories["other"].append(link)

        return dict(categories)

    def get_diverse_links(
        self, scored_links: list[ScoredLink], per_category: int = 2, total_limit: int = 15
    ) -> list[ScoredLink]:
        """
        Get diverse links from different categories.

        Args:
            scored_links: Scored links to select from
            per_category: Max links per category
            total_limit: Total max links

        Returns:
            Diverse selection of links
        """
        categories = self.categorize_links(scored_links)

        # Priority order for categories
        priority = [
            "about",
            "leadership",
            "products",
            "investors",
            "news",
            "contact",
            "careers",
            "other",
        ]

        selected: list[ScoredLink] = []
        for category in priority:
            if category in categories:
                for link in categories[category][:per_category]:
                    if len(selected) < total_limit:
                        selected.append(link)

        return selected


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

_scorer: LinkScorer | None = None


def get_link_scorer() -> LinkScorer:
    """Get the global link scorer instance."""
    global _scorer
    if _scorer is None:
        _scorer = LinkScorer()
    return _scorer


def reset_link_scorer() -> None:
    """Reset the global link scorer."""
    global _scorer
    _scorer = None


def score_links(
    links: list[LinkInfo], company_name: str | None = None, base_url: str | None = None
) -> list[ScoredLink]:
    """Score links using the global scorer."""
    return get_link_scorer().score_links(links, company_name, base_url)


def get_best_links(
    links: list[LinkInfo],
    company_name: str | None = None,
    base_url: str | None = None,
    limit: int = 10,
) -> list[ScoredLink]:
    """Get the best links from a list."""
    scorer = get_link_scorer()
    scored = scorer.score_links(links, company_name, base_url)
    return scorer.get_top_links(scored, limit=limit)
