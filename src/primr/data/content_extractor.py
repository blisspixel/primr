"""
Enhanced content extraction utilities.

This module provides:
- Structured data extraction from HTML
- Table parsing
- Financial figure extraction
- Quote identification

Usage:
    extractor = ContentExtractor()
    tables = extractor.extract_tables(html)
    figures = extractor.extract_financial_figures(text)
"""

import re
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup

from primr.utils.logging_config import get_logger

logger = get_logger("content_extractor")


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class ExtractedTable:
    """A table extracted from HTML."""

    headers: list[str]
    rows: list[list[str]]
    caption: str | None = None
    source_element: str | None = None

    @property
    def column_count(self) -> int:
        """Get number of columns."""
        return len(self.headers) if self.headers else (len(self.rows[0]) if self.rows else 0)

    @property
    def row_count(self) -> int:
        """Get number of data rows."""
        return len(self.rows)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "headers": self.headers,
            "rows": self.rows,
            "caption": self.caption,
            "column_count": self.column_count,
            "row_count": self.row_count,
        }


@dataclass
class FinancialFigure:
    """A financial figure extracted from text."""

    value: float
    raw_text: str
    unit: str  # e.g., "USD", "EUR", "%"
    scale: str  # e.g., "million", "billion"
    context: str  # Surrounding text

    @property
    def normalized_value(self) -> float:
        """Get value normalized to base units."""
        multipliers = {
            "thousand": 1_000,
            "million": 1_000_000,
            "billion": 1_000_000_000,
            "trillion": 1_000_000_000_000,
        }
        return self.value * multipliers.get(self.scale.lower(), 1)


@dataclass
class ExtractedQuote:
    """A quote extracted from text."""

    text: str
    speaker: str | None = None
    title: str | None = None
    context: str | None = None


@dataclass
class ExtractedList:
    """A list extracted from HTML."""

    items: list[str]
    list_type: str  # "ordered" or "unordered"
    title: str | None = None


# =============================================================================
# CONTENT EXTRACTOR
# =============================================================================


