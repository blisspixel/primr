# Primr Strategy Document Portfolio

This document tracks the available strategy documents in Primr and their implementation status.

## Overview

Strategy documents are OPTIONAL add-ons that can be run after the main Strategic Overview report. They use the Strategic Overview as primary input context and generate executive-level strategic frameworks.

These are NOT implementation plans or technical architectures. They are MBA/CEO/CIO/CMO/CISO level strategic thinking - frameworks that can be theorized from outside using public information and industry best practices.

## Key Principles

1. **Theorizable from Outside**: Can be developed using public information, strategic frameworks, and industry best practices
2. **Executive-Level**: Board/C-suite strategic thinking, not implementation details
3. **Not Presumptive**: Don't require internal knowledge we don't have (no cloud migration, no data modernization)
4. **Adoption Psychology**: All strategies include facilitation toolkit (Part A: Ideas + Part B: How to make them own it)
5. **Use Strategic Overview**: All strategies use the Strategic Overview report as primary input context

## What These Are NOT

- Implementation plans (requires internal knowledge)
- Technical architecture (requires knowing their stack)
- Specific tool recommendations (requires knowing their tools)
- Migration roadmaps (requires knowing current state)

## Strategy Documents

### Tier 1: Implemented and Tested

These strategies are fully implemented, tested, and ready to use. All have been validated with real company data (Delta Dental Plans Association, January 2026).

#### 1. AI Strategy (`ai_first_transformation.yaml`)
- **Audience**: CIO, Board, Executive Leadership
- **Purpose**: Board-level AI roadmap for strategic decision making
- **Goal**: Answer "What should we actually do with AI, and why?"
- **Status**: DONE - Fully Implemented and Tested
- **Usage**: `primr --ai-strategy-only "report.md" --cloud-vendor azure`
- **Output**: `{company}_AI_Strategy_{date}.md/txt/docx`
- **Key Sections**:
  - Strategic Thesis (AI-enabled vs AI-native)
  - Current State Hypotheses
  - AI Architecture Posture
  - Opportunity Domains (Productivity, Automation, Conversational, Agentic)
  - Quick Wins + Bigger Bets
  - Facilitation Toolkit (Socratic questions, stakeholder inception, workshop design)

#### 2. Customer Experience Strategy (`customer_experience.yaml`)
- **Audience**: CMO, Chief Customer Officer, VP Customer Success
- **Purpose**: CMO-level customer experience transformation strategy
- **Goal**: Answer "How do we create world-class digital customer experiences?"
- **Status**: DONE - Fully Implemented and Tested
- **Usage**: `primr --ai-strategy-only "report.md" --strategy-type customer_experience`
- **Output**: `{company}_Customer_Experience_Strategy_{date}.md/txt/docx`
- **Key Sections**:
  - Strategic Context (The CX Imperative)
  - Recommended CX Posture (Journey Architecture, Personalization, Self-Service)
  - CX Priorities (Critical Moments → Strategic Capabilities → Advanced)
  - Investment Framework
  - Technology Enablement
  - Facilitation Toolkit (Board presentation, stakeholder inception, workshop design)

#### 3. Security & Compliance Strategy (`modern_security_compliance.yaml`)
- **Audience**: CISO, CIO, Board Risk Committee
- **Purpose**: CISO-level security transformation strategy for the AI era
- **Goal**: Answer "How do we secure our organization in the age of AI and Zero Trust?"
- **Status**: DONE - Fully Implemented and Tested
- **Usage**: `primr --ai-strategy-only "report.md" --strategy-type modern_security_compliance`
- **Output**: `{company}_Security_Compliance_Strategy_{date}.md/txt/docx`
- **Key Sections**:
  - Strategic Context (Security in the AI Era)
  - Recommended Security Posture (Zero Trust, AI Security, Data Governance)
  - Compliance as Competitive Advantage
  - Security Priorities (Foundation + Quick Wins → Strategic → Advanced)
  - Investment Framework
  - Facilitation Toolkit (Board presentation, stakeholder inception, workshop design)

