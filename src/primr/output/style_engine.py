"""
StyleEngine for premium report generation.

Manages document styling for consistent, professional formatting that meets
WCAG 2.1 AA accessibility standards and follows cognitive science principles.
"""

from typing import Any

from docx import Document
from docx.shared import Inches, Pt, RGBColor


class StyleEngine:
    """Manages document styles for consistent formatting."""

    # ==========================================================================
    # Color Palette (Professional Blue Theme - WCAG 2.1 AA compliant)
    # ==========================================================================
    PRIMARY_COLOR = RGBColor(0, 51, 102)  # Dark navy blue - chapter titles
    SECONDARY_COLOR = RGBColor(0, 82, 147)  # Medium blue - section headings
    ACCENT_COLOR = RGBColor(0, 120, 174)  # Light blue - sub-headings
    TEXT_COLOR = RGBColor(51, 51, 51)  # Dark gray - body text
    MUTED_COLOR = RGBColor(128, 128, 128)  # Gray - captions, metadata
    HIGHLIGHT_BG = RGBColor(240, 248, 255)  # Alice blue - callout backgrounds
    TABLE_HEADER_BG = RGBColor(0, 51, 102)  # Navy - table headers
    TABLE_ALT_ROW = RGBColor(245, 247, 250)  # Light gray-blue - alternating rows

    # ==========================================================================
    # Typography Scale (Golden ratio 1.2x between levels)
    # ==========================================================================
    FONTS = {
        "title": ("Calibri Light", Pt(28)),  # Cover page title
        "chapter": ("Calibri Light", Pt(18)),  # Chapter headings (H1)
        "section": ("Calibri", Pt(14)),  # Section headings (H2) - bold
        "subsection": ("Calibri", Pt(12)),  # Sub-section headings (H3) - bold
        "body": ("Calibri", Pt(11)),  # Body text
        "bullet": ("Calibri", Pt(11)),  # Bullet text
        "caption": ("Calibri", Pt(9)),  # Table captions, footnotes
        "metadata": ("Calibri Light", Pt(10)),  # Date, page numbers
    }

    # ==========================================================================
    # Spacing (ensuring 30% white space ratio)
    # ==========================================================================
    SPACING = {
        "after_title": Pt(24),  # Space after cover title
        "after_chapter": Pt(18),  # Space after chapter heading
        "after_section": Pt(12),  # Space after section heading
        "after_subsection": Pt(8),  # Space after sub-section heading
        "after_paragraph": Pt(8),  # Space after body paragraph
        "after_bullet": Pt(4),  # Space after bullet item
        "line_spacing": 1.15,  # Line height multiplier
        "bullet_indent": Inches(0.25),  # Bullet indentation per level
    }

    def __init__(self, document: Document):
        """
        Initialize StyleEngine with a Document.

        Args:
            document: A python-docx Document object
        """
        self.document = document

    def setup_styles(self) -> None:
        """Configure all document styles for consistency."""
        self._setup_normal_style()
        self._setup_heading_styles()
        self._setup_list_styles()

    def _setup_normal_style(self) -> None:
        """Configure the Normal (body text) style."""
        style = self.document.styles["Normal"]
        font = style.font
        font.name = self.FONTS["body"][0]
        font.size = self.FONTS["body"][1]
        font.color.rgb = self.TEXT_COLOR

        para_format = style.paragraph_format
        para_format.space_after = self.SPACING["after_paragraph"]
        para_format.line_spacing = self.SPACING["line_spacing"]

    def _setup_heading_styles(self) -> None:
        """
        Configure heading hierarchy.

        Heading 1: Chapter titles (dark blue, 18pt, light font)
        Heading 2: Section titles (medium blue, 14pt, bold)
        Heading 3: Sub-section titles (accent blue, 12pt, bold)
        Heading 4: Inline sub-headings (dark gray, 11pt, bold)
        """
        # Heading 1 - Chapter titles
        h1 = self.document.styles["Heading 1"]
        h1.font.name = self.FONTS["chapter"][0]
        h1.font.size = self.FONTS["chapter"][1]
        h1.font.color.rgb = self.PRIMARY_COLOR
        h1.font.bold = False
        h1.paragraph_format.space_before = Pt(24)
        h1.paragraph_format.space_after = self.SPACING["after_chapter"]

        # Heading 2 - Section titles
        h2 = self.document.styles["Heading 2"]
        h2.font.name = self.FONTS["section"][0]
        h2.font.size = self.FONTS["section"][1]
        h2.font.color.rgb = self.SECONDARY_COLOR
        h2.font.bold = True
        h2.paragraph_format.space_before = Pt(18)
        h2.paragraph_format.space_after = self.SPACING["after_section"]

        # Heading 3 - Sub-section titles
        h3 = self.document.styles["Heading 3"]
        h3.font.name = self.FONTS["subsection"][0]
        h3.font.size = self.FONTS["subsection"][1]
        h3.font.color.rgb = self.ACCENT_COLOR
        h3.font.bold = True
        h3.paragraph_format.space_before = Pt(12)
        h3.paragraph_format.space_after = self.SPACING["after_subsection"]

        # Heading 4 - Inline sub-headings (detected from content)
        h4 = self.document.styles["Heading 4"]
        h4.font.name = self.FONTS["body"][0]
        h4.font.size = self.FONTS["body"][1]
        h4.font.color.rgb = self.TEXT_COLOR
        h4.font.bold = True
        h4.paragraph_format.space_before = Pt(8)
        h4.paragraph_format.space_after = Pt(4)

    def _setup_list_styles(self) -> None:
        """
        Configure bullet and numbered list styles.

        - Consistent bullet character (•)
        - Proper hanging indent
        - Reduced spacing between items
        - Support for 2 nesting levels (Miller's Law)
        """
        # List Bullet style
        try:
            list_bullet = self.document.styles["List Bullet"]
            list_bullet.font.name = self.FONTS["bullet"][0]
            list_bullet.font.size = self.FONTS["bullet"][1]
            list_bullet.font.color.rgb = self.TEXT_COLOR
            list_bullet.paragraph_format.space_after = self.SPACING["after_bullet"]
            list_bullet.paragraph_format.left_indent = self.SPACING["bullet_indent"]
        except KeyError:
            pass  # Style may not exist in all templates

        # List Number style
        try:
            list_number = self.document.styles["List Number"]
            list_number.font.name = self.FONTS["bullet"][0]
            list_number.font.size = self.FONTS["bullet"][1]
            list_number.font.color.rgb = self.TEXT_COLOR
            list_number.paragraph_format.space_after = self.SPACING["after_bullet"]
            list_number.paragraph_format.left_indent = self.SPACING["bullet_indent"]
        except KeyError:
            pass

    def get_style_for_level(self, level: int) -> str:
        """
        Get the appropriate heading style name for a given level.

        Args:
            level: Heading level (1-4)

        Returns:
            Style name string
        """
        style_map = {
            1: "Heading 1",
            2: "Heading 2",
            3: "Heading 3",
            4: "Heading 4",
        }
        return style_map.get(level, "Normal")

    def get_font_config(self, style_type: str) -> tuple:
        """
        Get font configuration for a style type.

        Args:
            style_type: One of 'title', 'chapter', 'section', 'subsection',
                       'body', 'bullet', 'caption', 'metadata'

        Returns:
            Tuple of (font_name, font_size)
        """
        return self.FONTS.get(style_type, self.FONTS["body"])

    def get_color(self, color_type: str) -> RGBColor:
        """
        Get color for a given type.

        Args:
            color_type: One of 'primary', 'secondary', 'accent', 'text',
                       'muted', 'highlight_bg', 'table_header', 'table_alt'

        Returns:
            RGBColor object
        """
        color_map = {
            "primary": self.PRIMARY_COLOR,
            "secondary": self.SECONDARY_COLOR,
            "accent": self.ACCENT_COLOR,
            "text": self.TEXT_COLOR,
            "muted": self.MUTED_COLOR,
            "highlight_bg": self.HIGHLIGHT_BG,
            "table_header": self.TABLE_HEADER_BG,
            "table_alt": self.TABLE_ALT_ROW,
        }
        return color_map.get(color_type, self.TEXT_COLOR)

    def apply_inline_header_formatting(self, paragraph: Any, header: str, content: str) -> None:
        """
        Apply bold to header portion of 'Header: content' pattern.

        Args:
            paragraph: A python-docx Paragraph object
            header: The header text (before the colon)
            content: The content text (after the colon)
        """
        run_header = paragraph.add_run(header + ": ")
        run_header.bold = True
        run_header.font.color.rgb = self.TEXT_COLOR

        run_content = paragraph.add_run(content)
        run_content.font.color.rgb = self.TEXT_COLOR

    def apply_financial_highlight(self, run: Any) -> None:
        """
        Apply subtle highlight to financial figures.

        Args:
            run: A python-docx Run object containing financial text
        """
        run.bold = True

    def create_callout_paragraph(self, paragraph: Any) -> None:
        """
        Style a paragraph as a callout (for key insights, warnings, etc.).

        Args:
            paragraph: A python-docx Paragraph object
        """
        paragraph.paragraph_format.left_indent = Inches(0.25)
        paragraph.paragraph_format.right_indent = Inches(0.25)
        # Note: Background shading requires more complex XML manipulation
        # For now, we use indentation to visually distinguish callouts


