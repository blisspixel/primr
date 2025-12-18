# Requirements Document

## Introduction

This specification addresses critical failures in the current Deep Research report generation system. The current implementation attempts to run 10 parallel Deep Research API calls (one per chapter), which consistently fails due to API quota limits (429 errors), resulting in reports with ✗ marks for failed chapters, truncated content, and an unprofessional output. 

The correct architecture, per Google's Deep Research API guidance, is to use Stage 1 (Gemini Pro + scraping) to create comprehensive structured data, then pass that as context to a SINGLE Deep Research API call that produces the entire cohesive report. Deep Research is designed for autonomous multi-step research and can produce comprehensive 15,000+ word reports in a single invocation.

## Glossary

- **Stage 1 (Structured Research)**: The initial research phase using Gemini 2.0 Flash/Pro and web scraping to collect company data into structured sections
- **Stage 2 (Deep Research)**: The Google Deep Research API (`deep-research-pro-preview-12-2025`) that performs autonomous multi-step web research
- **File Search Store**: Google's managed RAG system for providing context documents to the Deep Research agent
- **Interactions API**: Google's stateful API for long-running agentic tasks
- **Cohesive Report**: A single, unified document with consistent narrative flow (not concatenated independent chapters)

## Requirements

### Requirement 1

**User Story:** As a consultant, I want the Deep Research report to be a single cohesive document, so that I receive a professional deliverable without failed chapter markers or truncated content.

#### Acceptance Criteria

1. WHEN Deep Research mode is executed THEN the System SHALL produce a complete report without any failure markers (✗) in the output
2. WHEN the Deep Research API encounters quota limits THEN the System SHALL retry with exponential backoff up to 5 attempts before failing the entire operation
3. WHEN a report is generated THEN the System SHALL produce a unified narrative document rather than concatenated independent sections
4. IF the Deep Research API fails after all retries THEN the System SHALL clearly communicate the failure and suggest running in scrape-only mode instead

### Requirement 2

**User Story:** As a user, I want Stage 1 structured research to feed into Stage 2 Deep Research as context, so that the Deep Research agent has accurate company baseline data.

#### Acceptance Criteria

1. WHEN Stage 1 completes THEN the System SHALL upload the structured research output to a File Search Store
2. WHEN Stage 2 begins THEN the System SHALL reference the File Search Store in the Deep Research prompt with explicit hierarchy of truth instructions
3. WHEN the Deep Research agent generates content THEN the System SHALL instruct it to use File Search data as authoritative for company facts and web search for external context
4. WHEN Stage 2 completes THEN the System SHALL delete the temporary File Search Store to prevent data leakage

### Requirement 3

**User Story:** As a user, I want a single Deep Research API call to produce the entire report, so that I avoid quota exhaustion from parallel chapter requests.

#### Acceptance Criteria

1. WHEN Deep Research mode executes THEN the System SHALL make exactly one Deep Research API call per report (not one per chapter)
2. WHEN constructing the Deep Research prompt THEN the System SHALL include the complete report structure (all 10 chapters) in a single comprehensive prompt
3. WHEN the Deep Research agent runs THEN the System SHALL allow up to 60 minutes for completion (the documented maximum for complex research)
4. WHEN polling for completion THEN the System SHALL use adaptive intervals (5s initially, increasing to 30s for long-running tasks)

### Requirement 4

**User Story:** As a user, I want clear progress feedback during the long-running Deep Research operation, so that I know the system is working.

#### Acceptance Criteria

1. WHILE Deep Research is running THEN the System SHALL display status updates at regular intervals
2. WHEN the agent's thinking summaries are available THEN the System SHALL stream them to the user interface
3. WHEN the operation exceeds 5 minutes THEN the System SHALL display estimated time remaining based on typical completion times
4. IF the operation times out THEN the System SHALL provide a clear error message with the interaction ID for debugging

### Requirement 5

**User Story:** As a user, I want the report output to be properly formatted without artifacts from failed operations, so that I can use it directly for client work.

#### Acceptance Criteria

1. WHEN generating the Table of Contents THEN the System SHALL NOT include checkmarks (✓) or X marks (✗) for chapter status
2. WHEN the report is complete THEN the System SHALL include all 10 standard chapters with content
3. WHEN citations are present THEN the System SHALL format them consistently using the configured citation style
4. WHEN the report is saved THEN the System SHALL produce clean Markdown, DOCX, and PDF outputs without debug artifacts

### Requirement 6

**User Story:** As a developer, I want the Deep Research prompt to use consulting frameworks, so that the output matches professional strategic advisory standards.

#### Acceptance Criteria

1. WHEN constructing the Deep Research prompt THEN the System SHALL inject the consulting persona ("Senior Strategy Consultant at a top-tier firm")
2. WHEN specifying output structure THEN the System SHALL require SWOT analysis, competitive landscape, and strategic recommendations sections
3. WHEN setting epistemic standards THEN the System SHALL require citations for facts and explicit labeling of inferences
4. WHEN formatting instructions are provided THEN the System SHALL prohibit excessive bullet lists and require narrative prose

### Requirement 7

**User Story:** As a user, I want the option to run Stage 1 only without Deep Research, so that I can get results quickly when Deep Research quota is exhausted.

#### Acceptance Criteria

1. WHEN the user specifies `--mode scrape` THEN the System SHALL execute only Stage 1 and produce a report from structured data
2. WHEN Deep Research fails due to quota THEN the System SHALL suggest the scrape-only mode as an alternative
3. WHEN running scrape-only mode THEN the System SHALL produce a complete report using the Stage 1 data with a different report template
4. WHEN comparing modes THEN the System SHALL document that scrape mode is faster (20-25 min) while deep mode provides broader market context (30-40 min)
