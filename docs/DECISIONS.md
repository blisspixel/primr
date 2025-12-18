# Design Decisions

This document records key architectural and design decisions in Primr, including the context, options considered, and rationale for each choice.

## ADR-001: Gemini as Primary AI Provider

### Context
Primr needs an AI provider for research synthesis, content generation, and analysis. The primary options were OpenAI (GPT-4), Anthropic (Claude), and Google (Gemini).

### Decision
Use Google Gemini as the primary (and currently only) AI provider.

### Rationale
1. **Deep Research Agent**: Gemini offers a unique Deep Research Agent that autonomously plans and executes multi-step research with built-in Google Search. No other provider offers this capability.
2. **File Search Store**: Gemini's File Search Store allows uploading context documents that the agent can reference during research. This enables the two-phase architecture where Phase 0 results inform Phase 2.
3. **Cost**: Gemini pricing is competitive, especially for the flash models used in planning.
4. **Integration**: Single provider simplifies API key management and reduces complexity.

### Consequences
- Primr is dependent on Google's API availability and pricing
- Users must have Google Cloud accounts
- Future multi-provider support would require abstraction layer

### Status
Accepted (December 2025)

---

## ADR-002: 4-Tier Scraping Architecture

### Context
Web scraping faces varying levels of bot protection. A single approach fails on many sites.

### Decision
Implement a 4-tier fallback system:
1. requests (simple HTTP)
2. httpx (HTTP/2)
3. Playwright (browser)
4. Playwright Aggressive (full stealth)

### Rationale
1. **Speed vs. Capability Tradeoff**: Simple HTTP is fast but fails on JS-heavy sites. Browsers are slow but handle everything. Tiered approach optimizes for the common case.
2. **Cost Efficiency**: Most sites work with Tier 1-2. Only escalate to expensive browser scraping when needed.
3. **Graceful Degradation**: Each tier failing triggers the next, rather than failing the entire operation.

### Alternatives Considered
- **Single Playwright approach**: Simpler but 10x slower for simple sites
- **Headless Chrome only**: Missing HTTP/2 benefits of httpx
- **Third-party scraping services**: Adds cost and external dependency

### Consequences
- More complex codebase
- Playwright dependency adds installation complexity
- Some sites still block all tiers

### Status
Accepted (November 2025)

---

## ADR-003: Local-First Architecture

### Context
Research tools can be built as SaaS platforms or local applications.

### Decision
Primr runs entirely on the user's machine. No server component, no data storage outside the local filesystem.

### Rationale
1. **Privacy**: Company research may involve sensitive competitive intelligence. Local execution keeps data private.
2. **Simplicity**: No auth, no multi-tenancy, no infrastructure to maintain.
3. **Cost Transparency**: Users pay API costs directly, no markup.
4. **Reliability**: No dependency on Primr servers being available.

### Alternatives Considered
- **SaaS model**: Better for collaboration but adds complexity and privacy concerns
- **Hybrid**: Local execution with optional cloud sync. Deferred for future consideration.

### Consequences
- No built-in collaboration features
- Users must manage their own API keys
- Long-running operations tie up local resources
- Scale path requires architectural changes (see ROADMAP.md)

### Status
Accepted (November 2025)

---

## ADR-004: Recursive Hierarchical Research Architecture

### Context
Comprehensive company research requires both breadth (many topics) and depth (detailed analysis). A single AI call cannot produce 40+ pages of quality content.

### Decision
Implement a 4-phase architecture for Complete Mode:
1. Phase 0: Data Collection (structured scraping)
2. Phase 1: Planning (chapter decomposition)
3. Phase 2: Parallel Execution (10 Deep Research tasks)
4. Phase 3: Aggregation (combine chapters)

### Rationale
1. **Divide and Conquer**: Breaking into chapters allows each to be researched deeply.
2. **Parallelization**: 10 chapters at 3 concurrent = ~15-20 minutes vs. 100+ minutes sequential.
3. **Shared Context**: File Search Store ensures all chapters have access to baseline facts.
4. **Graceful Failure**: Individual chapter failures don't fail the entire report.

### Alternatives Considered
- **Single large prompt**: Token limits and quality degradation at scale
- **Sequential chapters**: Too slow (10 x 10-15 min = 100+ min)
- **No shared context**: Chapters would repeat basic facts or contradict each other

