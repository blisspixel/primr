# Requirements Document

## Introduction

Primr has three research modes - this feature **enhances `--mode full`** without breaking existing modes:

| Mode | Current | After Enhancement |
|------|---------|-------------------|
| `--mode scrape` | Works fine | No change |
| `--mode deep` | Works fine | No change |
| `--mode full` | Broken (incomplete output) | **Enhanced with recursive architecture** |

The problem with `--mode full`: It uses `strategic_layer` prompt which skips foundational sections, then tries to programmatically merge results → incomplete, fragmented output.

The fix: Implement **Recursive Hierarchical Research Architecture** for `--mode full` to produce comprehensive 40+ page reports.

**Key insight from Gemini documentation:**
> "A single invocation of the Deep Research agent typically yields 1,500-2,000 words. To produce a comprehensive strategic document, the solution is a Recursive Hierarchical Research Architecture."

## Glossary

- **Master Architect**: Planning agent that decomposes the report into chapters
- **Research Nodes**: Parallel Deep Research tasks, one per chapter
- **File Search Store**: Gemini API feature to upload scraped data as context
- **Hierarchy of Truth**: Scraped data = baseline facts, web search = external context
- **Recursive Hierarchical Architecture**: Multi-chapter parallel research pattern

## Requirements

### Requirement 1

**User Story:** As a consultant, I want a comprehensive Strategic Company Overview that deeply covers all aspects of the company, so that I'm fully prepared for the engagement.

#### Acceptance Criteria

1. WHEN running `--mode full` THEN the system SHALL decompose the report into 8-10 substantive chapters
2. WHEN chapters are defined THEN the system SHALL run parallel Deep Research tasks for each chapter
3. WHEN all chapters complete THEN the system SHALL aggregate into a single comprehensive document
4. WHEN the report is generated THEN it SHALL contain 40+ pages of strategic intelligence

### Requirement 2

**User Story:** As a consultant, I want the report to cover both foundational company understanding AND strategic analysis in depth.

#### Acceptance Criteria

1. WHEN the report is generated THEN it SHALL include foundational chapters: Company Overview, Products & Services, Leadership & Culture, Financial Position
2. WHEN the report is generated THEN it SHALL include strategic chapters: Competitive Landscape, Industry Dynamics, SWOT Analysis, Risk Assessment, Strategic Recommendations
3. WHEN the report is generated THEN each chapter SHALL be 4-6 pages of substantive analysis (not bullet lists)

### Requirement 3

**User Story:** As a consultant, I want Deep Research to use scraped website data as the authoritative baseline for company facts.

#### Acceptance Criteria

1. WHEN Step 1 scraping completes THEN the system SHALL upload results to a File Search Store
2. WHEN Deep Research runs THEN each chapter task SHALL have access to the same File Search Store
3. WHEN context contains company-specific data THEN Deep Research SHALL use those figures as the baseline
4. WHEN context and web search conflict on company facts THEN Deep Research SHALL prefer context

### Requirement 4

**User Story:** As a user, I want the system to handle the complexity of parallel research gracefully.

#### Acceptance Criteria

1. WHEN running parallel research THEN the system SHALL limit concurrency to avoid rate limits (max 3 concurrent)
2. WHEN a chapter task fails THEN the system SHALL log the error and continue with other chapters
3. WHEN all chapters complete THEN the system SHALL aggregate with narrative smoothing between chapters

### Requirement 5

**User Story:** As a user, I want existing modes (`--mode scrape` and `--mode deep`) to continue working unchanged.

#### Acceptance Criteria

1. WHEN running `--mode scrape` THEN the system SHALL produce Company_Overview.docx using existing structured pipeline
2. WHEN running `--mode deep` THEN the system SHALL produce Strategic_Overview.docx using existing single Deep Research call
3. WHEN running either standalone mode THEN the behavior SHALL be identical to before this enhancement
