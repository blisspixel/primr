"""
Pagination detection and handling for web scraping.

This module provides:
- Detection of pagination patterns in HTML
- URL generation for paginated content
- Infinite scroll detection
- Load more button detection
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from primr.utils.logging_config import get_logger

logger = get_logger("data.pagination")


class PaginationType(Enum):
    """Types of pagination patterns."""

    NUMBERED = "numbered"        # ?page=1, ?page=2
    OFFSET = "offset"            # ?offset=0, ?offset=10
    CURSOR = "cursor"            # ?cursor=abc123
    PATH = "path"                # /page/1, /page/2
    LOAD_MORE = "load_more"      # JavaScript load more button
    INFINITE_SCROLL = "infinite" # Infinite scroll
    NONE = "none"                # No pagination detected


@dataclass
class PaginationInfo:
    """Information about detected pagination."""

    pagination_type: PaginationType
    current_page: int = 1
    total_pages: int | None = None
    has_next: bool = False
    has_prev: bool = False
    next_url: str | None = None
    prev_url: str | None = None
    all_page_urls: list[str] = field(default_factory=list)
    confidence: float = 0.0
    pattern: str = ""


@dataclass
class PaginationPattern:
    """A detected pagination pattern."""

    pattern_type: PaginationType
    param_name: str = ""
    base_url: str = ""
    start_value: int = 0
    increment: int = 1
    max_pages: int | None = None


class PaginationDetector:
    """
    Detects and handles pagination in web pages.

    Example:
        detector = PaginationDetector()
        info = detector.detect(html_content, current_url)

        if info.has_next:
            next_page = info.next_url
    """

    # Common pagination parameter names
    PAGE_PARAMS = {"page", "p", "pg", "pagenum", "pagenumber"}
    OFFSET_PARAMS = {"offset", "start", "skip", "from"}
    CURSOR_PARAMS = {"cursor", "after", "next_cursor", "continuation"}

    # Pagination link patterns
    NEXT_PATTERNS = [
        r'rel=["\']?next["\']?',
        r'class=["\'][^"\']*next[^"\']*["\']',
        r'aria-label=["\'][^"\']*next[^"\']*["\']',
        r'>next<',
        r'>next\s*page<',
        r'>\s*›\s*<',
        r'>\s*»\s*<',
        r'>\s*→\s*<',
    ]

    PREV_PATTERNS = [
        r'rel=["\']?prev["\']?',
        r'class=["\'][^"\']*prev[^"\']*["\']',
        r'aria-label=["\'][^"\']*prev[^"\']*["\']',
        r'>prev<',
        r'>previous<',
        r'>\s*‹\s*<',
        r'>\s*«\s*<',
        r'>\s*←\s*<',
    ]

    # Load more button patterns
    LOAD_MORE_PATTERNS = [
        r'class=["\'][^"\']*load[-_]?more[^"\']*["\']',
        r'id=["\'][^"\']*load[-_]?more[^"\']*["\']',
        r'>load\s*more<',
        r'>show\s*more<',
        r'>view\s*more<',
        r'>see\s*more<',
    ]

    # Infinite scroll indicators
    INFINITE_SCROLL_PATTERNS = [
        r'infinite[-_]?scroll',
        r'lazy[-_]?load',
        r'scroll[-_]?load',
        r'data-infinite',
        r'IntersectionObserver',
    ]

    def __init__(self, max_pages: int = 100):
        """
        Initialize the pagination detector.

        Args:
            max_pages: Maximum pages to generate URLs for
        """
        self._max_pages = max_pages
        logger.debug(f"PaginationDetector initialized (max_pages={max_pages})")

    def detect(self, html: str, current_url: str) -> PaginationInfo:
        """
        Detect pagination in HTML content.

        Args:
            html: HTML content to analyze
            current_url: Current page URL

        Returns:
            PaginationInfo with detected pagination details
        """
        html_lower = html.lower()

        # Check for infinite scroll first
        if self._detect_infinite_scroll(html_lower):
            return PaginationInfo(
                pagination_type=PaginationType.INFINITE_SCROLL,
                confidence=0.8,
                pattern="infinite_scroll",
            )

        # Check for load more button
        if self._detect_load_more(html_lower):
            return PaginationInfo(
                pagination_type=PaginationType.LOAD_MORE,
                confidence=0.7,
                pattern="load_more_button",
            )

        # Try to detect path-based pagination first (more specific)
        path_pagination = self._detect_path_pagination(html, current_url)
        if path_pagination.pagination_type != PaginationType.NONE:
            return path_pagination

        # Try to detect URL-based pagination
        url_pagination = self._detect_url_pagination(html, current_url)
        if url_pagination.pagination_type != PaginationType.NONE:
            return url_pagination

        # No pagination detected
        return PaginationInfo(
            pagination_type=PaginationType.NONE,
            confidence=0.5,
        )

    def generate_page_urls(
        self,
        base_url: str,
        pattern: PaginationPattern,
        num_pages: int = 10,
    ) -> list[str]:
        """
        Generate URLs for multiple pages.

        Args:
            base_url: Base URL to paginate
            pattern: Pagination pattern to use
            num_pages: Number of pages to generate

        Returns:
            List of page URLs
        """
        urls = []
        num_pages = min(num_pages, self._max_pages)

        if pattern.pattern_type == PaginationType.NUMBERED:
            for i in range(pattern.start_value, pattern.start_value + num_pages):
                url = self._add_param(base_url, pattern.param_name, str(i))
                urls.append(url)

        elif pattern.pattern_type == PaginationType.OFFSET:
            for i in range(num_pages):
                offset = pattern.start_value + (i * pattern.increment)
                url = self._add_param(base_url, pattern.param_name, str(offset))
                urls.append(url)

        elif pattern.pattern_type == PaginationType.PATH:
            parsed = urlparse(base_url)
            base_path = re.sub(r'/page/\d+/?$', '', parsed.path)

            for i in range(pattern.start_value, pattern.start_value + num_pages):
                new_path = f"{base_path}/page/{i}"
                new_url = urlunparse((
                    parsed.scheme, parsed.netloc, new_path,
                    parsed.params, parsed.query, parsed.fragment
                ))
                urls.append(new_url)

        return urls

    def extract_page_links(self, html: str, base_url: str) -> list[str]:
        """
        Extract all pagination links from HTML.

        Args:
            html: HTML content
            base_url: Base URL for resolving relative links

        Returns:
            List of pagination URLs
        """
        links = set()

        # Find links with pagination patterns
        link_pattern = r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>'

        for match in re.finditer(link_pattern, html, re.I):
            href = match.group(1)
            full_match = match.group(0).lower()

            # Check if this looks like a pagination link
            is_pagination = False

            # Check for page numbers in URL
            if re.search(r'[?&](page|p|pg)=\d+', href, re.I):
                is_pagination = True
            elif re.search(r'/page/\d+', href, re.I):
                is_pagination = True

            # Check for pagination classes/attributes
            if any(p in full_match for p in ['pagination', 'pager', 'page-link']):
                is_pagination = True

            if is_pagination:
                full_url = urljoin(base_url, href)
                links.add(full_url)

        return sorted(links)

    def get_current_page(self, url: str) -> int:
        """
        Extract current page number from URL.

        Args:
            url: URL to analyze

        Returns:
            Current page number (1 if not found)
        """
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        # Check query parameters
        for param in self.PAGE_PARAMS:
            if param in params:
                try:
                    return int(params[param][0])
                except (ValueError, IndexError):
                    pass

        # Check path
        path_match = re.search(r'/page/(\d+)', parsed.path)
        if path_match:
            return int(path_match.group(1))

        return 1

    def _detect_url_pagination(self, html: str, current_url: str) -> PaginationInfo:
        """Detect URL parameter-based pagination."""
        parsed = urlparse(current_url)
        params = parse_qs(parsed.query)

        # Check for page parameter
        for param in self.PAGE_PARAMS:
            if param in params:
                try:
                    current_page = int(params[param][0])
                except (ValueError, IndexError):
                    current_page = 1

                # Find next/prev links
                next_url = self._find_next_link(html, current_url)
                prev_url = self._find_prev_link(html, current_url)

                # Estimate total pages from pagination links
                page_links = self.extract_page_links(html, current_url)
                total_pages = self._estimate_total_pages(page_links, current_page)

                return PaginationInfo(
                    pagination_type=PaginationType.NUMBERED,
                    current_page=current_page,
                    total_pages=total_pages,
                    has_next=next_url is not None,
                    has_prev=prev_url is not None or current_page > 1,
                    next_url=next_url,
                    prev_url=prev_url,
                    all_page_urls=page_links,
                    confidence=0.9,
                    pattern=f"?{param}=N",
                )

        # Check for offset parameter
        for param in self.OFFSET_PARAMS:
            if param in params:
                try:
                    current_offset = int(params[param][0])
                except (ValueError, IndexError):
                    current_offset = 0

                next_url = self._find_next_link(html, current_url)

                return PaginationInfo(
                    pagination_type=PaginationType.OFFSET,
                    current_page=current_offset // 10 + 1,  # Assume 10 per page
                    has_next=next_url is not None,
                    has_prev=current_offset > 0,
                    next_url=next_url,
                    confidence=0.85,
                    pattern=f"?{param}=N",
                )

        # Check if pagination links exist even without current param
        page_links = self.extract_page_links(html, current_url)
        if page_links:
            next_url = self._find_next_link(html, current_url)

            return PaginationInfo(
                pagination_type=PaginationType.NUMBERED,
                current_page=1,
                has_next=next_url is not None or len(page_links) > 0,
                next_url=next_url or (page_links[0] if page_links else None),
                all_page_urls=page_links,
                confidence=0.7,
                pattern="detected_links",
            )

        return PaginationInfo(pagination_type=PaginationType.NONE)

    def _detect_path_pagination(self, html: str, current_url: str) -> PaginationInfo:
        """Detect path-based pagination (/page/N)."""
        parsed = urlparse(current_url)

        path_match = re.search(r'/page/(\d+)', parsed.path)
        if path_match:
            current_page = int(path_match.group(1))

            next_url = self._find_next_link(html, current_url)
            prev_url = self._find_prev_link(html, current_url)

            return PaginationInfo(
                pagination_type=PaginationType.PATH,
                current_page=current_page,
                has_next=next_url is not None,
                has_prev=current_page > 1,
                next_url=next_url,
                prev_url=prev_url,
                confidence=0.9,
                pattern="/page/N",
            )

        # Check if path pagination links exist
        if re.search(r'/page/\d+', html, re.I):
            page_links = self.extract_page_links(html, current_url)
            path_links = [link for link in page_links if '/page/' in link]

            if path_links:
                return PaginationInfo(
                    pagination_type=PaginationType.PATH,
                    current_page=1,
                    has_next=True,
                    next_url=path_links[0],
                    all_page_urls=path_links,
                    confidence=0.8,
                    pattern="/page/N",
                )

        return PaginationInfo(pagination_type=PaginationType.NONE)

    def _detect_infinite_scroll(self, html_lower: str) -> bool:
        """Detect infinite scroll patterns."""
        for pattern in self.INFINITE_SCROLL_PATTERNS:
            if re.search(pattern, html_lower, re.I):
                return True
        return False

    def _detect_load_more(self, html_lower: str) -> bool:
        """Detect load more button patterns."""
        for pattern in self.LOAD_MORE_PATTERNS:
            if re.search(pattern, html_lower, re.I):
                return True
        return False

    def _find_next_link(self, html: str, base_url: str) -> str | None:
        """Find the next page link."""
        for pattern in self.NEXT_PATTERNS:
            # Find link containing the pattern
            link_pattern = rf'<a[^>]+href=["\']([^"\']+)["\'][^>]*{pattern}'
            match = re.search(link_pattern, html, re.I)
            if match:
                return str(urljoin(base_url, match.group(1)))

            # Try reverse order (pattern before href)
            link_pattern = rf'<a[^>]*{pattern}[^>]+href=["\']([^"\']+)["\']'
            match = re.search(link_pattern, html, re.I)
            if match:
                return str(urljoin(base_url, match.group(1)))

        return None

    def _find_prev_link(self, html: str, base_url: str) -> str | None:
        """Find the previous page link."""
        for pattern in self.PREV_PATTERNS:
            link_pattern = rf'<a[^>]+href=["\']([^"\']+)["\'][^>]*{pattern}'
            match = re.search(link_pattern, html, re.I)
            if match:
                return str(urljoin(base_url, match.group(1)))

            link_pattern = rf'<a[^>]*{pattern}[^>]+href=["\']([^"\']+)["\']'
            match = re.search(link_pattern, html, re.I)
            if match:
                return str(urljoin(base_url, match.group(1)))

        return None

    def _estimate_total_pages(self, page_links: list[str], current_page: int) -> int | None:
        """Estimate total pages from pagination links."""
        max_page = current_page

        for link in page_links:
            # Extract page number from URL
            match = re.search(r'[?&](?:page|p|pg)=(\d+)', link, re.I)
            if match:
                page_num = int(match.group(1))
                max_page = max(max_page, page_num)

            match = re.search(r'/page/(\d+)', link, re.I)
            if match:
                page_num = int(match.group(1))
                max_page = max(max_page, page_num)

        return max_page if max_page > current_page else None

    def _add_param(self, url: str, param: str, value: str) -> str:
        """Add or update a query parameter."""
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        params[param] = [value]

        new_query = urlencode(params, doseq=True)
        return urlunparse((
            parsed.scheme, parsed.netloc, parsed.path,
            parsed.params, new_query, parsed.fragment
        ))



# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_detector: PaginationDetector | None = None


def get_pagination_detector() -> PaginationDetector:
    """
    Get the global pagination detector instance.

    Returns:
        PaginationDetector instance
    """
    global _detector
    if _detector is None:
        _detector = PaginationDetector()
    return _detector


def reset_pagination_detector() -> None:
    """Reset the global detector (useful for testing)."""
    global _detector
    _detector = None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def detect_pagination(html: str, url: str) -> PaginationInfo:
    """
    Detect pagination in HTML content.

    Args:
        html: HTML content to analyze
        url: Current page URL

    Returns:
        PaginationInfo with detected pagination details
    """
    return get_pagination_detector().detect(html, url)


def get_page_urls(
    base_url: str,
    pagination_type: PaginationType = PaginationType.NUMBERED,
    param_name: str = "page",
    num_pages: int = 10,
    start_page: int = 1,
) -> list[str]:
    """
    Generate URLs for multiple pages.

    Args:
        base_url: Base URL to paginate
        pagination_type: Type of pagination
        param_name: Parameter name for page number
        num_pages: Number of pages to generate
        start_page: Starting page number

    Returns:
        List of page URLs
    """
    pattern = PaginationPattern(
        pattern_type=pagination_type,
        param_name=param_name,
        start_value=start_page,
        increment=10 if pagination_type == PaginationType.OFFSET else 1,
    )
    return get_pagination_detector().generate_page_urls(base_url, pattern, num_pages)


def extract_pagination_links(html: str, base_url: str) -> list[str]:
    """
    Extract all pagination links from HTML.

    Args:
        html: HTML content
        base_url: Base URL for resolving relative links

    Returns:
        List of pagination URLs
    """
    return get_pagination_detector().extract_page_links(html, base_url)


def get_current_page_number(url: str) -> int:
    """
    Extract current page number from URL.

    Args:
        url: URL to analyze

    Returns:
        Current page number (1 if not found)
    """
    return get_pagination_detector().get_current_page(url)