#### 4. Data Fabric Strategy (`data_fabric_strategy.yaml`)
- **Audience**: CDO, CTO, Data Leadership, Executive Leadership
- **Purpose**: Modern data platform strategy for the agentic AI era
- **Goal**: Answer "How do we build an intelligent data estate that grounds AI agents?"
- **Status**: DONE - Fully Implemented and Tested
- **Usage**: `primr --ai-strategy-only "report.md" --strategy-type data_fabric_strategy`
- **Output**: `{company}_Data_Fabric_Strategy_{date}.md/txt/docx`
- **Key Sections**:
  - Paradigm Shift (From warehousing to intelligent estates)
  - Current Data Landscape Assessment
  - Target Architecture (Data fabric, semantic layer, vectorization, real-time)
  - Platform Comparison (Fabric vs Snowflake vs Databricks)
  - Governance Framework (Access fabric, semantic governance, quality, compliance)
  - Agent Enablement (Data agents, operations agents, MCP integration)
  - Implementation Roadmap (Foundation → Semantic → Agents → Scale)
  - Investment Analysis
  - Facilitation Toolkit (Workshop agenda, stakeholder map, ghostwritten materials)

### Tier 2: Planned (Not Yet Implemented)

These strategies are identified but not yet implemented. They follow the same pattern as Tier 1.

#### 6. Employee Experience & Productivity Strategy
- **Audience**: CHRO, COO, Executive Leadership
- **Purpose**: Strategic framework for modern employee experience
- **Goal**: Answer "How do we create a workplace that attracts and retains top talent?"
- **Status**: Planned
- **Key Focus**:
  - Remote/hybrid work enablement
  - Digital workplace transformation
  - Employee productivity and wellbeing
  - Talent retention and development

#### 7. AI Governance & Responsible AI Strategy
- **Audience**: Chief AI Officer, Board, Legal/Compliance
- **Purpose**: Strategic framework for responsible AI governance
- **Goal**: Answer "How do we govern AI to maximize value while managing risk?"
- **Status**: Planned
- **Key Focus**:
  - AI ethics and responsible AI principles
  - AI governance framework
  - Risk management and compliance
  - Transparency and explainability

#### 8. AI-Powered Go-To-Market Strategy
- **Audience**: CRO, CMO, VP Sales
- **Purpose**: Strategic framework for AI-powered sales and marketing
- **Goal**: Answer "How do we leverage AI to accelerate growth?"
- **Status**: Planned
- **Key Focus**:
  - AI-powered lead generation and qualification
  - Personalized marketing at scale
  - Sales enablement and automation
  - Customer intelligence and insights

#### 9. Product Innovation & AI Integration Strategy
- **Audience**: CPO, CTO, Product Leadership
- **Purpose**: Strategic framework for AI-native product development
- **Goal**: Answer "How do we build AI into our products?"
- **Status**: Planned
- **Key Focus**:
  - AI-native product architecture
  - Product innovation pipeline
  - Build vs buy vs partner decisions
  - Competitive positioning

### Deprecated/Requires Internal Discovery

These strategies exist as placeholders but are TOO PRESUMPTIVE - they require internal knowledge we don't have from outside.

#### Cloud Migration Strategy (`cloud_migration.yaml`)
- **Status**: Requires Internal Discovery
- **Why**: We don't know their current infrastructure, applications, or data
- **When to Use**: After internal discovery and assessment
- **Note**: May need deprecation warning or removal

#### Data Strategy (`data_strategy.yaml`)
- **Status**: REPLACED by `data_fabric_strategy.yaml`
- **Why**: Old placeholder version (v0.1.0) was too generic and didn't reflect 2026 data fabric thinking
- **Replacement**: Use `data_fabric_strategy.yaml` instead - comprehensive 2026 data strategy with semantic layers, data fabrics, and agent enablement
- **Note**: Old file should be deprecated or removed to avoid confusion

