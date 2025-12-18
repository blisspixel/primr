# Requirements Document

## Introduction

This specification defines enhancements to transform the Company Researcher's one-time report output from a good automated report into a consulting-tier deliverable that rivals McKinsey, BCG, or Bain quality. The core product is a deep-dive company analysis snapshot - a single, comprehensive research report that provides exceptional value at a specific point in time.

The goal is to produce reports that executives would pay $50K+ for from a top consulting firm.

## Glossary

- **Report_Generator**: The system component that produces the final company research document
- **Research_Agent**: The orchestrator that coordinates scraping, analysis, and report generation
- **Section_Analyzer**: Component that generates individual report sections with AI
- **Quality_Grader**: Component that evaluates and refines section quality
- **Executive_Summary**: A C-suite ready 1-page overview of key findings
- **Insight_Engine**: Component that extracts non-obvious insights from data
- **Confidence_Indicator**: Visual marker showing data reliability (verified, inferred, estimated)

## Requirements

### Requirement 1: Executive Summary Excellence

**User Story:** As a C-suite executive, I want a powerful 1-page executive summary, so that I can quickly grasp the company's strategic position and key insights.

#### Acceptance Criteria

1. WHEN the report is generated THEN the Report_Generator SHALL produce an executive summary containing: company snapshot, strategic position, 3-5 key insights, critical risks, and recommended actions
2. WHEN presenting key insights THEN the Report_Generator SHALL prioritize non-obvious findings over publicly available information
3. WHEN the executive summary exceeds 500 words THEN the Report_Generator SHALL condense content while preserving strategic value
4. IF financial data is available THEN the Report_Generator SHALL include key metrics with year-over-year trends
5. WHEN generating the summary THEN the Report_Generator SHALL use consulting-style language (direct, insight-driven, action-oriented)

### Requirement 2: Deep Industry Context

**User Story:** As a business development professional, I want comprehensive industry analysis, so that I can understand the company's competitive landscape and market dynamics.

#### Acceptance Criteria

1. WHEN analyzing industry THEN the Section_Analyzer SHALL identify market size, growth rate, and key trends with source citations
2. WHEN mapping competitors THEN the Section_Analyzer SHALL provide a competitive positioning matrix with at least 5 direct competitors
3. WHEN assessing market position THEN the Section_Analyzer SHALL estimate market share and competitive advantages
4. WHEN identifying trends THEN the Section_Analyzer SHALL distinguish between macro trends, industry trends, and company-specific trends
5. IF regulatory factors exist THEN the Section_Analyzer SHALL highlight compliance requirements and their business impact

### Requirement 3: Financial Intelligence

**User Story:** As an investor or analyst, I want detailed financial analysis, so that I can assess the company's financial health and growth trajectory.

#### Acceptance Criteria

1. WHEN financial data is available THEN the Section_Analyzer SHALL present revenue, profitability, and growth metrics with historical trends
2. WHEN public financials are unavailable THEN the Section_Analyzer SHALL estimate company size using employee count, funding rounds, and market signals
3. WHEN presenting financial data THEN the Report_Generator SHALL include confidence indicators showing data source reliability
4. WHEN analyzing financials THEN the Section_Analyzer SHALL benchmark against industry averages and key competitors
5. IF the company is venture-backed THEN the Section_Analyzer SHALL include funding history, investors, and implied valuation

### Requirement 4: Strategic Insights Engine

**User Story:** As a consultant, I want non-obvious strategic insights, so that I can provide unique value beyond what's publicly available.

#### Acceptance Criteria

1. WHEN generating insights THEN the Insight_Engine SHALL identify at least 5 strategic insights not immediately obvious from the company website
2. WHEN analyzing the company THEN the Insight_Engine SHALL identify potential vulnerabilities and strategic risks
3. WHEN assessing opportunities THEN the Insight_Engine SHALL suggest 3-5 actionable strategic recommendations with rationale
4. WHEN presenting insights THEN the Report_Generator SHALL support each insight with evidence and confidence level
5. WHEN analyzing leadership THEN the Insight_Engine SHALL assess leadership team background and strategic implications

### Requirement 5: Data Quality and Sourcing

**User Story:** As a report consumer, I want transparent data sourcing, so that I can trust the information and understand its reliability.

#### Acceptance Criteria

1. WHEN presenting any fact THEN the Report_Generator SHALL indicate the source (website, news, SEC filing, estimate)
2. WHEN data is estimated or inferred THEN the Report_Generator SHALL clearly mark it with confidence level (high, medium, low)
3. WHEN conflicting information exists THEN the Report_Generator SHALL present both perspectives with source attribution
4. WHEN scraping fails for key sources THEN the Research_Agent SHALL attempt alternative data sources before marking as unavailable
5. WHEN the report is complete THEN the Report_Generator SHALL include a sources appendix with all referenced URLs and access dates

### Requirement 6: Clean, Readable Presentation

**User Story:** As a busy professional, I want a clean, easy-to-read report, so that I can quickly absorb information without visual clutter.

#### Acceptance Criteria

1. WHEN generating output THEN the Report_Generator SHALL use clean formatting without emojis, excessive em-dashes, or decorative elements
2. WHEN structuring sections THEN the Report_Generator SHALL use natural headings (not numbered like "1. Executive Summary") that flow like a narrative
3. WHEN presenting data THEN the Report_Generator SHALL use simple tables and clean bullet points without over-formatting
4. WHEN generating content THEN the Report_Generator SHALL write in a direct, conversational professional tone - not stiff corporate-speak
5. WHEN formatting numbers THEN the Report_Generator SHALL use readable formats ($50M not $50,000,000.00) without excessive precision

### Requirement 7: Actionable Recommendations

