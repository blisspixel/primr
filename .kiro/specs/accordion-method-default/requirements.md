# Requirements Document

## Introduction

This specification fixes the Deep Research stage to deliver on its intended purpose: **30+ page Strategic Company Overviews** instead of the ~12 pages that a single Deep Research call produces.

**The Problem:** Google's Deep Research API (December 2025) produces ~8-12 pages maximum per call, regardless of prompt instructions. Our `--mode full` was supposed to produce comprehensive reports but hits this API ceiling.

**The Fix:** The "Accordion Method" - a simple architectural change:
- Deep Research gathers facts (as "Lead Researcher") → ~12 page dossier
- Gemini Pro writes each section one-by-one (as "Writer") → expands to 30+ pages
- Result: Same report structure, same formatting, but with the depth that was always intended

**What stays the same:** Everything in the README - CLI, output formats, section structure, modes, flags.

**What changes:** Reports will have substantive content in each section instead of compressed summaries.

## Glossary

- **Accordion Method**: 1 Deep Research call (research) + N Gemini Pro calls (writing) to produce comprehensive reports
- **Stage 1 (Scrape + Gemini Pro)**: Website scraping + Google Search + section-by-section AI analysis
- **Stage 2 (Research Dossier)**: Deep Research API call that gathers external context as "Lead Researcher"
- **Stage 3 (Section Elaboration)**: Gemini Pro writes each section one-by-one with context continuity
- **Strategic Company Overview**: The primary 30+ page research deliverable

## Requirements

### Requirement 1

**User Story:** As a consultant, I want the default `primr` command to produce a comprehensive 30+ page Strategic Company Overview, so that I have thorough research for client preparation.

#### Acceptance Criteria

1. WHEN a user runs `primr "Company" https://company.com` without flags THEN the System SHALL execute the full Accordion Method pipeline
2. WHEN the pipeline completes successfully THEN the System SHALL produce a Strategic Company Overview with substantive content in each section
3. WHEN the report is generated THEN the System SHALL include all 10 standard sections with detailed analysis (not compressed summaries)
4. IF any phase fails THEN the System SHALL provide clear error messages and suggest fallback modes

### Requirement 2

**User Story:** As a consultant, I want Stage 1 to create comprehensive baseline facts from the company website, so that Deep Research has accurate ground truth data.

#### Acceptance Criteria

1. WHEN Stage 1 executes THEN the System SHALL scrape the company website using the 4-tier scraping engine
2. WHEN Stage 1 executes THEN the System SHALL perform Google Search for additional public information
3. WHEN Stage 1 completes THEN the System SHALL generate section-by-section analysis using Gemini Pro
4. WHEN Stage 1 completes THEN the System SHALL produce a structured context file for upload to File Search Store

### Requirement 3

**User Story:** As a consultant, I want Stage 2 to leverage all available context, so that Deep Research produces a rich research dossier.

#### Acceptance Criteria

1. WHEN Stage 2 begins THEN the System SHALL upload Stage 1 context to a File Search Store
2. WHEN the Deep Research prompt is constructed THEN the System SHALL instruct the agent to act as "Lead Researcher" gathering facts (not writing the final report)
3. WHEN Deep Research executes THEN the System SHALL capture the interaction_id for use in Stage 3
4. WHEN Stage 2 completes THEN the System SHALL produce a research dossier with raw facts, data, and citations

### Requirement 4

**User Story:** As a consultant, I want Stage 3 to write each section with context continuity, so that the final report has consistent narrative flow and substantive depth.

#### Acceptance Criteria

1. WHEN Stage 3 begins THEN the System SHALL use Gemini Pro to write each section sequentially
2. WHEN writing each section THEN the System SHALL pass the research dossier as source material
3. WHEN writing each section THEN the System SHALL pass summaries of previously written sections for context continuity
4. WHEN writing sections THEN the System SHALL execute sequentially with short delays between calls
5. IF a section fails THEN the System SHALL retry up to 2 times before skipping

### Requirement 5

**User Story:** As a consultant, I want the AI Strategy report to be generated after the Strategic Company Overview, so that I have both research and recommendations.

#### Acceptance Criteria

1. WHEN the Strategic Company Overview completes successfully THEN the System SHALL generate the AI Strategy report
2. WHEN generating AI Strategy THEN the System SHALL use the completed Strategic Company Overview as context
3. WHEN generating AI Strategy THEN the System SHALL apply the specified cloud vendor (azure/aws/gcp/agnostic)
4. WHEN the user specifies `--no-ai-strategy` THEN the System SHALL skip AI Strategy generation

### Requirement 6

**User Story:** As a user, I want clear progress feedback during the long-running pipeline, so that I know the system is working.

#### Acceptance Criteria

1. WHEN each phase begins THEN the System SHALL display a phase banner
2. WHEN each section is written THEN the System SHALL display the section name and word count
3. WHEN the pipeline completes THEN the System SHALL display total duration and output file locations

### Requirement 7

**User Story:** As a user, I want flags to run partial pipelines, so that I can skip expensive stages when needed.

#### Acceptance Criteria

1. WHEN the user specifies `--mode scrape` THEN the System SHALL execute only Stage 1 and produce a report from that data
2. WHEN the user specifies `--mode deep` THEN the System SHALL execute only a single Deep Research call
3. WHEN the user specifies `--skip-elaboration` THEN the System SHALL skip Stage 3 and use the Deep Research dossier directly

### Requirement 8

**User Story:** As a developer, I want the section definitions to be configurable, so that the report structure can evolve without code changes.

#### Acceptance Criteria

1. WHEN sections are defined THEN the System SHALL load section definitions from YAML configuration
2. WHEN section config specifies instructions THEN the System SHALL include those instructions in the section writing prompt

### Requirement 9

**User Story:** As a user, I want the system to handle API rate limits gracefully, so that long-running research completes successfully.

#### Acceptance Criteria

1. WHEN a 429 rate limit error occurs THEN the System SHALL wait with exponential backoff before retrying
2. WHEN consecutive failures exceed threshold (3) THEN the System SHALL stop and return partial results

### Requirement 10

**User Story:** As a developer, I want to test the Accordion Method independently, so that I can validate it works before integrating with the full pipeline.

#### Acceptance Criteria

1. WHEN testing the Accordion Method THEN the System SHALL support a standalone test mode with any research topic
2. WHEN the test completes THEN the System SHALL report word count, page estimate, and section completion status
3. WHEN the test produces output THEN the System SHALL save the result to a file for manual review