## Adoption Psychology Pattern

All strategy documents follow the same two-part structure:

### Part A: THE IDEAS (What's Possible)
Traditional strategy content:
- Strategic context and burning platform
- Current state hypotheses
- Recommended posture/framework
- Specific priorities and roadmap
- Investment framework
- Risk analysis

### Part B: THE FACILITATION TOOLKIT (How to Make Them Own It)
Adoption psychology and enablement:
- Board presentation materials (ready-to-use slide outlines)
- Stakeholder inception map (who to incept and how)
- Workshop co-creation agenda (IKEA Effect at strategic level)
- Champion enablement materials (ghostwritten templates)
- Next steps (immediate actions)

## Usage Patterns

### Generate AI Strategy (Default)
```bash
primr "Company Name" https://example.com --cloud-vendor azure
```
Generates Strategic Overview + AI Strategy

### Generate Specific Strategy from Existing Report
```bash
# Customer Experience Strategy
primr --ai-strategy-only "output/Company_Strategic_Overview.md" --strategy-type customer_experience

# Security & Compliance Strategy
primr --ai-strategy-only "output/Company_Strategic_Overview.md" --strategy-type modern_security_compliance

# Data Fabric Strategy
primr --ai-strategy-only "output/Company_Strategic_Overview.md" --strategy-type data_fabric_strategy

# AI Strategy (regenerate or with different vendor)
primr --ai-strategy-only "output/Company_Strategic_Overview.md" --cloud-vendor azure
```

### List Available Strategies
```bash
primr --list-strategies
```
Shows all available strategy types with usage examples

### Generate Multiple Strategies (Future)
```bash
primr "Company Name" https://example.com --strategies ai,security,cx
```
Generates Strategic Overview + Multiple Strategies (not yet implemented)

## Implementation Checklist

When implementing a new strategy document:

- [ ] Create YAML file in `src/primr/prompts/strategies/`
- [ ] Follow the established pattern (see `ai_first_transformation.yaml` as reference)
- [ ] Include both Part A (Ideas) and Part B (Facilitation Toolkit)
- [ ] Add adoption psychology principles in `document_purpose`
- [ ] Define all sections with clear purpose and depth guidance
- [ ] Add `cli_description` field to meta section explaining what the strategy helps think through
- [ ] Update CLI to support `--strategy-type` flag for new strategy
- [ ] Update README with new strategy option
- [ ] Update this document (STRATEGY_PORTFOLIO.md)
- [ ] Test generation with real company data
- [ ] Verify quality assessment works with new strategy

## Quality Standards

All strategy documents must:

1. **Be Specific**: Connect to THIS company's situation from Strategic Overview
2. **Be Honest**: Use ranges, state assumptions, acknowledge uncertainty
3. **Be Actionable**: Provide concrete next steps and decision frameworks
4. **Be Facilitative**: Include tools to help them own the ideas
5. **Be Strategic**: Executive-level thinking, not implementation details

## Next Steps

1. **Implement CLI Support**: Update CLI to support `--strategy-type` flag
2. **Test Tier 1 Strategies**: Generate all three new strategies with real companies
3. **Update README**: Document new strategy options
4. **Consider Tier 2**: Evaluate which Tier 2 strategies to implement next
5. **Deprecation Decision**: Decide whether to deprecate or clearly mark cloud_migration and data_strategy

## References

- AI Strategy: `src/primr/prompts/strategies/ai_strategy.yaml`
- AI-First Transformation: `src/primr/prompts/strategies/ai_first_transformation.yaml`
- Security & Compliance: `src/primr/prompts/strategies/modern_security_compliance.yaml`
- Customer Experience: `src/primr/prompts/strategies/customer_experience.yaml`
- Data Fabric Strategy: `src/primr/prompts/strategies/data_fabric_strategy.yaml`
- Social Engineering Research: `docs/research/research social engineering to help.txt`
- Data Strategy Research (2026): `docs/research/research data strategy with fabric 2026.txt`
