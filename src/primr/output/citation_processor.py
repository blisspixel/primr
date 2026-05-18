"""
Citation Processor for clean numbered references.

Transforms inline markdown URLs into numbered references [1] style,
collecting all sources in a Sources appendix for professional documents.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import re
from urllib.parse import urlparse


class CitationStyle(Enum):
    """Citation formatting styles."""

    NUMBERED = "numbered"  # [1] style with appendix (default)
    INLINE = "inline"  # Preserve inline URLs as-is
    SIDECAR = "sidecar"  # Separate {company}_sources.md file


@dataclass
class SourceCitation:
    """A citation entry for the sources appendix."""

    url: str
    title: str
    reference_number: int
    accessed_at: datetime = field(default_factory=datetime.now)

    def to_appendix_entry(self) -> str:
        """Format as appendix entry: [1] Title - URL"""
        return f"[{self.reference_number}] {self.title}\n    {self.url}"


@dataclass
class CitationResult:
    """Result of processing content for citations."""

    transformed_content: str
    citations: list[SourceCitation]
    reference_map: dict[str, int]  # URL -> reference number


class CitationProcessor:
    """
    Transforms inline URLs into numbered references for clean document output.

    Input: "According to [Acme Corp](https://acme.example), the Model X..."
    Output: "According to Acme Corp [1], the Model X..."

    Reuses reference numbers for duplicate URLs.
    """

    # Pattern to match markdown links: [text](url)
    MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

    def __init__(self, style: CitationStyle = CitationStyle.NUMBERED):
        """
        Initialize the citation processor.

        Args:
            style: Citation style to use (NUMBERED, INLINE, SIDECAR)
        """
        self.style = style
        self._url_to_ref: dict[str, int] = {}
        self._citations: list[SourceCitation] = []
        self._next_ref: int = 1

    def reset(self) -> None:
        """Reset the processor state for a new document."""
        self._url_to_ref = {}
        self._citations = []
        self._next_ref = 1

    def process_content(self, content: str) -> CitationResult:
        """
        Transform inline markdown links to numbered references.

        Args:
            content: Content with markdown links [text](url)

        Returns:
            CitationResult with transformed content and citation list
        """
        if self.style == CitationStyle.INLINE:
            # Preserve URLs as-is
            return CitationResult(transformed_content=content, citations=[], reference_map={})

        def replace_link(match: re.Match[str]) -> str:
            text = match.group(1)
            url = match.group(2)

            # Skip non-http URLs (mailto:, tel:, etc.)
            if not url.startswith(("http://", "https://")):
                return str(match.group(0))  # Keep original

            ref_num = self.get_reference_number(url, text)
            return f"{text} [{ref_num}]"

        transformed = self.MARKDOWN_LINK_PATTERN.sub(replace_link, content)

        return CitationResult(
            transformed_content=transformed,
            citations=list(self._citations),
            reference_map=dict(self._url_to_ref),
        )

    def get_reference_number(self, url: str, title: str | None = None) -> int:
        """
        Get or create reference number for a URL.

        Reuses existing reference number if URL was seen before.

        Args:
            url: The URL to get a reference for
            title: Optional title for the citation

        Returns:
            Reference number (1-indexed)
        """
        # Normalize URL for deduplication
        normalized_url = self._normalize_url(url)

        if normalized_url in self._url_to_ref:
            return self._url_to_ref[normalized_url]

        ref_num = self._next_ref
        self._next_ref += 1
        self._url_to_ref[normalized_url] = ref_num

        # Create citation entry
        citation = SourceCitation(
            url=url, title=title or self._extract_domain(url), reference_number=ref_num
        )
        self._citations.append(citation)

        return ref_num

    # Tracking parameters to strip for deduplication (all lowercase for comparison)
    TRACKING_PARAMS = {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "fbclid",
        "gclid",
        "gclsrc",
        "dclid",
        "msclkid",
        "ref",
        "source",
        "ref_src",
        "ref_url",
        "_ga",
        "_gl",
        "mc_cid",
        "mc_eid",
        "trk",
        "trkinfo",
        "originalreferer",
    }

    def _normalize_url(self, url: str) -> str:
        """
        Normalize URL for deduplication.

        - Removes tracking parameters (UTM, fbclid, gclid, etc.)
        - Preserves meaningful query parameters (page, id, query, etc.)
        - Normalizes scheme and netloc to lowercase
        - Removes fragments
        - Removes trailing slashes from path
        """
        try:
            from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

            parsed = urlparse(url)

            # Normalize scheme and netloc to lowercase
            scheme = parsed.scheme.lower()
            netloc = parsed.netloc.lower()

            # Remove trailing slash from path
            path = parsed.path.rstrip("/")

            # Filter out tracking parameters but keep meaningful ones
            query = ""
            if parsed.query:
                params = parse_qs(parsed.query)
                clean_params = {
                    k: v for k, v in params.items() if k.lower() not in self.TRACKING_PARAMS
                }
                if clean_params:
                    query = urlencode(clean_params, doseq=True)

            # Reconstruct URL without fragment
            normalized = urlunparse(
                (
                    scheme,
                    netloc,
                    path,
                    "",  # params (rarely used)
                    query,
                    "",  # fragment (removed)
                )
            )

            return normalized
        except Exception:
            # Fallback to simple normalization
            return url.rstrip("/")

    def _extract_domain(self, url: str) -> str:
        """Extract domain name from URL for use as default title."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc
            # Remove www. prefix
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except Exception:
            return url

    def generate_sources_appendix(self) -> str:
        """
        Generate formatted sources appendix.

        Returns:
            Markdown-formatted sources list
        """
        if not self._citations:
            return ""

        lines = [
            "## Sources",
            "",
            f"This document references {len(self._citations)} source(s).",
            "",
        ]

        for citation in sorted(self._citations, key=lambda c: c.reference_number):
            lines.append(citation.to_appendix_entry())
            lines.append("")

        return "\n".join(lines)

    def generate_sidecar_file(self, company_name: str) -> tuple[str, str]:
        """
        Generate sidecar sources file.

        Args:
            company_name: Company name for filename

        Returns:
            Tuple of (filename, content)
        """
        # Sanitize company name for filename
        safe_name = re.sub(r"[^\w\s-]", "", company_name).strip().replace(" ", "_")
        filename = f"{safe_name}_sources.md"

        lines = [
            f"# Sources for {company_name} Research",
            "",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            f"Total sources: {len(self._citations)}",
            "",
            "---",
            "",
        ]

        for citation in sorted(self._citations, key=lambda c: c.reference_number):
            lines.append(f"### [{citation.reference_number}] {citation.title}")
            lines.append("")
            lines.append(f"**URL:** {citation.url}")
            lines.append("")
            lines.append(f"**Accessed:** {citation.accessed_at.strftime('%Y-%m-%d')}")
            lines.append("")
            lines.append("---")
            lines.append("")

        return filename, "\n".join(lines)

    @property
    def citation_count(self) -> int:
        """Get the number of unique citations."""
        return len(self._citations)

    @property
    def citations(self) -> list[SourceCitation]:
        """Get all citations in order."""
        return list(self._citations)


def process_citations(
    content: str, style: CitationStyle = CitationStyle.NUMBERED
) -> CitationResult:
    """
    Convenience function to process citations in content.

    Args:
        content: Content with markdown links
        style: Citation style to use

    Returns:
        CitationResult with transformed content
    """
    processor = CitationProcessor(style=style)
    return processor.process_content(content)