### Consequences
- Complex orchestration logic
- Higher API costs (multiple Deep Research calls)
- Potential for chapter inconsistencies despite shared context

### Status
Accepted (December 2025)

---

## ADR-005: Epistemic Humility in Prompts

### Context
AI-generated research can sound authoritative even when speculative. This creates risk when outputs inform business decisions.

### Decision
Encode epistemic humility directly into prompts:
- Distinguish facts, inferences, and hypotheses
- Use hedging language ("appears to", "worth exploring")
- Frame strategic observations as questions, not conclusions
- Require citations for factual claims

### Rationale
1. **Accuracy**: Prevents AI from hallucinating confident claims
2. **Usefulness**: Outputs that acknowledge uncertainty are more actionable
3. **Trust**: Users can rely on the distinction between verified and speculative
4. **Consulting Best Practice**: Mirrors how good consultants actually think

### Alternatives Considered
- **Confidence scores**: Numeric scores feel false precision
- **Post-processing filters**: Harder to implement than prompt engineering
- **User responsibility**: Puts burden on users to evaluate claims

### Consequences
- Outputs may feel less "decisive" to some users
- Longer prompts increase token costs
- Requires consistent prompt maintenance

### Status
Accepted (December 2025)

---

## ADR-006: Section-Based Output Structure

### Context
Research output needs structure for both human consumption and programmatic access.

### Decision
Use a section-based structure where each section has a key (e.g., "company_overview") and content. Sections are stored as a dictionary and can be individually accessed, graded, and refined.

### Rationale
1. **Granular Quality Control**: Each section can be graded and refined independently
2. **Flexible Output**: Same sections can produce TXT, DOCX, or PDF
3. **Incremental Updates**: Future iterations can update specific sections
4. **Programmatic Access**: API users can extract specific sections

### Alternatives Considered
- **Single document blob**: Simpler but no granular control
- **Hierarchical chapters/sections**: More complex, deferred for future
- **Database storage**: Overkill for local-first tool

### Consequences
- Section keys must be consistent across modes
- Normalization needed when combining different research modes
- Some content doesn't fit neatly into sections

### Status
Accepted (November 2025)

---

## ADR-007: Quality Grading Loop

### Context
AI-generated content varies in quality. Some sections may be thin or miss key information.

### Decision
Implement a grading loop where each section is scored (0-100) and sections below threshold trigger refinement.

### Rationale
1. **Quality Assurance**: Catches low-quality sections before output
2. **Targeted Improvement**: Only refines sections that need it
3. **Transparency**: Grades provide insight into output quality
4. **Automation**: No manual review required for basic quality

### Alternatives Considered
- **No grading**: Faster but inconsistent quality
- **Human review**: Doesn't scale, defeats automation purpose
- **Regenerate everything**: Wasteful when most sections are good

### Consequences
- Additional API calls for grading
- Threshold tuning affects output quality vs. cost
- Grading itself can be inconsistent

### Status
Accepted (November 2025)

---

## ADR-008: Thread-Safe Singletons

### Context
Components like AI clients and caches should be shared across the application but initialized lazily.

### Decision
Use double-check locking pattern for thread-safe singletons with explicit reset functions for testing.

```python
_instance = None
_lock = threading.Lock()

def get_instance():
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = MyClass()
    return _instance

def reset_instance():
    global _instance
    with _lock:
        _instance = None
```

### Rationale
1. **Thread Safety**: Prevents race conditions in concurrent code
2. **Lazy Initialization**: Resources only created when needed
3. **Testability**: Reset functions allow test isolation
4. **Consistency**: Same pattern across all singletons

### Alternatives Considered
- **Module-level instances**: Not lazy, harder to test
- **Dependency injection**: More complex, overkill for this scale
- **No singletons**: Would create multiple clients, waste resources

### Consequences
- Global state can make debugging harder
- Must remember to reset in tests
- Pattern must be applied consistently

### Status
Accepted (December 2025)

---

## ADR-009: Adaptive Polling for Deep Research

### Context
Deep Research tasks take 5-20 minutes. Polling too frequently wastes API calls; too infrequently delays completion detection.

### Decision
Implement adaptive polling that starts fast and slows down:
- 0-60s: Poll every 5 seconds
- 60-300s: Poll every 10 seconds
- 300s+: Poll every 20 seconds

