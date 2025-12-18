# Design Document: Recursive Hierarchical Research Architecture

## Overview

Implement a **Recursive Hierarchical Research Architecture** to produce comprehensive, 40+ page strategic reports. Per Gemini documentation:

> "A single invocation of the Deep Research agent typically yields 1,500-2,000 words (~6-8 pages). To produce a comprehensive strategic document, the solution is a Recursive Hierarchical Research Architecture."

**Three-phase approach:**
1. **Master Architect**: Decompose report into 8-10 chapters
2. **Parallel Research Nodes**: Run Deep Research for each chapter (with shared context)
3. **Aggregation**: Combine chapters with narrative smoothing

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ Phase 0: Data Collection (~20 min)                              │
│                                                                  │
│ Structured Pipeline:                                            │
│ - Website scraping (4-tier)                                     │
│ - Google Custom Search                                          │
│ - Section extraction                                            │
│                                                                  │
│ Output: Consolidated context file → File Search Store           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Phase 1: Master Architect (~2 min)                              │
│                                                                  │
│ Model: gemini-2.0-flash (fast, cheap for planning)              │
│                                                                  │
│ Input: Company name + context summary                           │
│ Output: JSON with 8-10 chapters, each containing:               │
│   - title: "Competitive Landscape Analysis"                     │
│   - research_prompt: 200-word detailed instructions             │
│                                                                  │
│ Chapters cover:                                                 │
│ 1. Executive Summary & Company Snapshot                         │
│ 2. Products, Services & Value Proposition                       │
│ 3. Leadership, Culture & Organization                           │
│ 4. Financial Position & Business Model                          │
│ 5. Target Markets & Customer Segments                           │
│ 6. Competitive Landscape & Market Position                      │
│ 7. Industry Dynamics & External Forces                          │
│ 8. SWOT Analysis & Strategic Assessment                         │
│ 9. Risk Analysis & Mitigation                                   │
│ 10. Strategic Recommendations & Questions                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Phase 2: Parallel Research Nodes (~15-20 min)                   │
│                                                                  │
│ Concurrency: 3 parallel tasks (rate limit protection)           │
│                                                                  │
│ Each node:                                                      │
│ - Agent: deep-research-pro-preview-12-2025                      │
│ - Tools: file_search (shared context) + google_search           │
│ - Prompt: Chapter-specific research instructions                │
│ - Output: 1,500-2,000 words (~5-6 pages)                        │
│                                                                  │
│ ┌─────────┐ ┌─────────┐ ┌─────────┐                            │
│ │Chapter 1│ │Chapter 2│ │Chapter 3│  ← Running                 │
│ └─────────┘ └─────────┘ └─────────┘                            │
│ ┌─────────┐ ┌─────────┐ ┌─────────┐                            │
│ │Chapter 4│ │Chapter 5│ │Chapter 6│  ← Queued                  │
│ └─────────┘ └─────────┘ └─────────┘                            │
│ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌──────────┐               │
│ │Chapter 7│ │Chapter 8│ │Chapter 9│ │Chapter 10│ ← Queued      │
│ └─────────┘ └─────────┘ └─────────┘ └──────────┘               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Phase 3: Aggregation & Smoothing (~2 min)                       │
│                                                                  │
│ - Concatenate chapter outputs                                   │
│ - Generate cohesive Executive Summary                           │
│ - Smooth transitions between chapters                           │
│ - Add table of contents                                         │
│                                                                  │
│ Output: {Company}_Strategic_Overview_{date}.docx (40+ pages)    │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. MasterArchitect Class

**File:** `src/primr/ai/report_architect.py` (new)

```python
class MasterArchitect:
    """Decomposes strategic report into chapters."""
    
    async def generate_chapter_plan(
        self, 
        company_name: str, 
        context_summary: str
    ) -> list[dict]:
        """
        Returns list of chapters:
        [
            {
                "title": "Executive Summary & Company Snapshot",
                "research_prompt": "Write a comprehensive executive summary..."
            },
            ...
        ]
        """
```

### 2. ResearchNodeExecutor Class

**File:** `src/primr/ai/research_executor.py` (new)

```python
class ResearchNodeExecutor:
    """Executes parallel Deep Research tasks with rate limiting."""
    
    def __init__(self, file_search_store: str, max_concurrent: int = 3):
        self.store = file_search_store
        self.semaphore = asyncio.Semaphore(max_concurrent)
    
    async def execute_chapter(self, chapter: dict) -> str:
        """Run Deep Research for a single chapter."""
        async with self.semaphore:
            # Rate-limited execution
            ...
    
    async def execute_all(self, chapters: list[dict]) -> list[str]:
        """Run all chapters in parallel (with concurrency limit)."""
        tasks = [self.execute_chapter(ch) for ch in chapters]
        return await asyncio.gather(*tasks)
```

### 3. ReportAggregator Class

**File:** `src/primr/ai/report_aggregator.py` (new)