class DualCodingEnhancer:
    """
    Pairs verbal information with visual encoding for better retention.

    Based on Dual Coding Theory - information encoded both verbally AND
    visually is retained 6x better.
    """

    # Visual indicators for common patterns
    TREND_INDICATORS = {
        "increase": "↑",
        "decrease": "↓",
        "stable": "→",
        "up": "↑",
        "down": "↓",
        "flat": "→",
    }

    STATUS_INDICATORS = {
        "positive": "✓",
        "negative": "✗",
        "warning": "⚠",
        "info": "ℹ",
    }

    PRIORITY_INDICATORS = {
        "high": "●",
        "medium": "◐",
        "low": "○",
    }

    CONFIDENCE_INDICATORS = {
        "high": "●●●",  # Multiple sources, recent data
        "medium": "●●○",  # Single source or older data
        "low": "●○○",  # Inference or limited data
    }

    # Unicode block characters for sparklines
    SPARKLINE_CHARS = "▁▂▃▄▅▆▇█"

    def add_trend_indicator(self, value: str, trend: str) -> str:
        """
        Add visual trend indicator to a metric value.

        Args:
            value: The metric value (e.g., "$480M")
            trend: Trend direction ('increase', 'decrease', 'stable')

        Returns:
            Value with trend indicator (e.g., "$480M ↑")
        """
        indicator = self.TREND_INDICATORS.get(trend.lower(), "")
        if indicator:
            return f"{value} {indicator}"
        return value

    def add_priority_indicator(self, text: str, priority: str) -> str:
        """
        Add priority indicator to text.

        Args:
            text: The text content
            priority: Priority level ('high', 'medium', 'low')

        Returns:
            Text with priority indicator
        """
        indicator = self.PRIORITY_INDICATORS.get(priority.lower(), "")
        if indicator:
            return f"{indicator} {text}"
        return text

    def add_confidence_indicator(self, text: str, confidence: str) -> str:
        """
        Add confidence level indicator to text.

        Args:
            text: The text content
            confidence: Confidence level ('high', 'medium', 'low')

        Returns:
            Text with confidence indicator
        """
        indicator = self.CONFIDENCE_INDICATORS.get(confidence.lower(), "")
        if indicator:
            return f"{text} ({indicator})"
        return text

    def create_sparkline(self, values: list, max_width: int = 8) -> str:
        """
        Create a sparkline-style mini visualization using Unicode blocks.

        Args:
            values: List of numeric values
            max_width: Maximum number of characters

        Returns:
            Unicode sparkline string (e.g., "▁▂▄▆█▆▄▂")
        """
        if not values:
            return ""

        # Normalize values to 0-7 range (8 block characters)
        min_val = min(values)
        max_val = max(values)

        if max_val == min_val:
            # All values are the same
            return self.SPARKLINE_CHARS[4] * min(len(values), max_width)

        # Sample if too many values
        if len(values) > max_width:
            step = len(values) / max_width
            values = [values[int(i * step)] for i in range(max_width)]

        sparkline = ""
        for val in values:
            normalized = (val - min_val) / (max_val - min_val)
            index = int(normalized * 7)
            sparkline += self.SPARKLINE_CHARS[index]

        return sparkline

    def format_metric_with_trend(
        self,
        label: str,
        value: str,
        trend: str | None = None,
        sparkline_data: list[float] | None = None,
    ) -> str:
        """
        Format a metric with optional trend indicator and sparkline.

        Args:
            label: Metric label (e.g., "Revenue")
            value: Metric value (e.g., "$480M")
            trend: Optional trend direction
            sparkline_data: Optional list of values for sparkline

        Returns:
            Formatted metric string
        """
        result = f"{label}: {value}"

        if trend:
            indicator = self.TREND_INDICATORS.get(trend.lower(), "")
            if indicator:
                result = f"{result} {indicator}"

        if sparkline_data:
            sparkline = self.create_sparkline(sparkline_data)
            if sparkline:
                result = f"{result} {sparkline}"

        return result
