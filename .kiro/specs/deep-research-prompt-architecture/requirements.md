# Requirements Document

## Introduction

This specification defines an internal refactor to externalize Deep Research prompts from hardcoded Python strings to structured, versionable YAML configuration files. The CLI behavior and user experience remain unchanged - this is about maintainability and extensibility.

**What already works (no changes):**
- `primr "Company" https://company.com` generates comprehensive reports
- `--mode deep` / `--mode full` uses Deep Research API
- `--cloud-vendor azure/aws/gcp` generates AI strategy with vendor context
- `--no-ai-strategy` skips AI strategy generation
- Produces DOCX/PDF outputs

**What this spec addresses:**
- Critical prompts are hardcoded in `deep_research.py`: `_build_strategic_layer_prompt()`, `ConsultingPromptBuilder.build_comprehensive_prompt()`, and various epistemic rules
- This creates maintenance burden and inconsistent prompt engineering
- Blocks the roadmap goal of extensible strategy modules (v1.2.6)

**The solution:**
- Externalize ALL Deep Research prompts to YAML files
- Create shared components (epistemic rules, formatting, personas) for consistency
- Plan for future `--strategy` flag extensibility (cloud, data, security modules)
- Optimize prompts for comprehensive, long-form Deep Research output (20-70 pages per report)

## Glossary

- **Deep_Research_Prompt_System**: The unified system for loading, composing, and building prompts from YAML configurations
- **Prompt_Config**: A YAML file defining sections, epistemic rules, formatting, and persona for a specific prompt type
- **Strategy_Module**: A pluggable YAML configuration that generates a specific type of strategic analysis (AI, cloud, data, etc.)
- **Shared_Components**: Reusable YAML fragments for epistemic rules, formatting standards, and consulting personas
- **Prompt_Composer**: The Python component that assembles final prompts from YAML configurations and runtime context
- **Section_Spec**: A YAML definition of a report section including purpose, coverage requirements, and depth guidance
- **Epistemic_Rules**: Standards for distinguishing facts, inferences, and hypotheses in generated content
- **Consulting_Persona**: The voice and perspective injected into prompts (e.g., "Senior Strategy Consultant")

## Requirements

### Requirement 1

**User Story:** As a developer, I want all Deep Research prompts externalized to YAML files, so that prompt engineering is separated from code and can be iterated independently.

#### Acceptance Criteria

1. WHEN the Deep_Research_Prompt_System loads a prompt THEN the system SHALL read all prompt content from YAML files rather than hardcoded Python strings
2. WHEN the `_build_strategic_layer_prompt()` function is called THEN the system SHALL load the strategic layer configuration from `strategic_layer.yaml`
3. WHEN the `ConsultingPromptBuilder.build_comprehensive_prompt()` method is called THEN the system SHALL delegate to the unified Prompt_Composer using `company_overview.yaml`
4. WHEN a prompt YAML file is modified THEN the system SHALL use the updated content without requiring code changes
5. WHEN a prompt YAML file is missing or malformed THEN the system SHALL raise a descriptive error identifying the file and issue

### Requirement 2

**User Story:** As a developer, I want shared prompt components (epistemic rules, formatting, personas) in separate YAML files, so that consistency is maintained across all prompts without duplication.

#### Acceptance Criteria

1. WHEN the Prompt_Composer builds any prompt THEN the system SHALL load epistemic rules from `shared/epistemic_rules.yaml`
2. WHEN the Prompt_Composer builds any prompt THEN the system SHALL load formatting standards from `shared/formatting.yaml`
3. WHEN the Prompt_Composer builds any prompt THEN the system SHALL load the consulting persona from `shared/personas.yaml`
4. WHEN a shared component is updated THEN the system SHALL apply the change to all prompts that reference it
5. WHEN a prompt YAML overrides a shared component THEN the system SHALL use the prompt-specific value for that prompt only

### Requirement 3

**User Story:** As a user, I want the Strategic Company Overview to be comprehensive (~30-40 pages), so that I have consulting-grade research for client preparation.

#### Acceptance Criteria

