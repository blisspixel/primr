# QA Grading System Fix - Requirements Document

## Introduction

The Primr QA system currently fails to provide useful feedback on report quality, defaulting to generic 50/100 scores instead of actionable insights. This undermines Primr's core goal of producing useful internal research outputs. The Evertrue LLC case demonstrates this - a comprehensive 35+ page strategic analysis received a meaningless fallback score with no actionable feedback for improvement.

The QA system should help validate that reports meet Primr's quality standards for internal research: coherent strategic thesis, hypothesis-driven framing, specific evidence with citations, and rigorous framework application.

## Glossary

- **QA System**: Quality feedback system that evaluates reports against Primr's internal research standards
- **Actionable Feedback**: Specific suggestions for improving report quality aligned with Primr's goals
- **Strategic Coherence**: Whether the report has a clear strategic thesis that ties analysis together
- **Hypothesis-Driven**: Framing observations as hypotheses rather than declarative statements
- **Citation Quality**: Proper attribution with appropriate precision (ranges vs exact figures)

## Requirements

### Requirement 1

**User Story:** As a Primr user, I want actionable feedback on report quality aligned with Primr's internal research goals, so that I can improve the strategic value of my outputs.

#### Acceptance Criteria

1. WHEN the QA system analyzes a report THEN the system SHALL evaluate strategic coherence and hypothesis-driven framing per Primr standards
2. WHEN citation issues are found THEN the system SHALL provide specific guidance on appropriate precision and attribution
3. WHEN framework sections lack rigor THEN the system SHALL identify which frameworks need strengthening
4. WHEN insights are repeated across sections THEN the system SHALL flag redundancy that violates Primr's "one insight per section" rule
5. WHEN the report lacks a clear strategic thesis THEN the system SHALL suggest how to better tie the analysis together

### Requirement 2

**User Story:** As a Primr user, I want to understand specific quality issues rather than generic scores, so that I can take concrete action to improve my research outputs.

#### Acceptance Criteria

1. WHEN QA analysis completes THEN the system SHALL provide specific, actionable feedback rather than just numerical scores
2. WHEN quality issues are identified THEN the system SHALL reference Primr's calibration notes and intended use guidelines
3. WHEN the analysis fails THEN the system SHALL explain what prevented proper evaluation rather than showing generic errors
4. WHEN reports meet Primr standards THEN the system SHALL confirm alignment with internal research goals
5. WHEN improvements are suggested THEN the system SHALL tie recommendations to Primr's value creation framework

### Requirement 3

**User Story:** As a Primr developer, I want reliable QA analysis that doesn't fail on well-structured reports, so that users receive consistent feedback on their research quality.

#### Acceptance Criteria

1. WHEN comprehensive reports are analyzed THEN the system SHALL complete analysis without falling back to generic responses
2. WHEN AI parsing encounters issues THEN the system SHALL retry with alternative approaches before declaring failure
3. WHEN network or service issues occur THEN the system SHALL implement proper retry logic with exponential backoff
4. WHEN analysis succeeds THEN the system SHALL validate results align with Primr's quality expectations
5. WHEN multiple failures occur THEN the system SHALL escalate through model fallbacks before giving up