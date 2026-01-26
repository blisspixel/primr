# CLI/UX Enhancement - Requirements

## Problem Statement

The CLI output during scraping looks "like shit" with excessive WARNING logs every 2 seconds for normal operation. The user experience doesn't reflect Primr's mission: generating comprehensive company intelligence briefs where content quality matters more than speed.

**Current Issues:**
1. WARNING logs for every page >8s even when scraping succeeds
2. Multi-line diagnostics spam the console for normal operation
3. Progress display is noisy with tier information
4. User cancelled runs 3 times due to poor UX

**Core Philosophy Mismatch:**
- Primr runs 25-40 minute pipelines costing $0.80-1.50
- Purpose: Generate consultant-grade company intelligence
- "34 pages from a protected site typically yields more useful content than 100 pages from a poorly-structured site" (README)
- **Content quality > Speed**: "its OK if it takes 21 seconds to scrape a page"

## User Stories

### 1. Clean Progress Display
**As a** Primr user  
**I want** clean, minimal progress output during scraping  
**So that** I can see what's happening without noise

**Acceptance Criteria:**
- 1.1. No WARNING logs for successful pages (even if slow)
- 1.2. Inline progress updates: `Scraping 3/50 /investors/financial-reports (9s)`
- 1.3. Only log actual failures at debug level
- 1.4. No multi-line diagnostics for normal operation
- 1.5. Tier information only shown on failure (not every page)

### 2. Modern CLI/UX for 2026
**As a** Primr user  
**I want** a modern CLI experience  
**So that** the tool feels professional and polished

**Acceptance Criteria:**
- 2.1. Clean inline updates (no scrolling spam)
- 2.2. Color-coded status (success=green, warning=yellow, error=red)
- 2.3. Progress bar or percentage indicator
- 2.4. Summary stats at end (not per-page noise)
- 2.5. Verbose mode available for debugging

### 3. Content-First Messaging
**As a** Primr user  
**I want** messaging that reflects content quality over speed  
**So that** I understand the tool's priorities

**Acceptance Criteria:**
- 3.1. No "slow page" warnings for pages <30s
- 3.2. Success messages emphasize content quality (e.g., "✓ 2.4KB extracted")
- 3.3. Failure messages explain why (blocked, timeout, no content)
- 3.4. Summary shows quality metrics (pages scraped, content extracted, avg quality)

## Technical Requirements

### 1. Remove Excessive Logging
**File:** `src/primr/data/scrape.py` (lines 335-345)

**Current:**
```python
if elapsed > 8.0:
    logger.warning(
        f"WARNING: Slow page ({elapsed:.1f}s): {url}\n"
        f"  Tier: {result.tier}\n"
        f"  Status: {'success' if result.success else 'failed'}\n"
        f"  Attempts: {len(result.attempts)}"
    )
```

**Fix:**
- Remove WARNING logs for successful pages
- Only log failures at debug level
- Keep timing info for verbose mode

### 2. Simplify Progress Display
**File:** `src/primr/utils/console.py` (lines 216-237)

**Current:**
```python
def scrape_progress(current: int, total: int, url: str, tier: str = None):
    msg = f"Scraping {current}/{total} {url}"
    if tier:
        msg += f" ({tier})"
    print(msg)
```

**Fix:**
- Inline updates (overwrite previous line)
- Show timing for slow pages (>10s)
- No tier info unless failure
- Format: `Scraping 3/50 /investors/financial-reports (9s)`

### 3. Add Summary Stats
**File:** `src/primr/data/scrape.py` (end of `fetch_web_content()`)

**Add:**
- Total pages scraped
- Total content extracted (KB)
- Average page time
- Success rate
- Quality metrics (if available)

## Non-Goals

- Don't change scraping logic (tier selection, timeouts, etc.)
- Don't change error handling (just presentation)
- Don't add complex UI frameworks (keep it simple)
- Don't remove verbose mode (still needed for debugging)

## Success Metrics

- No WARNING logs for successful pages
- Clean inline progress (no scrolling spam)
- User doesn't cancel runs due to poor UX
- Summary stats show content quality metrics
- Verbose mode still available for debugging

## Files to Modify

1. `src/primr/data/scrape.py` - Remove excessive logging
2. `src/primr/utils/console.py` - Simplify progress display
3. `src/primr/data/scrape.py` - Add summary stats

## Testing Strategy

1. **Manual Tests:**
   - Run `primr "Torex Gold Resources Inc." https://torexgold.com/`
   - Verify clean progress output
   - Verify no WARNING spam
   - Verify summary stats at end

2. **Visual Tests:**
   - Compare before/after screenshots
   - Verify inline updates work
   - Verify color coding works

3. **Regression Tests:**
   - Verify verbose mode still works
   - Verify error messages still clear
   - Verify trace logging still works

## Example Output

### Before (Current - "looks like shit")
```
✓ 82 links → 50 selected
Scraping 2/50 /about-us/our-company
WARNING: Slow page (9.0s): https://torexgold.com/about-us/our-company
  Tier: playwright
  Status: success
  Attempts: 1
Scraping 3/50 /investors/financial-reports (9s)
WARNING: Slow page (11.2s): https://torexgold.com/investors/financial-reports
  Tier: playwright
  Status: success
  Attempts: 1
```

### After (Proposed - Clean)
```
✓ 82 links → 50 selected
Scraping 3/50 /investors/financial-reports (11s)
...
✓ 34/50 pages scraped (68% success)
  Content: 156KB extracted
  Avg time: 8.2s/page
  Quality: 89% high-quality content
```

## User Feedback

> "i cancelled again... surely there is a better way to do CLI / UI/X in 2026?"

> "i mean the problem is NOT that it takes time to get the content though... like I want the content but at the same time dont make it take longer than it needs to? and I need modern UI/X for a cli app for 2026... not like fucking errors every 2 seconds?"

> "its OK if it takes 21 seconds to scrape a page... read the readme. Explain why its importan to GET THE CONTENT not fail fucking as fast as possible."

## Core Mission Alignment

From README:
- **Purpose:** Generate comprehensive company intelligence briefs for consultants
- **Pipeline:** 25-40 minutes, $0.80-1.50 per run
- **Philosophy:** "Quality matters more than quantity. 34 pages from a protected site typically yields more useful content than 100 pages from a poorly-structured site"
- **Scrape Mode:** 5-10 minutes, $0.01-0.05 (still substantial)

**Key Insight:** A few extra seconds per page is irrelevant in a 25-40 minute pipeline. Getting quality content is paramount.