1. WHEN Deep Research generates a Strategic Company Overview THEN the output SHALL contain all sections defined in `company_overview.yaml` (minimum 20 sections across 5 parts)
2. WHEN a section is generated THEN the content SHALL meet the depth requirements specified in the Section_Spec (substantive analysis, not surface summaries)
3. WHEN the report is complete THEN the word count SHALL be approximately 15,000-20,000 words (30-40 pages)
4. WHEN tables are appropriate THEN the system SHALL include data tables for financials, competitors, timelines, and comparisons
5. WHEN the report is generated THEN the system SHALL include all five parts: Foundational Understanding, Market Context, Strategic Analysis, Hypotheses and Questions, Strategic Frameworks

### Requirement 4

**User Story:** As a user, I want strategy modules (AI Strategy, Cloud Migration, etc.) to be pluggable YAML configurations, so that I can generate different strategic analyses from the same company research.

#### Acceptance Criteria

1. WHEN the user specifies `--strategy ai` THEN the system SHALL load and use `strategies/ai_strategy.yaml` to generate an AI Strategy document
2. WHEN the user specifies `--strategy cloud` THEN the system SHALL load and use `strategies/cloud_migration.yaml` to generate a Cloud Migration assessment
3. WHEN the user specifies multiple strategies `--strategy ai,cloud` THEN the system SHALL generate separate documents for each strategy module
4. WHEN the user specifies `--no-strategy` THEN the system SHALL generate only the Strategic Company Overview without any strategy modules
5. WHEN the user runs `primr --list-strategies` THEN the system SHALL display all available strategy modules from the `strategies/` directory
6. WHEN a strategy module defines data_sources THEN the system SHALL upload the associated files to File Search Store as context for Deep Research

### Requirement 5

**User Story:** As a user, I want the default behavior to produce both Strategic Company Overview and AI Strategy, so that a single command gives me comprehensive research output.

#### Acceptance Criteria

1. WHEN the user runs `primr "Company" https://company.com` without strategy flags THEN the system SHALL generate both Strategic Company Overview and AI Strategy documents
2. WHEN the user specifies `--cloud-vendor azure` THEN the AI Strategy SHALL use Azure-specific guidance from the vendor configuration AND upload Azure vendor research files as context
3. WHEN both documents are generated THEN the system SHALL produce separate DOCX files for each (Company_Strategic_Overview.docx and Company_AI_Strategy.docx)
4. WHEN the AI Strategy is generated THEN the system SHALL use the Strategic Company Overview as context input
5. WHEN the total generation completes THEN each document SHALL be substantial (Strategic Overview: 20-70 pages, AI Strategy: 15-30 pages)

### Requirement 6

**User Story:** As a developer, I want the prompt YAML schema to support rich section definitions, so that each section has clear purpose, coverage requirements, and depth guidance.

#### Acceptance Criteria

1. WHEN a Section_Spec is defined in YAML THEN the schema SHALL support: id, name, part, purpose, covers (list), depth, and optional subsections
2. WHEN the Prompt_Composer builds a section THEN the system SHALL include the purpose statement explaining why this section matters
3. WHEN the Prompt_Composer builds a section THEN the system SHALL include all coverage items as explicit requirements
4. WHEN the Prompt_Composer builds a section THEN the system SHALL include depth guidance specifying the expected level of detail
5. WHEN a section has subsections THEN the system SHALL render them with appropriate heading hierarchy (H2 for sections, H3 for subsections)

### Requirement 7

**User Story:** As a user, I want consistent epistemic standards across all generated content, so that facts, inferences, and hypotheses are clearly distinguished.

#### Acceptance Criteria

1. WHEN any prompt is built THEN the system SHALL include the epistemic rule requiring distinction between facts (with citations), inferences (labeled), and hypotheses (to validate)
2. WHEN any prompt is built THEN the system SHALL include the epistemic rule for framing risks as "areas to explore" not definitive threats
3. WHEN any prompt is built THEN the system SHALL include the epistemic rule requiring hedging language ("appears to", "worth exploring", "we'd want to validate")
4. WHEN any prompt is built THEN the system SHALL include the transformation rule for rewriting inevitability statements as scenario comparisons
5. WHEN the generated content contains strong claims THEN the content SHALL treat them as working hypotheses unless explicitly supported by cited sources

### Requirement 8

**User Story:** As a user, I want consistent formatting standards across all generated content, so that reports are clean and professional without manual cleanup.

#### Acceptance Criteria

