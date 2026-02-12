"""
Enhanced markdown parser for premium report generation.

Provides robust regex-based parsing that handles all formatting variations
encountered in AI-generated content.
"""

import re
from typing import Any

from primr.output.models import ContentBlock, ParsedLine


class MarkdownParser:
    """Robust markdown parser that handles all formatting variations."""

    # Bullet patterns: *, -, •, followed by 1-4 spaces
    BULLET_PATTERN = re.compile(r'^(\s*)([*\-•])\s{1,4}(.+)$')

    # Numbered list: 1. or 1) followed by space
    NUMBERED_PATTERN = re.compile(r'^(\s*)(\d+)[.)]\s+(.+)$')

    # Heading patterns: # to ####
    HEADING_PATTERN = re.compile(r'^(#{1,4})\s+(.+)$')

    # Inline header: "Label: content" where Label is capitalized
    # Excludes URLs (http:, https:, ftp:) and times (10:30)
    INLINE_HEADER_PATTERN = re.compile(r'^([A-Z][A-Za-z\s&]{2,40}):\s*(.+)$')

    # Bold patterns: **text** or __text__
    BOLD_PATTERN = re.compile(r'\*\*(.+?)\*\*|__(.+?)__')

    # Italic patterns: *text* or _text_ (single)
    ITALIC_PATTERN = re.compile(r'(?<!\*)\*([^*]+)\*(?!\*)|(?<!_)_([^_]+)_(?!_)')

    # URL pattern for excluding false positive inline headers
    URL_PREFIXES = {'http', 'https', 'ftp', 'mailto', 'tel'}

    # Markdown table patterns (Deep Research often includes tables)
    TABLE_ROW_PATTERN = re.compile(r'^\|(.+)\|$')
    TABLE_SEPARATOR_PATTERN = re.compile(r'^\|[\s\-:|]+\|$')

    def parse_line(self, line: str) -> ParsedLine:
        """
        Parse a single line and return structured result.

        Priority order:
        1. Empty line
        2. Heading (# syntax)
        3. Bullet point (*, -, •)
        4. Numbered list (1., 1))
        5. Inline header (Label: content) - only if not a bullet
        6. Plain text (fallback)

        Args:
            line: The raw line to parse

        Returns:
            ParsedLine with type, content, level, raw, and metadata
        """
        stripped = line.rstrip()

        if not stripped:
            return ParsedLine('empty', '', 0, line, {})

        # Check heading
        if match := self.HEADING_PATTERN.match(stripped):
            level = len(match.group(1))
            return ParsedLine('heading', match.group(2).strip(), level, line, {})

        # Check bullet (handles *, -, • with variable spacing)
        if match := self.BULLET_PATTERN.match(stripped):
            indent = len(match.group(1)) // 4  # 4 spaces = 1 level
            content = match.group(3)
            return ParsedLine('bullet', content, indent, line,
                            {'bullet_char': match.group(2)})

        # Check numbered
        if match := self.NUMBERED_PATTERN.match(stripped):
            indent = len(match.group(1)) // 4
            return ParsedLine('numbered', match.group(3), indent, line,
                            {'number': match.group(2)})

        # Check inline header (but not if it looks like a URL or time)
        if match := self.INLINE_HEADER_PATTERN.match(stripped):
            header, content = match.group(1), match.group(2)
            # Exclude false positives like "https:" or "10:30"
            if header.lower() not in self.URL_PREFIXES and not header.isdigit():
                return ParsedLine('inline_header', content, 0, line,
                                {'header_text': header})

        # Check table row (|col1|col2|col3|) - Deep Research often includes tables
        if self.TABLE_ROW_PATTERN.match(stripped):
            # Check if it's a separator row (|---|---|)
            if self.TABLE_SEPARATOR_PATTERN.match(stripped):
                return ParsedLine('table_separator', '', 0, line, {})
            # Parse cells
            cells = [c.strip() for c in stripped.strip('|').split('|')]
            return ParsedLine('table_row', stripped, 0, line, {'cells': cells})

        # Plain text fallback
        return ParsedLine('text', stripped.lstrip(), 0, line, {})


    def _same_block_type(self, block_type: str, parsed: ParsedLine) -> bool:
        """Check if a parsed line belongs to the same block type."""
        if block_type == 'paragraph' and parsed.type == 'text':
            return True
        if block_type == 'bullet_list' and parsed.type == 'bullet':
            return True
        if block_type == 'numbered_list' and parsed.type == 'numbered':
            return True
        if block_type == 'table' and parsed.type in ('table_row', 'table_separator'):
            return True
        return False

    def _get_block_type(self, parsed: ParsedLine) -> str:
        """Get the block type for a parsed line."""
        if parsed.type == 'text':
            return 'paragraph'
        if parsed.type == 'bullet':
            return 'bullet_list'
        if parsed.type == 'numbered':
            return 'numbered_list'
        if parsed.type in ('heading', 'subheading'):
            return 'heading'
        if parsed.type == 'inline_header':
            return 'paragraph'
        if parsed.type in ('table_row', 'table_separator'):
            return 'table'
        return 'paragraph'

    def parse_content(self, content: str) -> list[ContentBlock]:
        """
        Parse multi-line content into structured blocks.

        Groups consecutive lines of the same type into blocks.
        Detects sub-heading patterns (plain text followed by bullets).

        Args:
            content: Multi-line markdown content string

        Returns:
            List of ContentBlock objects
        """
        lines = content.split('\n')
        blocks: list[ContentBlock] = []
        current_block: ContentBlock | None = None

        i = 0
        while i < len(lines):
            line = lines[i]
            parsed = self.parse_line(line)

            # Skip empty lines but close current block
            if parsed.type == 'empty':
                if current_block and current_block.lines:
                    blocks.append(current_block)
                    current_block = None
                i += 1
                continue

            # Detect sub-heading: plain text followed by bullet
            if parsed.type == 'text' and i + 1 < len(lines):
                next_parsed = self.parse_line(lines[i + 1])
                if next_parsed.type == 'bullet':
                    # This text line is actually a sub-heading
                    parsed = ParsedLine(
                        'subheading',
                        parsed.content,
                        0,
                        parsed.raw,
                        {'detected': True}
                    )

            # Headings always start a new block
            if parsed.type in ('heading', 'subheading'):
                if current_block and current_block.lines:
                    blocks.append(current_block)
                blocks.append(ContentBlock('heading', [parsed], {'level': parsed.level}))
                current_block = None
                i += 1
                continue

            # Determine block type for this line
            block_type = self._get_block_type(parsed)

            # Start new block or continue existing
            if current_block is None:
                current_block = ContentBlock(block_type, [parsed], {})
            elif self._same_block_type(current_block.type, parsed):
                current_block.lines.append(parsed)
            else:
                # Different type, start new block
                blocks.append(current_block)
                current_block = ContentBlock(block_type, [parsed], {})

            i += 1

        # Don't forget the last block
        if current_block and current_block.lines:
            blocks.append(current_block)

        return blocks

    def parse_table_block(self, block: ContentBlock) -> dict:
        """
        Parse a table block into structured data.

        Args:
            block: ContentBlock of type 'table'

        Returns:
            Dict with 'headers' (list) and 'rows' (list of lists)
        """
        headers: list[str] = []
        rows: list[list[str]] = []

        for line in block.lines:
            if line.type == 'table_separator':
                continue  # Skip separator rows
            if line.type == 'table_row':
                cells = line.metadata.get('cells', [])
                if not headers:
                    # First row is headers
                    headers = cells
                else:
                    rows.append(cells)

        return {'headers': headers, 'rows': rows}

    def apply_inline_formatting(self, paragraph: Any, text: str) -> None:
        """
        Apply bold/italic formatting to text within a Word paragraph.

        Handles:
        - **bold** and __bold__ patterns
        - *italic* and _italic_ patterns (single markers)

        Args:
            paragraph: A python-docx Paragraph object
            text: The text containing markdown formatting
        """
        # Combined pattern for bold (must be processed first to avoid conflict with italic)
        # Process the text segment by segment

        # First, find all bold patterns
        bold_matches = list(self.BOLD_PATTERN.finditer(text))

        if not bold_matches:
            # No bold formatting, just add the text as-is
            paragraph.add_run(text)
            return

        last_end = 0
        for match in bold_matches:
            # Add text before the match
            if match.start() > last_end:
                paragraph.add_run(text[last_end:match.start()])

            # Add bold text (group 1 is **text**, group 2 is __text__)
            bold_text = match.group(1) or match.group(2)
            bold_run = paragraph.add_run(bold_text)
            bold_run.bold = True

            last_end = match.end()

        # Add remaining text after last match
        if last_end < len(text):
            paragraph.add_run(text[last_end:])

    def strip_markdown_formatting(self, text: str) -> str:
        """
        Remove markdown formatting from text, returning plain text.

        Useful for extracting clean text content.

        Args:
            text: Text with markdown formatting

        Returns:
            Plain text with formatting markers removed
        """
        # Remove bold markers
        result = self.BOLD_PATTERN.sub(r'\1\2', text)
        # Remove italic markers (be careful not to remove asterisks in bold)
        result = self.ITALIC_PATTERN.sub(r'\1\2', result)
        return result

    def extract_bold_segments(self, text: str) -> list[tuple[str, bool]]:
        """
        Extract text segments with their bold status.

        Useful for testing without requiring python-docx.

        Args:
            text: Text with markdown formatting

        Returns:
            List of (text, is_bold) tuples
        """
        segments: list[tuple[str, bool]] = []
        bold_matches = list(self.BOLD_PATTERN.finditer(text))

        if not bold_matches:
            return [(text, False)]

        last_end = 0
        for match in bold_matches:
            # Add text before the match
            if match.start() > last_end:
                segments.append((text[last_end:match.start()], False))

            # Add bold text
            bold_text = match.group(1) or match.group(2)
            segments.append((bold_text, True))

            last_end = match.end()

        # Add remaining text
        if last_end < len(text):
            segments.append((text[last_end:], False))

        return segments