```python
class ReportAggregator:
    """Combines chapters into cohesive document."""
    
    async def aggregate(
        self, 
        chapters: list[str],
        company_name: str
    ) -> str:
        """
        - Concatenate chapters
        - Generate unified executive summary
        - Smooth transitions
        - Add TOC
        """
```

### 4. Updated ResearchOrchestrator

**File:** `src/primr/core/research_orchestrator.py`

Modify `_run_complete_research()` to use the new recursive architecture:

```python
async def _run_complete_research(self, ...):
    # Phase 0: Structured Pipeline (existing)
    structured_result = await self._run_structured_research(...)
    context_file = self._prepare_step1_context(...)
    store_name = await self._upload_to_file_search(context_file)
    
    # Phase 1: Master Architect (new)
    architect = MasterArchitect()
    chapters = await architect.generate_chapter_plan(
        company_name, 
        self._summarize_context(structured_result)
    )
    
    # Phase 2: Parallel Research (new)
    executor = ResearchNodeExecutor(store_name, max_concurrent=3)
    chapter_contents = await executor.execute_all(chapters)
    
    # Phase 3: Aggregation (new)
    aggregator = ReportAggregator()
    final_report = await aggregator.aggregate(chapter_contents, company_name)
    
    # Cleanup
    await self._delete_file_search_store(store_name)
    
    return final_report
```

## Prompt Engineering

### Master Architect Prompt

```
You are a Principal Strategic Architect. We are commissioning a comprehensive 
strategic advisory report on {company_name}.

Context Summary: {context_summary}

Task: Deconstruct this topic into exactly 10 substantive chapters.
Each chapter must be distinct, exhaustive, and capable of standing alone 
as a 5-6 page deep dive.

Output a JSON object:
{
  "chapters": [
    {
      "title": "Chapter Title",
      "research_prompt": "Detailed 200-word instruction set for a researcher agent.
        Explicitly ask for data tables, specific metrics, and analysis relevant 
        to this chapter."
    }
  ]
}

Required chapters (adapt titles as appropriate):
1. Executive Summary & Company Snapshot
2. Products, Services & Value Proposition  
3. Leadership, Culture & Organization
4. Financial Position & Business Model
5. Target Markets & Customer Segments
6. Competitive Landscape & Market Position
7. Industry Dynamics & External Forces
8. SWOT Analysis & Strategic Assessment
9. Risk Analysis & Mitigation
10. Strategic Recommendations & Questions for Discovery
```

### Research Node Prompt Template

```
Task: Write a comprehensive, 2,000-word strategic chapter titled '{chapter_title}'.

Instructions: {chapter_research_prompt}

HIERARCHY OF TRUTH:
1. COMPANY FACTS: Use the File Search Store for baseline company data.
   These are facts from the company's own website - highest authority.
2. EXTERNAL CONTEXT: Use Google Search for market conditions, competitive intel,
   industry trends, and news.
3. SYNTHESIS: Weave internal baseline + external context into cohesive narrative.

Constraints:
- Include at least 2 Markdown data tables comparing key metrics
- Cite every claim using inline citations
- Write in full paragraphs, not bullet lists
- Tone: Professional Strategic Advisory
- If data unavailable, state "Not publicly available" rather than estimating
```

## Correctness Properties

### Property 1: Chapter Decomposition
*For any* full mode execution, the Master Architect SHALL produce 8-10 chapter definitions with titles and research prompts.
**Validates: Requirements 1.1**

### Property 2: Parallel Execution with Rate Limiting
*For any* parallel research execution, the system SHALL limit concurrent tasks to max 3.
**Validates: Requirements 4.1**

### Property 3: Shared Context Access
*For any* research node execution, the Deep Research API call SHALL include the same File Search Store.
**Validates: Requirements 3.2**

### Property 4: Chapter Completeness
*For any* successful chapter execution, the output SHALL be 1,000+ words of substantive content.
**Validates: Requirements 2.3**

### Property 5: Aggregation Produces Single Document
*For any* full mode execution, the final output SHALL be a single document containing all chapters.
**Validates: Requirements 1.3**

### Property 6: Graceful Failure Handling
*For any* chapter task that fails, the system SHALL log the error and continue with remaining chapters.
**Validates: Requirements 4.2**

## Error Handling

1. **Master Architect fails**: Fall back to default chapter structure
2. **Research node fails**: Log error, continue with other chapters, note gap in final report
3. **Rate limit hit**: Exponential backoff, retry
4. **File Search upload fails**: Proceed without context (web search only)
5. **Aggregation fails**: Return raw concatenated chapters

## Testing Strategy

**Library:** Hypothesis (Python), minimum 100 iterations

**Unit Tests:**
- Master Architect produces valid JSON with required fields
- Research executor respects concurrency limit
- Aggregator produces valid markdown

**Integration Tests:**
- End-to-end with mock Deep Research responses
- Verify 10 chapters produced and aggregated

**Property Tests:**
- Chapter count within range (8-10)
- Each chapter has title and research_prompt
- Concurrency never exceeds limit
