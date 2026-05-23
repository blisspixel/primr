"""Coverage tests for primr.output.markdown_converter."""

from __future__ import annotations

from docx import Document

from primr.output.markdown_converter import (
    add_hyperlink,
    markdown_to_docx,
    parse_inline_markdown,
    render_section_content,
    render_table,
    sanitize_text,
    strip_heading_markers,
    strip_markdown_header_block,
)


# --------------------------------------------------------------------------- #
# sanitize_text
# --------------------------------------------------------------------------- #
def test_sanitize_text_empty():
    assert sanitize_text("") == ""


def test_sanitize_text_removes_control_chars():
    out = sanitize_text("a\x00b\x07c")
    assert out == "abc"


def test_sanitize_text_keeps_tab_newline():
    out = sanitize_text("a\tb\nc\rd")
    assert out == "a\tb\nc\rd"


# --------------------------------------------------------------------------- #
# add_hyperlink
# --------------------------------------------------------------------------- #
def test_add_hyperlink_basic():
    doc = Document()
    para = doc.add_paragraph()
    add_hyperlink(para, "Example", "https://example.com")
    # The hyperlink element should be appended to the paragraph XML.
    xml = para._p.xml
    assert "hyperlink" in xml
    assert "Example" in xml


def test_add_hyperlink_empty_skips():
    doc = Document()
    para = doc.add_paragraph()
    add_hyperlink(para, "", "https://example.com")
    assert "hyperlink" not in para._p.xml


# --------------------------------------------------------------------------- #
# parse_inline_markdown
# --------------------------------------------------------------------------- #
def test_parse_inline_markdown_empty():
    doc = Document()
    para = doc.add_paragraph()
    parse_inline_markdown(para, "")
    assert len(para.runs) == 0


def test_parse_inline_markdown_bold():
    doc = Document()
    para = doc.add_paragraph()
    parse_inline_markdown(para, "**bold**")
    assert para.runs[0].font.bold is True
    assert para.runs[0].text == "bold"


def test_parse_inline_markdown_italic():
    doc = Document()
    para = doc.add_paragraph()
    parse_inline_markdown(para, "*ital*")
    assert para.runs[0].font.italic is True


def test_parse_inline_markdown_code():
    doc = Document()
    para = doc.add_paragraph()
    parse_inline_markdown(para, "`code`")
    assert para.runs[0].text == "code"
    assert para.runs[0].font.name == "Consolas"


def test_parse_inline_markdown_link():
    doc = Document()
    para = doc.add_paragraph()
    parse_inline_markdown(para, "[text](https://example.com)")
    assert "hyperlink" in para._p.xml


def test_parse_inline_markdown_plain_mixed():
    doc = Document()
    para = doc.add_paragraph()
    parse_inline_markdown(para, "plain **bold** end")
    texts = [r.text for r in para.runs]
    assert "plain " in texts
    assert "bold" in texts
    assert " end" in texts


# --------------------------------------------------------------------------- #
# render_table
# --------------------------------------------------------------------------- #
def test_render_table_too_few_lines():
    doc = Document()
    render_table(doc, ["| only one |"])
    assert len(doc.tables) == 0


def test_render_table_basic():
    doc = Document()
    # Separator rows for a single-column table (no inner pipe) are detected/skipped.
    lines = [
        "| Name |",
        "|------|",
        "| Foo |",
        "| Bar |",
    ]
    render_table(doc, lines)
    assert len(doc.tables) == 1
    table = doc.tables[0]
    assert len(table.rows) == 3  # header + 2 data rows (separator skipped)


def test_render_table_multicolumn_keeps_all_rows():
    doc = Document()
    # The separator regex does not match multi-column separators (inner pipes),
    # so all four lines are rendered as rows.
    lines = [
        "| Name | Value |",
        "|------|-------|",
        "| Foo | 1 |",
        "| Bar | 2 |",
    ]
    render_table(doc, lines)
    assert len(doc.tables) == 1
    assert len(doc.tables[0].rows) == 4