1. WHEN any prompt is built THEN the system SHALL include formatting rules prohibiting em-dashes and en-dashes
2. WHEN any prompt is built THEN the system SHALL include formatting rules requiring single-level bullets only (no nested hierarchies)
3. WHEN any prompt is built THEN the system SHALL include formatting rules requiring full paragraphs with evidence (not bullet-point summaries)
4. WHEN any prompt is built THEN the system SHALL include formatting rules for citation style ([cite: X, Y, Z] format)
5. WHEN any prompt is built THEN the system SHALL include formatting rules requiring tables for financials, competitors, and timelines

### Requirement 9

**User Story:** As a developer, I want the Prompt_Composer to support variable substitution, so that company name, website, date, and other context can be injected into prompts.

#### Acceptance Criteria

1. WHEN the Prompt_Composer builds a prompt THEN the system SHALL replace `{company_name}` placeholders with the actual company name
2. WHEN the Prompt_Composer builds a prompt THEN the system SHALL replace `{website_url}` placeholders with the actual website URL
3. WHEN the Prompt_Composer builds a prompt THEN the system SHALL replace `{current_date}` placeholders with the current date in appropriate format
4. WHEN the Prompt_Composer builds a prompt THEN the system SHALL replace `{cloud_vendor}` placeholders with the specified vendor name
5. WHEN a placeholder has no value provided THEN the system SHALL either use a sensible default or omit the placeholder section entirely

### Requirement 10

**User Story:** As a developer, I want the prompt architecture to support the two-stage research pipeline, so that Stage 1 context can inform Stage 2 Deep Research.

#### Acceptance Criteria

1. WHEN Stage 2 Deep Research begins THEN the Prompt_Composer SHALL include instructions for using File Search Store context as authoritative baseline
2. WHEN Stage 2 Deep Research begins THEN the Prompt_Composer SHALL include hierarchy of truth instructions (internal data > web search for company facts)
3. WHEN the strategic layer prompt is built THEN the system SHALL explicitly instruct not to repeat foundational information from Stage 1
4. WHEN context is available THEN the prompt SHALL reference it with instructions like "You have access to initial research findings that cover the basics"
5. WHEN no Stage 1 context is available THEN the prompt SHALL generate a complete standalone report without context dependencies

### Requirement 11

**User Story:** As a user, I want the ability to add custom strategy modules by creating YAML files, so that I can extend Primr for my specific consulting needs.

#### Acceptance Criteria

1. WHEN a new YAML file is added to `strategies/` directory THEN the system SHALL automatically discover and make it available via `--strategy` flag
2. WHEN a custom strategy module is loaded THEN the system SHALL validate it against the Strategy_Module schema
3. WHEN a custom strategy module is used THEN the system SHALL apply the same shared components (epistemic rules, formatting) as built-in modules
4. WHEN `primr --list-strategies` is run THEN the system SHALL include both built-in and custom strategy modules in the output
5. WHEN a custom strategy module has errors THEN the system SHALL provide clear validation messages identifying the issues

### Requirement 12

**User Story:** As a developer, I want the prompt YAML files to be self-documenting, so that prompt engineers can understand and modify them without reading code.

#### Acceptance Criteria

1. WHEN a prompt YAML file is created THEN the file SHALL include a header comment explaining its purpose and usage
2. WHEN a prompt YAML file defines sections THEN each section SHALL have a clear purpose field explaining why it exists
3. WHEN a prompt YAML file uses shared components THEN the file SHALL document which shared files it depends on
4. WHEN the prompt architecture is documented THEN the documentation SHALL include example YAML for creating new strategy modules
5. WHEN prompt YAML files are version controlled THEN changes SHALL be reviewable as clear diffs showing prompt evolution

### Requirement 13

**User Story:** As a user, I want strategy modules to have associated data sources, so that the Deep Research agent has current, relevant context for generating accurate recommendations.

#### Acceptance Criteria

1. WHEN a strategy module YAML defines data_sources THEN the system SHALL recognize and load the associated file paths
2. WHEN a data source specifies a vendor filter THEN the system SHALL only include that file when the matching `--cloud-vendor` is specified
3. WHEN data source files exist THEN the system SHALL upload them to File Search Store before executing the Deep Research API call
4. WHEN a required data source file is missing THEN the system SHALL warn the user but continue with available sources
5. WHEN the Deep Research prompt is built THEN the system SHALL include instructions to use the data source files as authoritative context

</content>
</invoke>