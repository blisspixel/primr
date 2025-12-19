# Primr Glossary

This document defines terms used throughout Primr's codebase and documentation.

## Research Concepts

### Complete Mode
The recommended research mode that combines Scrape Mode and Deep Mode in a two-phase architecture. Produces comprehensive 40+ page reports by first collecting baseline data, then running parallel deep research on 10 chapters.

### Deep Mode
Research mode using Gemini's Deep Research Agent for autonomous web research. The agent plans its own research strategy, searches the web, and synthesizes findings. Best for broad market analysis and competitive intelligence.

### Deep Research Agent
Google's Gemini-based autonomous research system. It plans multi-step research, executes web searches, reads pages, and synthesizes findings with citations. Primr integrates with this via the `DeepResearchClient`.

### Epistemic Humility
The practice of distinguishing between what we know (facts), what we think (inferences), and what we should ask (hypotheses). Encoded in Primr's prompts and output formatting to avoid overconfident claims.

### Hierarchy of Truth
The precedence order for information in Complete Mode:
1. Company Facts (from website scraping): highest authority
2. External Context (from web search): market conditions, competitive intel
3. Synthesis: integrated analysis combining both sources

### Hypothesis
A strategic observation framed as something to validate rather than a conclusion. Primr outputs use language like "worth exploring" and "to validate with the client" to maintain epistemic humility.

### Scrape Mode
Research mode focused on the company's own website. Uses 4-tier scraping with AI-powered section extraction. Best for deep website analysis and specific data extraction.

### Section
A discrete unit of research output (e.g., "Company Overview", "Products & Services", "Leadership"). Scrape Mode produces ~18 sections; Complete Mode produces 10 chapters.

### Value Theory
An internal working document that captures hypotheses about how a company creates value. Used as context for subsequent analysis but not included in final output.

## Architecture Terms

### Composed Prompt
The result of building a prompt from YAML configuration. Contains the final prompt content, source files used, section count, word count, and list of substituted variables.

### Data Source
A file associated with a strategy module that provides context to the Deep Research agent. For AI Strategy, this includes vendor research files (e.g., `vendor-research-azure-2025-12.txt`). Data sources are uploaded to File Search Store before research.

### File Search Store
A Gemini API feature that allows uploading documents for the Deep Research Agent to reference. In Complete Mode, Phase 0 results are uploaded here so all chapter research nodes can access the baseline context.

### Grading Loop
The quality assurance process where each section is scored (0-100) by an AI grader. Sections below the threshold (default: 80) trigger additional research refinement.

### Master Architect
The component that decomposes a comprehensive report into 10 chapters. Uses gemini-2.0-flash for fast, cost-effective planning. Each chapter includes detailed research instructions.

### Orchestrator
The central coordinator (`ResearchOrchestrator`) that routes research requests to the appropriate engine based on mode selection and manages the overall research flow.

### Research Node
A single Deep Research task executing one chapter of a report. In Complete Mode, up to 3 nodes run in parallel, each with access to the shared File Search Store.

### Prompt Composer
The central class (`PromptComposer`) that builds prompts from YAML configurations. Loads prompt configs, merges shared components, performs variable substitution, and produces composed prompts ready for the AI.

### Prompt Config
A YAML file defining a prompt's structure: meta information, document purpose, epistemic rules, formatting guidelines, and sections. Located in `src/primr/prompts/`.

### Report Aggregator
The component that combines chapter outputs into a cohesive document. Generates table of contents, consolidates citations, and handles missing chapters gracefully.

### Shared Components
Reusable YAML fragments for epistemic rules, formatting standards, and consulting personas. Located in `src/primr/prompts/shared/`. Automatically merged into all prompts by the PromptComposer.

### Soft Block
When a website blocks a scraping request without returning an HTTP error. Examples: captchas, "please enable JavaScript" messages, Cloudflare challenges. Detected by content analysis.

### Strategy Module
A pluggable YAML configuration that generates a specific type of strategic analysis. Examples: AI Strategy, Cloud Migration, Data Strategy. Located in `src/primr/prompts/strategies/`. Each module can define its own sections, data sources, and vendor-specific guidance.

### Strategy Module Registry
The component (`StrategyModuleRegistry`) that discovers and manages strategy modules. Auto-discovers YAML files in the `strategies/` directory and provides access to their metadata and data sources.

### Tier (Scraping)
One of four scraping methods, tried in order of increasing complexity:
1. requests: Simple HTTP, no JavaScript
2. httpx: HTTP/2 with better headers
3. Playwright: Full browser with JavaScript
4. Playwright Aggressive: Full browser with stealth evasion

## Data Structures

### ComposedPrompt
The result from PromptComposer containing: content (the final prompt string), source_files (YAML files used), section_count, word_count, and variables_substituted.

### ChapterPlan
A single chapter in the research plan, containing: chapter number, title, research prompt, and expected page count.