class ContentExtractor:
    """
    Extracts structured content from HTML and text.

    Features:
    - Table extraction with header detection
    - Financial figure parsing
    - Quote identification
    - List extraction

    Example:
        extractor = ContentExtractor()

        tables = extractor.extract_tables(html)
        figures = extractor.extract_financial_figures(text)
        quotes = extractor.extract_quotes(text)
    """

    # Currency patterns
    CURRENCY_SYMBOLS = {
        "$": "USD",
        "€": "EUR",
        "£": "GBP",
        "¥": "JPY",
        "₹": "INR",
    }

    # Scale words
    SCALE_WORDS = {
        "k": "thousand",
        "thousand": "thousand",
        "m": "million",
        "million": "million",
        "mm": "million",
        "b": "billion",
        "billion": "billion",
        "bn": "billion",
        "t": "trillion",
        "trillion": "trillion",
    }

    def __init__(self):
        """Initialize the content extractor."""
        # Compile regex patterns
        self._money_pattern = re.compile(
            r"([$€£¥₹])\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*"
            r"(thousand|million|billion|trillion|k|m|mm|b|bn|t)?",
            re.IGNORECASE,
        )

        self._percent_pattern = re.compile(r"(\d+(?:\.\d+)?)\s*%")

        self._quote_pattern = re.compile(r'["“”]([^"“”]+)["“”]', re.MULTILINE)

    def extract_tables(self, html: str) -> list[ExtractedTable]:
        """
        Extract tables from HTML.

        Args:
            html: HTML content

        Returns:
            List of ExtractedTable objects
        """
        tables = []

        try:
            soup = BeautifulSoup(html, "html.parser")

            for table_elem in soup.find_all("table"):
                table = self._parse_table(table_elem)
                if table and (table.headers or table.rows):
                    tables.append(table)

        except Exception as e:
            logger.warning(f"Error extracting tables: {e}")

        return tables

    def _parse_table(self, table_elem: Any) -> ExtractedTable | None:
        """Parse a single table element."""
        headers: list[str] = []
        rows: list[list[str]] = []
        caption: str | None = None

        try:
            # Get caption
            caption_elem = table_elem.find("caption")
            if caption_elem:
                caption = caption_elem.get_text(strip=True)

            # Get headers from thead or first row
            thead = table_elem.find("thead")
            if thead:
                header_row = thead.find("tr")
                if header_row:
                    headers = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]

            # Get body rows
            tbody = table_elem.find("tbody") or table_elem
            for tr in tbody.find_all("tr"):
                cells = tr.find_all(["td", "th"])
                if cells:
                    row = [cell.get_text(strip=True) for cell in cells]

                    # If no headers yet and this looks like a header row
                    if not headers and all(cell.name == "th" for cell in cells):
                        headers = row
                    else:
                        rows.append(row)

            return ExtractedTable(headers=headers, rows=rows, caption=caption)

        except Exception as e:
            logger.warning(f"Error parsing table: {e}")
            return None

    def extract_lists(self, html: str) -> list[ExtractedList]:
        """
        Extract lists from HTML.

        Args:
            html: HTML content

        Returns:
            List of ExtractedList objects
        """
        lists = []

        try:
            soup = BeautifulSoup(html, "html.parser")

            for list_elem in soup.find_all(["ul", "ol"]):
                items = [
                    li.get_text(strip=True)
                    for li in list_elem.find_all("li", recursive=False)
                    if li.get_text(strip=True)
                ]

                if items:
                    # Try to find a title (preceding heading)
                    title = None
                    prev = list_elem.find_previous_sibling()
                    if prev and prev.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                        title = prev.get_text(strip=True)

                    lists.append(
                        ExtractedList(
                            items=items,
                            list_type="ordered" if list_elem.name == "ol" else "unordered",
                            title=title,
                        )
                    )

        except Exception as e:
            logger.warning(f"Error extracting lists: {e}")

        return lists

    def extract_financial_figures(self, text: str) -> list[FinancialFigure]:
        """
        Extract financial figures from text.

        Args:
            text: Text content

        Returns:
            List of FinancialFigure objects
        """
        figures = []

        # Extract money amounts
        for match in self._money_pattern.finditer(text):
            symbol = match.group(1)
            value_str = match.group(2).replace(",", "")
            scale_str = match.group(3) or ""

            try:
                value = float(value_str)
                unit = self.CURRENCY_SYMBOLS.get(symbol, "USD")
                scale = self.SCALE_WORDS.get(scale_str.lower(), "") if scale_str else ""

                # Get context (surrounding text)
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end].strip()

                figures.append(
                    FinancialFigure(
                        value=value,
                        raw_text=match.group(0),
                        unit=unit,
                        scale=scale,
                        context=context,
                    )
                )

            except ValueError:
                continue

        # Extract percentages
        for match in self._percent_pattern.finditer(text):
            try:
                value = float(match.group(1))

                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end].strip()

                figures.append(
                    FinancialFigure(
                        value=value, raw_text=match.group(0), unit="%", scale="", context=context
                    )
                )

            except ValueError:
                continue

        return figures

    def extract_quotes(self, text: str) -> list[ExtractedQuote]:
        """
        Extract quotes from text.

        Args:
            text: Text content

        Returns:
            List of ExtractedQuote objects
        """
        quotes = []

        for match in self._quote_pattern.finditer(text):
            quote_text = match.group(1).strip()

            # Skip very short or very long quotes
            if len(quote_text) < 20 or len(quote_text) > 500:
                continue

            # Try to find speaker (look for "said X" or "- X" patterns)
            speaker = None
            title = None

            # Get context after quote
            end_pos = match.end()
            after_text = text[end_pos : end_pos + 100]

            # Look for attribution patterns
            attribution_patterns = [
                r",?\s*said\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
                r",?\s*-\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
                r",?\s*according to\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
            ]

            for pattern in attribution_patterns:
                attr_match = re.search(pattern, after_text)
                if attr_match:
                    speaker = attr_match.group(1)
                    break

            quotes.append(
                ExtractedQuote(
                    text=quote_text,
                    speaker=speaker,
                    title=title,
                    context=text[max(0, match.start() - 30) : min(len(text), match.end() + 100)],
                )
            )

        return quotes

    def extract_headings(self, html: str) -> dict[str, list[str]]:
        """
        Extract headings from HTML.

        Args:
            html: HTML content

        Returns:
            Dictionary of heading level -> list of headings
        """
        headings: dict[str, list[str]] = {f"h{i}": [] for i in range(1, 7)}

        try:
            soup = BeautifulSoup(html, "html.parser")

            for level in range(1, 7):
                for heading in soup.find_all(f"h{level}"):
                    text = heading.get_text(strip=True)
                    if text:
                        headings[f"h{level}"].append(text)

        except Exception as e:
            logger.warning(f"Error extracting headings: {e}")

        return headings

    def extract_metadata(self, html: str) -> dict[str, str]:
        """
        Extract metadata from HTML.

        Args:
            html: HTML content

        Returns:
            Dictionary of metadata
        """
        metadata = {}

        try:
            soup = BeautifulSoup(html, "html.parser")

            # Title
            title = soup.find("title")
            if title:
                metadata["title"] = title.get_text(strip=True)

            # Meta tags
            for meta in soup.find_all("meta"):
                name_attr = meta.get("name", meta.get("property", ""))
                content_attr = meta.get("content", "")
                # Convert to str (BeautifulSoup can return AttributeValueList)
                name = str(name_attr) if name_attr else ""
                content = str(content_attr) if content_attr else ""

                if name and content:
                    # Common meta tags
                    if name.lower() in ["description", "keywords", "author"]:
                        metadata[name.lower()] = content
                    elif name.startswith("og:"):
                        metadata[name] = content

        except Exception as e:
            logger.warning(f"Error extracting metadata: {e}")

        return metadata

    def extract_all(self, html: str) -> dict[str, Any]:
        """
        Extract all structured content from HTML.

        Args:
            html: HTML content

        Returns:
            Dictionary with all extracted content
        """
        # Get text content
        try:
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(separator=" ", strip=True)
        except (ValueError, TypeError):
            text = ""

        return {
            "metadata": self.extract_metadata(html),
            "headings": self.extract_headings(html),
            "tables": [t.to_dict() for t in self.extract_tables(html)],
            "lists": [
                {"items": lst.items, "type": lst.list_type, "title": lst.title}
                for lst in self.extract_lists(html)
            ],
            "financial_figures": [
                {"value": f.value, "unit": f.unit, "scale": f.scale, "raw": f.raw_text}
                for f in self.extract_financial_figures(text)
            ],
            "quotes": [{"text": q.text, "speaker": q.speaker} for q in self.extract_quotes(text)],
        }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

_extractor: ContentExtractor | None = None


def get_content_extractor() -> ContentExtractor:
    """Get the global content extractor instance."""
    global _extractor
    if _extractor is None:
        _extractor = ContentExtractor()
    return _extractor


def reset_content_extractor() -> None:
    """Reset the global content extractor."""
    global _extractor
    _extractor = None


def extract_tables(html: str) -> list[ExtractedTable]:
    """Extract tables from HTML."""
    return get_content_extractor().extract_tables(html)


def extract_financial_figures(text: str) -> list[FinancialFigure]:
    """Extract financial figures from text."""
    return get_content_extractor().extract_financial_figures(text)


def extract_quotes(text: str) -> list[ExtractedQuote]:
    """Extract quotes from text."""
    return get_content_extractor().extract_quotes(text)


def extract_all_content(html: str) -> dict[str, Any]:
    """Extract all structured content from HTML."""
    return get_content_extractor().extract_all(html)
