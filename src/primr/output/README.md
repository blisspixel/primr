# Output Module

This module handles report generation, converting research results into professional documents.

## Components

### Document Builder (`document_builder.py`)

Main interface for generating DOCX documents:

```python
from primr.output import DocumentBuilder
from pathlib import Path

builder = DocumentBuilder()
doc_path = builder.build_docx(
    sections=result.section_results,
    company_name="Tesla",
    output_dir=Path("output")
)
```

### Report Assembler (`report_assembler.py`)

Assembles sections into a complete report structure:

```python
from primr.output import ReportAssembler

assembler = ReportAssembler()
report = assembler.assemble(sections, company_name)
```

### Citation Processor (`citation_processor.py`)

Handles citation formatting and bibliography generation:

```python
from primr.output import CitationProcessor

processor = CitationProcessor(style="numbered")
processed_content = processor.process(content, citations)
```

Citation styles:
- `numbered`: [1] style with bibliography
- `inline`: URLs preserved in text
- `sidecar`: Separate sources file

### Markdown Conversion

- `markdown_parser.py`: Parses markdown into structured elements
- `markdown_converter.py`: Converts markdown to DOCX formatting

```python
from primr.output import MarkdownConverter

converter = MarkdownConverter()
converter.convert_to_docx(markdown_content, document)
```

### Executive Summary (`executive_summary.py`, `executive_summary_generator.py`)

Generates the "so what" summary at the beginning of reports:

```python
from primr.output import ExecutiveSummaryGenerator

generator = ExecutiveSummaryGenerator()
summary = generator.generate(sections, company_name)
```

### Styling (`style_engine.py`)

Applies consistent styling to documents:

```python
from primr.output import StyleEngine

engine = StyleEngine()
engine.apply_heading_style(paragraph, level=1)
engine.apply_body_style(paragraph)
```

### Tables (`table_builder.py`)

Builds formatted tables in documents:

```python
from primr.output import TableBuilder

builder = TableBuilder()
table = builder.build_comparison_table(data, headers)
```

## Additional Components

- `chapter_config.py`: Chapter structure configuration
- `content_pattern_detector.py`: Detects content patterns for formatting
- `models.py`: Output data structures
- `output_utils.py`: Utility functions
- `polish_elements.py`: Final polish and cleanup
- `section_writer.py`: Section formatting
- `templates.py`: Report templates

## Output Formats

### TXT
Plain text output for quick review.

### DOCX
Professional Word document with:
- Styled headings
- Formatted tables
- Citation bibliography
- Table of contents (for Complete Mode)

### PDF
Generated from DOCX using Microsoft Word (Windows) or alternative converters.

### ZIP
Archive containing all output files for a research run.

## Key Patterns

### Section-Based Structure

Output is organized by sections:

```python
sections = {
    "company_overview": "Content...",
    "detailed_products_services": "Content...",
    "leadership": "Content...",
    # ...
}
```

### Template System

Reports use configurable templates:

```python
from primr.output.templates import get_template

template = get_template("company_overview")
content = template.render(data)
```

### Formatting Rules

All output follows consistent rules:
- No em-dashes (use commas or periods)
- No emojis
- Single-level bullets only
- Professional tone

## Configuration

Output behavior is configured via:

- `PathConfig`: Output directories
- Citation style: Command-line flag
- Platform: For AI strategy sections (`--platform`)
