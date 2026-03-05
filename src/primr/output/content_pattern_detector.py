"""
ContentPatternDetector for premium report generation.

Detects semantic patterns in content for intelligent formatting,
including sub-headings, inline headers, financial figures, and key metrics.
"""

import re


class ContentPatternDetector:
    """Detects semantic patterns in content for intelligent formatting."""

    # Pattern: Plain text line followed by bullets = sub-heading
    SUB_HEADING_PATTERN = re.compile(r'^([A-Z][^*\-•\n]+)\n\s*[*\-•]', re.MULTILINE)

    # Pattern: "Label: content" = inline header (bold the label)
    # Excludes URLs (http:, https:, ftp:) and times (10:30)
    INLINE_HEADER_PATTERN = re.compile(r'^([A-Z][A-Za-z\s&]{2,40}):\s*(.+)$')

    # Pattern: Financial figures for highlighting
    FINANCIAL_PATTERN = re.compile(r'\$[\d,]+(?:\.\d+)?[BMK]?|\d+(?:\.\d+)?%')

    # Patterns for extracting key metrics
    # These patterns are designed to extract meaningful data, not random numbers
    METRIC_PATTERNS = {
        'revenue': re.compile(
            r'(?:Annual |Quarterly |Total )?Revenue[^:]*:\s*\$?([\d,]+(?:\.\d+)?[BMK]?)',
            re.IGNORECASE
        ),
        'profit_margin': re.compile(
            r'(?:Gross |Net |Operating )?Profit Margin[^:]*:\s*([\d.]+%)',
            re.IGNORECASE
        ),
        # Employee patterns - look for meaningful employee counts (100+)
        # Prioritize patterns like "over X employees", "X+ employees", "approximately X employees"
        'employees': re.compile(
            r'(?:over|approximately|about|~|more than)\s*([\d,]+)\s*(?:full[- ]?time\s+)?employees?'
            r'|([\d,]+)\s*(?:full[- ]?time\s+)?employees?'
            r'|employees?[^:]*:\s*~?(?:over\s+|approximately\s+|about\s+)?([\d,]+)',
            re.IGNORECASE
        ),
        'founded': re.compile(
            r'Founded[^:]*:\s*(\d{4})',
            re.IGNORECASE
        ),
        'ticker': re.compile(
            r'(?:Ticker|Stock Symbol|NYSE|NASDAQ)[^:]*:\s*([A-Z]{1,5})',
            re.IGNORECASE
        ),
        'headquarters': re.compile(
            r'(?:Headquarters|HQ|Head Office)[^:]*:\s*([^,\n]+(?:,\s*[A-Z]{2})?)',
            re.IGNORECASE
        ),
    }

    # URL prefixes to exclude from inline header detection
    URL_PREFIXES = {'http', 'https', 'ftp', 'mailto', 'tel'}

    def detect_sub_headings(self, content: str) -> list[tuple[int, str]]:
        """
        Find lines that should be formatted as sub-headings.

        A sub-heading is plain text followed immediately by bullet items.

        Args:
            content: Multi-line content string

        Returns:
            List of (line_number, sub_heading_text) tuples
        """
        sub_headings = []
        lines = content.split('\n')

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue

            # Check if this line is plain text (not a bullet, heading, etc.)
            if (stripped and
                not stripped.startswith('#') and
                not stripped.startswith('*') and
                not stripped.startswith('-') and
                not stripped.startswith('•') and
                not re.match(r'^\d+[.)]\s', stripped)):

                # Check if next non-empty line is a bullet
                for j in range(i + 1, len(lines)):
                    next_line = lines[j].strip()
                    if not next_line:
                        continue
                    if (next_line.startswith(('*', '-', '•'))):
                        sub_headings.append((i, stripped))
                    break

        return sub_headings

    def detect_inline_headers(self, line: str) -> tuple[str, str] | None:
        """
        Detect 'Label: content' patterns for bold formatting.

        Excludes false positives like URLs and times.

        Args:
            line: Single line of text

        Returns:
            Tuple of (header, content) if pattern found, None otherwise
        """
        match = self.INLINE_HEADER_PATTERN.match(line.strip())
        if match:
            header, content = match.group(1), match.group(2)
            # Exclude false positives
            if header.lower() not in self.URL_PREFIXES and not header.isdigit():
                return (header, content)
        return None

    def extract_metrics(self, content: str) -> dict[str, str]:
        """
        Extract key metrics from content for the snapshot box.

        Args:
            content: Full document content or relevant sections

        Returns:
            Dict with keys: revenue, profit_margin, employees, founded,
                           ticker, headquarters
        """
        metrics = {}

        for metric_name, pattern in self.METRIC_PATTERNS.items():
            if metric_name == 'employees':
                # Special handling for employees - find the largest meaningful number
                # to avoid picking up random small numbers
                best_count = None
                for match in pattern.finditer(content):
                    # Get the first non-None group
                    for group in match.groups():
                        if group:
                            # Parse the number, removing commas
                            try:
                                count = int(group.replace(',', ''))
                                # Only consider counts >= 10 as meaningful
                                # (avoids "3 employees" type false positives)
                                if count >= 10:
                                    if best_count is None or count > best_count:
                                        best_count = count
                            except ValueError:
                                pass
                            break
                if best_count:
                    # Format with commas for display
                    metrics['employees'] = f"{best_count:,}"
            else:
                search_match = pattern.search(content)
                if search_match:
                    metrics[metric_name] = search_match.group(1).strip()

        return metrics

    def extract_financial_figures(self, text: str) -> list[str]:
        """
        Extract all financial figures from text for highlighting.

        Args:
            text: Text content

        Returns:
            List of financial figure strings (e.g., ["$480M", "15%"])
        """
        return self.FINANCIAL_PATTERN.findall(text)

    def detect_risk_keywords(self, text: str) -> bool:
        """
        Check if text contains risk-related keywords.

        Args:
            text: Text content

        Returns:
            True if risk keywords found
        """
        risk_keywords = [
            'risk', 'threat', 'challenge', 'concern', 'weakness',
            'vulnerability', 'decline', 'loss', 'competition',
            'regulatory', 'compliance', 'uncertainty'
        ]
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in risk_keywords)

    def detect_opportunity_keywords(self, text: str) -> bool:
        """
        Check if text contains opportunity-related keywords.

        Args:
            text: Text content

        Returns:
            True if opportunity keywords found
        """
        opportunity_keywords = [
            'opportunity', 'growth', 'expansion', 'potential',
            'strength', 'advantage', 'innovation', 'market share',
            'increase', 'improve', 'optimize'
        ]
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in opportunity_keywords)