### Rationale
1. **Responsiveness**: Fast polling initially catches quick completions
2. **Efficiency**: Slower polling later reduces unnecessary API calls
3. **User Experience**: Progress updates feel responsive without being noisy

### Alternatives Considered
- **Fixed interval**: Either too slow initially or wasteful later
- **Webhooks**: Not supported by Deep Research API
- **Exponential backoff**: Too aggressive slowdown

### Consequences
- Slightly more complex polling logic
- Completion detection delayed by up to 20s for long tasks
- Must track elapsed time during polling

### Status
Accepted (December 2025)

---

## ADR-010: Browser Fingerprint Rotation

### Context
Bot detection systems identify scrapers by browser fingerprints. Using a single fingerprint gets blocked.

### Decision
Maintain 4 browser profiles (Windows Chrome, Mac Chrome, Windows Firefox, Mac Safari) and rotate randomly. Each profile includes: user agent, platform, timezone, screen size, WebGL renderer, and other fingerprint components.

### Rationale
1. **Evasion**: Different fingerprints avoid pattern detection
2. **Realism**: Profiles based on real browser configurations
3. **Simplicity**: 4 profiles is enough diversity without complexity
4. **Maintainability**: Profiles can be updated as browsers evolve

### Alternatives Considered
- **Single fingerprint**: Gets blocked quickly
- **Random generation**: Unrealistic combinations get flagged
- **Fingerprint service**: External dependency, cost

### Consequences
- Profiles need periodic updates
- Some sites may still detect automation
- Adds complexity to scraping code

### Status
Accepted (November 2025)

---

## ADR-011: LRU Cache with Disk Persistence

### Context
Scraping the same URL multiple times wastes time and may trigger rate limits.

### Decision
Implement two-layer caching:
1. Memory: LRU cache with 100 entry limit
2. Disk: JSON metadata + text content with 24-hour TTL

### Rationale
1. **Speed**: Memory cache is instant
2. **Persistence**: Disk cache survives restarts
3. **Bounded Memory**: LRU prevents unbounded growth
4. **Freshness**: TTL ensures data doesn't get stale

### Alternatives Considered
- **Memory only**: Lost on restart
- **Disk only**: Slower for repeated access
- **Redis/SQLite**: Overkill for local tool
- **No cache**: Wasteful and slow

### Consequences
- Cache invalidation is time-based only
- Disk space usage grows with usage
- Cache key collisions theoretically possible (SHA-256)

### Status
Accepted (November 2025)

---

## ADR-012: Soft Block Detection

### Context
Some sites return HTTP 200 but serve captchas or "please enable JavaScript" pages instead of content.

### Decision
Implement content-based soft block detection by checking for indicator phrases: "captcha", "verify you are human", "cloudflare", "access denied", etc.

### Rationale
1. **Accuracy**: HTTP status alone doesn't indicate success
2. **Escalation Trigger**: Soft blocks trigger next scraping tier
3. **Logging**: Detected blocks are logged for debugging

### Alternatives Considered
- **Content length only**: Misses verbose block pages
- **Machine learning**: Overkill, hard to maintain
- **Ignore and proceed**: Would produce garbage output

### Consequences
- False positives possible (legitimate pages mentioning "captcha")
- Indicator list needs maintenance
- Some novel block pages may not be detected

### Status
Accepted (November 2025)

---

## ADR-013: No Em-Dashes or Emojis in Output

### Context
AI models often use em-dashes and emojis in generated text. These can cause encoding issues and look unprofessional in business documents.

### Decision
Explicitly instruct prompts to avoid em-dashes and emojis. Post-process output to remove any that slip through.

### Rationale
1. **Professionalism**: Business documents shouldn't have emojis
2. **Encoding Safety**: Em-dashes cause issues in some systems
3. **Consistency**: Uniform style across all outputs
4. **User Feedback**: Early users found these distracting

### Alternatives Considered
- **Allow and let users edit**: Adds friction
- **Configurable**: Complexity for edge case
- **Post-processing only**: Prompts are more reliable

### Consequences
- Prompts are slightly longer
- Some legitimate uses of em-dashes are lost
- Must maintain formatting rules in prompts

### Status
Accepted (December 2025)