**User Story:** As a business strategist, I want specific actionable recommendations, so that I can immediately apply insights to my engagement strategy.

#### Acceptance Criteria

1. WHEN generating recommendations THEN the Section_Analyzer SHALL provide specific, actionable items rather than generic advice
2. WHEN presenting recommendations THEN the Report_Generator SHALL prioritize by impact and feasibility
3. WHEN analyzing the company THEN the Section_Analyzer SHALL identify potential pain points and how to address them
4. WHEN targeting sales opportunities THEN the Section_Analyzer SHALL suggest specific entry points and value propositions
5. WHEN the company has known challenges THEN the Section_Analyzer SHALL propose solutions aligned with their strategic priorities

### Requirement 8: Technology and Operations Analysis

**User Story:** As a technology consultant, I want insight into the company's tech stack and operations, so that I can identify modernization opportunities.

#### Acceptance Criteria

1. WHEN analyzing technology THEN the Section_Analyzer SHALL identify visible technology choices (cloud providers, frameworks, tools)
2. WHEN assessing digital maturity THEN the Section_Analyzer SHALL rate the company's digital sophistication with supporting evidence
3. WHEN identifying tech stack THEN the Section_Analyzer SHALL note potential integration points and modernization opportunities
4. WHEN analyzing operations THEN the Section_Analyzer SHALL identify key operational processes and potential inefficiencies
5. IF job postings are available THEN the Section_Analyzer SHALL extract technology and skill requirements as signals

### Requirement 9: Report Quality Assurance

**User Story:** As a quality-conscious user, I want every report to meet consulting standards, so that I can confidently share it with senior stakeholders.

#### Acceptance Criteria

1. WHEN a section scores below 7/10 on quality THEN the Quality_Grader SHALL trigger additional research and regeneration
2. WHEN the report is complete THEN the Quality_Grader SHALL perform a final coherence check across all sections
3. WHEN inconsistencies are detected THEN the Quality_Grader SHALL flag and resolve conflicting information
4. WHEN generating content THEN the Section_Analyzer SHALL avoid generic filler and placeholder text
5. WHEN the report contains fewer than 3 unique insights THEN the Quality_Grader SHALL trigger deeper analysis

### Requirement 10: Speed and Efficiency

**User Story:** As a time-pressed professional, I want reports generated quickly, so that I can prepare for meetings on short notice.

#### Acceptance Criteria

1. WHEN generating a standard report THEN the Research_Agent SHALL complete within 5 minutes for typical companies
2. WHEN scraping encounters delays THEN the Research_Agent SHALL use parallel processing to maintain speed
3. WHEN AI calls are slow THEN the Research_Agent SHALL batch independent requests for efficiency
4. WHEN progress is being made THEN the Research_Agent SHALL display real-time status updates
5. IF a section takes longer than 60 seconds THEN the Research_Agent SHALL proceed with available data and note limitations


### Requirement 11: Writing Style and Tone

**User Story:** As a reader, I want content that reads naturally, so that I can engage with the material without being distracted by awkward formatting.

#### Acceptance Criteria

1. WHEN generating any content THEN the Section_Analyzer SHALL avoid em-dashes, replacing them with commas or separate sentences
2. WHEN generating any content THEN the Section_Analyzer SHALL never use emojis or decorative Unicode characters
3. WHEN writing insights THEN the Section_Analyzer SHALL use active voice and direct statements, not passive corporate jargon
4. WHEN structuring content THEN the Report_Generator SHALL flow naturally between sections like a well-written article
5. WHEN presenting lists THEN the Report_Generator SHALL use simple bullets without nested numbering schemes or excessive hierarchy

### Requirement 12: Clean Citation Formatting

**User Story:** As a report reader, I want inline URLs replaced with numbered references, so that the document text is clean and readable without long URLs breaking the flow.

#### Acceptance Criteria

1. WHEN the Report_Generator encounters an inline markdown link `[text](url)` THEN the system SHALL replace it with the link text followed by a numbered reference `[n]`
2. WHEN the same URL appears multiple times in the document THEN the system SHALL reuse the same reference number for all occurrences
3. WHEN a numbered reference is inserted THEN the system SHALL track the URL for inclusion in the Sources appendix
4. WHEN the document contains no URLs THEN the system SHALL produce output without any numbered references
5. WHEN the user specifies `--citation-style inline` THEN the system SHALL preserve inline URLs as-is (legacy behavior)
6. WHEN the user specifies `--citation-style sidecar` THEN the system SHALL generate a separate `{company}_sources.md` file alongside the report

### Requirement 13: AI Strategy Research

**User Story:** As a consultant preparing for a client meeting, I want AI opportunity recommendations tailored to the company's industry, so that I can discuss relevant AI use cases and technologies.

#### Acceptance Criteria

1. WHEN the user specifies `--ai-strategy` flag THEN the system SHALL run an AI opportunity analysis after company research completes
2. WHEN generating AI opportunities THEN the system SHALL produce 5 high-value AI use cases tailored to the company's industry and business model
3. WHEN the user specifies `--cloud-vendor azure` THEN the system SHALL reference Azure-specific technologies (Copilot, Azure OpenAI, Fabric, Power Platform)
4. WHEN the user specifies `--cloud-vendor aws` THEN the system SHALL reference AWS-specific technologies (Bedrock, SageMaker, Q, Lambda)
5. WHEN the user specifies `--cloud-vendor gcp` THEN the system SHALL reference GCP-specific technologies (Vertex AI, Gemini, BigQuery ML)
6. WHEN no cloud vendor is specified THEN the system SHALL provide cloud-agnostic AI recommendations
7. WHEN presenting AI opportunities THEN the system SHALL include for each: core idea, use case details, AI category, relevant technologies, and expected business impact