def test_render_table_only_separator_returns_empty():
    doc = Document()
    # Single-column separator lines match the separator regex and are skipped,
    # leaving no data rows -> no table created.
    render_table(doc, ["|---|", "|---|"])
    assert len(doc.tables) == 0


# --------------------------------------------------------------------------- #
# strip_heading_markers
# --------------------------------------------------------------------------- #
def test_strip_heading_markers_removes_formatting():
    assert strip_heading_markers("**Bold** *ital* `code`") == "Bold ital code"


def test_strip_heading_markers_empty():
    assert strip_heading_markers("") == ""
    assert strip_heading_markers("\x00") == ""


# --------------------------------------------------------------------------- #
# strip_markdown_header_block
# --------------------------------------------------------------------------- #
def test_strip_markdown_header_block_empty():
    assert strip_markdown_header_block("") == ""


def test_strip_markdown_header_block_removes_header():
    md = "# Title\n\n**Prepared by:** X\n**Date:** Y\n\n---\n\nBody content here"
    out = strip_markdown_header_block(md)
    assert "Title" not in out
    assert "Body content here" in out


def test_strip_markdown_header_block_no_heading_returns_same():
    md = "Just body text\nMore text"
    out = strip_markdown_header_block(md)
    assert "Just body text" in out


# --------------------------------------------------------------------------- #
# markdown_to_docx
# --------------------------------------------------------------------------- #
def test_markdown_to_docx_full(tmp_path):
    md = (
        "# Doc Title\n\n"
        "## Section A\n"
        "### Sub\n"
        "#### Minor\n"
        "Some paragraph text.\n\n"
        "- bullet one\n"
        "* bullet two\n"
        "1. numbered one\n"
        "2) numbered two\n\n"
        "> a quote line\n"
        "> second quote line\n\n"
        "---\n\n"
        "| H1 | H2 |\n"
        "|----|----|\n"
        "| a | b |\n"
    )
    out = tmp_path / "out.docx"
    result = markdown_to_docx(md, out, title="My Title", subtitle="My Subtitle")
    assert result == out
    assert out.exists()


def test_markdown_to_docx_table_at_end(tmp_path):
    md = "Intro\n\n| A | B |\n|---|---|\n| 1 | 2 |"
    out = tmp_path / "tbl.docx"
    markdown_to_docx(md, out, title=None)
    assert out.exists()


def test_markdown_to_docx_no_title(tmp_path):
    md = "## Heading\n\nbody"
    out = tmp_path / "nt.docx"
    markdown_to_docx(md, out)
    assert out.exists()


# --------------------------------------------------------------------------- #
# render_section_content
# --------------------------------------------------------------------------- #
def test_render_section_content_all_elements():
    doc = Document()
    content = (
        "## Heading\n"
        "### Sub\n"
        "#### Minor\n"
        "paragraph\n\n"
        "- bullet\n"
        "* star bullet\n"
        "1. num\n"
        "> quote\n"
        "---\n"
        "| X | Y |\n"
        "|---|---|\n"
        "| 1 | 2 |\n"
    )
    render_section_content(doc, content)
    assert len(doc.tables) == 1
    assert len(doc.paragraphs) > 0


# --------------------------------------------------------------------------- #
# table-detection content loss (regression)
# --------------------------------------------------------------------------- #
def test_single_pipe_prose_not_dropped():
    """A prose line containing a single '|' but no table separator must be
    rendered as a paragraph, not silently dropped as a degenerate table."""
    doc = Document()
    render_section_content(doc, "Strengths | Weaknesses\n\nFollowing paragraph text")
    texts = "\n".join(p.text for p in doc.paragraphs)
    assert "Strengths" in texts
    assert "Weaknesses" in texts
    assert "Following paragraph text" in texts


def test_real_table_still_renders_as_table():
    """A genuine markdown table (with a |---| separator row) renders as a DOCX table."""
    doc = Document()
    render_section_content(doc, "| A | B |\n| --- | --- |\n| 1 | 2 |")
    assert len(doc.tables) == 1