### ChapterResult
The output from executing a single chapter's research, containing: content, citations, duration, success status, and any error message.

### OrchestratorResult
The complete result from a research run, containing: section results (dict), raw content, citations, duration, success status, and metadata.

### ReportPlan
The complete plan for a multi-chapter report, containing: company name, list of ChapterPlans, and total expected pages.

### PromptContext
Runtime context for prompt variable substitution: company_name, website_url, cloud_vendor, current_date, has_stage1_context, and custom_vars dictionary.

### ResearchConfig
Configuration for a research task: mode, timeout, poll interval, and optional section filters.

### SectionSpec
A YAML definition of a report section: id, name, part number, purpose, covers (list of topics), depth guidance, and optional subsections.

### StrategyModule
Metadata about a strategy module: name, display_name, description, config_path, is_builtin flag, and data_sources list.

### ResearchProgress
A progress update from deep research: status, message, thought (if available), and partial result.

### ResearchResult
The result from a Deep Research task: content, citations, interaction ID, duration, status, and optional thinking log.

## Configuration Terms

### AIConfig
Configuration for AI model behavior: model names, retry counts, grade threshold, temperature, thinking level, and fallback chains.

### CacheConfig
Configuration for content caching: max size, TTL, and cache name.

### PathConfig
Configuration for file paths: project root, output directory, working directory, logs directory, and cache directory.

### PricingConfig
Configuration for cost estimation: token prices per million for input/output, base cost for deep research, and search cost per query.

### ScrapingConfig
Configuration for web scraping: max retries, timeout, max depth, cache TTL, minimum content lengths, excluded sites, and soft block indicators.

### TimeoutConfig
Configuration for HTTP timeouts: connect timeout, read timeout, and total operation timeout.

## Type System Terms

### Protocol
A Python typing construct that defines an interface without requiring inheritance. Primr uses protocols for dependency injection (e.g., `AIClientProtocol`, `ScraperProtocol`).

### Result Type
A generic type that represents either success (with a value) or failure (with an error). Provides methods like `is_ok`, `is_err`, `unwrap_or`.

### Type Guard
A function that performs runtime type checking and narrows the type for static analysis. Examples: `is_valid_url()`, `is_search_result()`.

### TypedDict
A Python typing construct that defines the shape of a dictionary with specific keys and value types. Used for structured data like `SearchResult`, `ScrapedPage`.

## Output Terms

### Citation
A reference to a source used in the research. Contains: number, title, URL, and optionally the chapter it appears in.

### Citation Style
How sources are referenced in the output:
- numbered: [1] style references with bibliography
- inline: URLs preserved in text
- sidecar: separate sources file

### Executive Summary
The "so what" section at the beginning of a report. Synthesizes the most critical findings a decision-maker needs in 60 seconds.

### Narrative Gap Analysis
A section that identifies contrasts between what a company says and external signals. Framed as observations to explore, not accusations.

### SWOT Analysis
Strengths, Weaknesses, Opportunities, Threats assessment. In Primr, framed as observations to validate with the client rather than conclusions.

## Operational Terms

### Adaptive Polling
Adjusting the interval between status checks based on elapsed time. Faster initially (every 5s), slower as research progresses (up to 20s).

### Backoff
Increasing delay between retry attempts after failures. Primr uses exponential backoff with jitter to avoid thundering herd problems.

### Correlation ID
A unique identifier that tracks a request through all components. Used for debugging and log correlation.

### Dry Run
Running the cost estimation without executing the actual research. Shows expected API calls, token usage, and estimated cost.

### Job Recovery
The ability to resume a Deep Research task after interruption. Pending jobs are saved to disk with their interaction IDs.

### Quota Exhaustion
When the daily API limit is reached. Primr detects this and stops immediately rather than retrying.

### Rate Limiting
Controlling the rate of API calls to avoid hitting limits. In Complete Mode, max 3 concurrent Deep Research tasks.

## Browser Fingerprinting Terms

### Browser Profile
A set of browser characteristics used to appear as a real user: user agent, platform, timezone, screen size, WebGL renderer, etc. Primr rotates through 4 profiles.

### Stealth Script
JavaScript injected into the browser to hide automation indicators. Removes `navigator.webdriver`, spoofs plugins, and masks other detection vectors.

### Cookie Banner Dismissal
Automatically clicking "Accept" on cookie consent dialogs to access page content. Primr tries multiple common selectors.

## File Locations

### Cache Directory
`logs/scrape_cache/` - Stores cached scraped content with metadata.

### Logs Directory
`logs/` - Contains scraping error logs, chat history, and usage tracking.

### Output Directory
`output/` - Where generated reports are saved (TXT, DOCX, PDF, ZIP).

### Working Directory
`working/{Company}/` - Intermediate files during research: scraped summaries, value theory, section drafts.