class ArtifactDetector:
    """
    Detects unconverted markdown artifacts in document text.

    Scans for patterns that should have been converted but weren't,
    such as ## headings, **bold**, bullet markers at line starts, etc.
    """

    # Patterns that indicate unconverted markdown
    HEADING_ARTIFACT = re.compile(r'^#{1,6}\s+', re.MULTILINE)
    BOLD_ARTIFACT = re.compile(r'\*\*[^*]+\*\*|__[^_]+__')
    ITALIC_ARTIFACT = re.compile(r'(?<!\*)\*[^*\n]+\*(?!\*)|(?<!_)_[^_\n]+_(?!_)')
    BULLET_ARTIFACT = re.compile(r'^\s*[*\-•]\s{1,4}(?=[A-Za-z])', re.MULTILINE)

    def __init__(self):
        self.artifacts_found: list[dict] = []

    def scan_text(self, text: str, context: str = '') -> list[dict]:
        """
        Scan text for markdown artifacts.

        Args:
            text: Text to scan
            context: Optional context (e.g., paragraph location) for logging

        Returns:
            List of artifact dicts with 'type', 'match', 'context'
        """
        artifacts = []

        # Check for heading artifacts (## at line start)
        for match in self.HEADING_ARTIFACT.finditer(text):
            artifacts.append({
                'type': 'heading',
                'match': match.group().strip(),
                'context': context,
                'position': match.start()
            })

        # Check for bold artifacts (**text**)
        for match in self.BOLD_ARTIFACT.finditer(text):
            artifacts.append({
                'type': 'bold',
                'match': match.group(),
                'context': context,
                'position': match.start()
            })

        # Check for bullet artifacts at line start
        for match in self.BULLET_ARTIFACT.finditer(text):
            artifacts.append({
                'type': 'bullet',
                'match': match.group().strip(),
                'context': context,
                'position': match.start()
            })

        return artifacts

    def scan_document(self, document: Any) -> list[dict]:
        """
        Scan a python-docx Document for markdown artifacts.

        Args:
            document: A python-docx Document object

        Returns:
            List of artifact dicts found in the document
        """
        all_artifacts = []

        for i, para in enumerate(document.paragraphs):
            text = para.text
            if text:
                context = f"Paragraph {i + 1}"
                artifacts = self.scan_text(text, context)
                all_artifacts.extend(artifacts)

        # Also scan table cells
        for table_idx, table in enumerate(document.tables):
            for row_idx, row in enumerate(table.rows):
                for cell_idx, cell in enumerate(row.cells):
                    text = cell.text
                    if text:
                        context = f"Table {table_idx + 1}, Row {row_idx + 1}, Cell {cell_idx + 1}"
                        artifacts = self.scan_text(text, context)
                        all_artifacts.extend(artifacts)

        self.artifacts_found = all_artifacts
        return all_artifacts

    def has_artifacts(self, document: Any) -> bool:
        """Check if document has any markdown artifacts."""
        return len(self.scan_document(document)) > 0

    def get_artifact_summary(self) -> str:
        """Get a summary of artifacts found."""
        if not self.artifacts_found:
            return "No markdown artifacts found."

        summary_lines = [f"Found {len(self.artifacts_found)} markdown artifact(s):"]
        for artifact in self.artifacts_found[:10]:  # Limit to first 10
            summary_lines.append(
                f"  - {artifact['type']}: '{artifact['match']}' in {artifact['context']}"
            )

        if len(self.artifacts_found) > 10:
            summary_lines.append(f"  ... and {len(self.artifacts_found) - 10} more")

        return '\n'.join(summary_lines)
