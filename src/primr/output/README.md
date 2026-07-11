# Output Package

`primr.output` turns validated research content into durable deliverables and
artifact metadata. It owns formatting and shipping checks, not evidence
collection, model routing, or report-quality judgment.

## Concern map

| Area | Modules | Responsibility |
|------|---------|----------------|
| Final content contract | `final_artifact.py` | Canonical final sections, Markdown parsing, and normalization |
| Run output boundary | `output_utils.py` | Output paths, format conversion, and final file placement |
| Artifact shipping | `artifact_validation.py`, `artifact_inventory.py` | Deterministic validation gates plus bounded metadata and hash inventory |
| DOCX construction | `document_builder.py`, `markdown_parser.py`, `markdown_converter.py` | Markdown parsing and professional Word document rendering |
| Report assembly | `report_assembler.py`, `section_writer.py` | Structured report composition and section formatting |
| Citations | `citation_processor.py` | Citation normalization, numbering, and bibliography handling |
| Executive summaries | `executive_summary.py`, `executive_summary_generator.py` | Deterministic and premium summary structures |
| Layout and style | `style_engine.py`, `table_builder.py`, `content_pattern_detector.py`, `polish_elements.py` | Headings, tables, pattern-aware formatting, and executive polish elements |
| Output models | `models.py`, `templates.py`, `chapter_config.py` | Document data structures, report templates, and chapter configuration |
| Specialized artifacts | `skills_generator.py`, `qa_report_generator.py` | Legacy generated skill files and QA report rendering |

The package exports supported building blocks such as `DocumentBuilder`,
`MarkdownParser`, `ReportAssembler`, `StyleEngine`, and `TableBuilder` from
`primr.output`. Conversion itself is function- and builder-based; there is no
package-level converter class.

## Artifact flow

```text
research sections or final Markdown
        |
        v
canonical final-artifact representation
        |
        v
deterministic artifact validation
        |
        +-> Markdown and TXT
        +-> DOCX document builder
        +-> best-effort PDF when a local converter is available
        |
        v
artifact inventory with paths, sizes, hashes, and classifications
```

Artifact validation is a shipping boundary. Blocking defects can withhold a
polished deliverable while preserving diagnostics and source content for
repair. QA scores and claim-verification judgments are produced by `primr.qa`
and `primr.core`; output only renders or inventories their artifacts.

## Package boundaries

- Canonicalize content once before rendering multiple formats.
- Use safe output-path and filename helpers rather than constructing paths from
  untrusted company names.
- Keep Markdown, TXT, and DOCX content equivalent at the final artifact seam.
- Treat PDF as best effort because converter availability is platform-specific.
- Keep report-body content out of compact inventories and status resources.
- Skill-pack ZIP packaging belongs to `primr.skill_pack`, not this package.
