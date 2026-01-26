# CLI/UX Enhancement - Design

## Overview

Redesign CLI output to reflect Primr's mission: comprehensive company intelligence where content quality matters more than speed. Remove excessive logging noise and provide clean, modern progress display.

## Problem Analysis

### Current State
```
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

**Problems:**
1. WARNING logs for successful pages (even if slow)
2. Multi-line diagnostics for every page >8s
3. Tier information shown for every page
4. Scrolling spam makes it hard to see progress
5. User perception: "looks like shit"

### Root Cause
The logging was designed for debugging, not production use. It treats slow-but-successful pages as warnings, which is wrong for Primr's use case.

**Philosophy Mismatch:**
- Current: Fast failure is success
- Correct: Getting content is success (even if slow)

## Solution Design

### 1. Remove Excessive Logging

**File:** `src/primr/data/scrape.py` (lines 335-345)

**Before:**
```python
if elapsed > 8.0:
    logger.warning(
        f"WARNING: Slow page ({elapsed:.1f}s): {url}\n"
        f"  Tier: {result.tier}\n"
        f"  Status: {'success' if result.success else 'failed'}\n"
        f"  Attempts: {len(result.attempts)}"
    )
```

**After:**
```python
# Only log actual failures (not slow successes)
if not result.success:
    logger.debug(
        f"Failed to scrape {url}: {result.error} "
        f"(tried {len(result.attempts)} tiers)"
    )
```

**Rationale:**
- Slow-but-successful pages are NORMAL for protected sites
- WARNING logs should be for actual problems
- Debug level is appropriate for failures (verbose mode)
- Timing info still available in trace logs

### 2. Simplify Progress Display

**File:** `src/primr/utils/console.py` (lines 216-237)

**Before:**
```python
def scrape_progress(current: int, total: int, url: str, tier: str = None):
    """Show scraping progress."""
    msg = f"Scraping {current}/{total} {url}"
    if tier:
        msg += f" ({tier})"
    print(msg)
```

**After:**
```python
def scrape_progress(
    current: int,
    total: int,
    url: str,
    elapsed: float = None,
    success: bool = True,
):
    """Show scraping progress with inline updates."""
    # Extract path from URL for cleaner display
    from urllib.parse import urlparse
    path = urlparse(url).path or "/"
    
    # Build message
    msg = f"Scraping {current}/{total} {path}"
    
    # Add timing for slow pages (>10s)
    if elapsed and elapsed > 10.0:
        msg += f" ({elapsed:.0f}s)"
    
    # Add failure indicator
    if not success:
        msg += " ✗"
    
    # Inline update (overwrite previous line)
    print(f"\r{msg:<80}", end="", flush=True)
```

**Rationale:**
- Inline updates reduce scrolling spam
- Show timing only for slow pages (>10s)
- Path instead of full URL is cleaner
- Success/failure indicator without noise
- 80 char width for clean overwrite

### 3. Add Summary Stats

**File:** `src/primr/data/scrape.py` (end of `fetch_web_content()`)

**Add after scraping loop:**
```python
# Print newline after inline progress
print()

# Calculate summary stats
total_scraped = len([r for r in results if r.success])
total_failed = len([r for r in results if not r.success])
success_rate = (total_scraped / len(results) * 100) if results else 0

# Calculate content stats
total_content_kb = sum(
    len(r.extracted_text or "") / 1024
    for r in results if r.success
)

# Calculate timing stats
avg_time = sum(
    r.elapsed_ms / 1000
    for r in results if r.elapsed_ms
) / len(results) if results else 0

# Print summary
console.success(
    f"✓ {total_scraped}/{len(results)} pages scraped "
    f"({success_rate:.0f}% success)"
)
console.info(f"  Content: {total_content_kb:.0f}KB extracted")
console.info(f"  Avg time: {avg_time:.1f}s/page")

if total_failed > 0:
    console.warning(f"  {total_failed} pages failed (see logs for details)")
```

**Rationale:**
- Summary shows what matters: content extracted
- Success rate gives quality signal
- Average time shows performance
- Failed pages noted but not emphasized

## Implementation Details

### Color Coding

Use existing console utilities:
```python
# src/primr/utils/console.py
def success(msg: str):
    """Print success message (green)."""
    print(f"\033[92m{msg}\033[0m")

def warning(msg: str):
    """Print warning message (yellow)."""
    print(f"\033[93m{msg}\033[0m")

def error(msg: str):
    """Print error message (red)."""
    print(f"\033[91m{msg}\033[0m")

def info(msg: str):
    """Print info message (default color)."""
    print(msg)
```

### Verbose Mode

Keep verbose mode for debugging:
```python
# In scrape.py
if verbose:
    logger.info(
        f"Page {current}/{total}: {url}\n"
        f"  Tier: {result.tier}\n"
        f"  Time: {elapsed:.1f}s\n"
        f"  Content: {len(result.extracted_text or '')} chars\n"
        f"  Attempts: {len(result.attempts)}"
    )
```

### Trace Logging

Keep trace logging unchanged:
```python
# Trace logs still capture everything
if self.trace_logger:
    self.trace_logger.log(result)
```

## Content Quality vs Speed Tradeoffs

### Current Timeout Logic Review

**File:** `src/primr/data/scraping/orchestrator.py`

#### 1. `max_page_time` (line 73)
```python
max_page_time: float = 30.0  # Current default
```

**Analysis:**
- 30s is reasonable for most pages
- But protected sites may need more time
- Vision tier alone needs 30s for LLM extraction
- Recommendation: Increase to 45s

**Proposed Change:**
```python
max_page_time: float = 45.0  # Allow more time for quality content
```

**Rationale:**
- Vision tier needs 30s for LLM extraction
- Protected sites need time for challenge solving
- 45s allows 2-3 tier attempts with generous timeouts
- Still fast enough (45s × 50 pages = 37.5 minutes max)

#### 2. `use_fast_timeout` Logic (lines 247-267)
```python
# Current: Reduce ALL tier timeouts to 5s when best_tier known
if host_state.best_tier:
    use_fast_timeout = True
    # ...
    if use_fast_timeout and not is_browser_tier:
        effective_timeout = min(tier.timeout, 5.0)
```

**Analysis:**
- Good: Speeds up HTTP tiers when we know they work
- Good: Excludes browser tiers (they need full timeout)
- Risk: May be too aggressive (5s might not be enough)
- Recommendation: Keep as-is (already fixed for browser tiers)

**No Change Needed:** Already working correctly after browser tier fix.

#### 3. "FAST FAIL" Logic (lines 420-426)
```python
# FAST FAIL: If we got HTML but content is too short (50-199 chars),
# the page is likely a stub/redirect, not a scraping issue.
# Don't waste time trying other tiers.
if extracted and 50 < len(extracted) < 200:
    logger.debug(f"Fast fail: Page has content but too short ({len(extracted)} chars)")
    break  # Exit tier loop, return failure
```

**Analysis:**
- Good: Avoids wasting time on stub pages
- Good: 50-199 char range is reasonable for stubs
- Risk: Might give up on pages that need more aggressive extraction
- Recommendation: Keep as-is (it's a good optimization)

**No Change Needed:** This is a smart optimization for stub pages.

### Tier Timeout Review

**File:** `src/primr/data/scraping/config.py` (lines 180-195)

```python
DEFAULT_TIMEOUT_REQUESTS = 10       # Simple HTTP
DEFAULT_TIMEOUT_HTTPX = 10          # HTTP/2
DEFAULT_TIMEOUT_CURL_CFFI = 10      # TLS fingerprint
DEFAULT_TIMEOUT_DRISSION = 15       # Driverless browser
DEFAULT_TIMEOUT_PLAYWRIGHT = 15     # Full browser
DEFAULT_TIMEOUT_DRISSION_STEALTH = 20  # Stealth browser
DEFAULT_TIMEOUT_PLAYWRIGHT_AGGRESSIVE = 15  # Interactive browser
DEFAULT_TIMEOUT_VISION = 30         # Vision AI (LLM extraction)
```

**Analysis:**
- HTTP tiers (10s): Reasonable - if they work, they work fast
- Browser tiers (15-20s): Reasonable - allows JS rendering + challenges
- Vision tier (30s): Necessary - LLM extraction takes time
- Total potential: 125s (but max_page_time limits to 45s)

**Recommendation:** Keep as-is. Timeouts are generous and appropriate.

### Summary of Changes

**Increase `max_page_time`:**
```python
# orchestrator.py line 73
max_page_time: float = 45.0  # Was 30.0
```

**Rationale:**
- Allows vision tier to complete (30s)
- Allows 2-3 tier attempts with full timeouts
- Still fast enough for 50-page scrapes (37.5 min max)
- Aligns with mission: content quality > speed

**Keep Everything Else:**
- `use_fast_timeout` logic: Already fixed for browser tiers
- "FAST FAIL" logic: Smart optimization for stub pages
- Tier timeouts: Generous and appropriate
- Circuit breaker: Good for avoiding repeated failures

## Testing Strategy

### Manual Tests
```bash
# Test with real site
primr "Torex Gold Resources Inc." https://torexgold.com/

# Expected output:
✓ 82 links → 50 selected
Scraping 34/50 /investors/financial-reports (12s)
✓ 34/50 pages scraped (68% success)
  Content: 156KB extracted
  Avg time: 8.2s/page
```

### Visual Tests
1. Run scrape and verify:
   - No WARNING logs for successful pages
   - Clean inline progress updates
   - Summary stats at end
   - Color coding works

2. Run with `--verbose` and verify:
   - Detailed logs still available
   - Tier information shown
   - Timing details shown

### Regression Tests
1. Verify trace logging still works
2. Verify error messages still clear
3. Verify verbose mode still works
4. Verify scraping logic unchanged

## Performance Impact

### Before
- WARNING logs every 2 seconds
- Multi-line diagnostics for every page >8s
- User cancels run due to poor UX

### After
- Clean inline progress
- Summary stats at end
- No noise for normal operation
- User can see progress clearly

### Timing Impact
- `max_page_time`: 30s → 45s (+15s per page max)
- Impact: Allows more tiers to complete
- Benefit: Higher success rate, more content
- Cost: Slightly longer scrapes (but still <40 min for full pipeline)

## Edge Cases

### 1. All Pages Fail
```
✓ 82 links → 50 selected
Scraping 50/50 /contact-us ✗
✓ 0/50 pages scraped (0% success)
  Content: 0KB extracted
  50 pages failed (see logs for details)
```

### 2. Very Slow Pages
```
Scraping 3/50 /investors/annual-report (45s)
```
Shows timing for pages >10s, helps user understand progress.

### 3. Verbose Mode
```bash
primr "Company" https://example.com --verbose

# Shows detailed logs:
Page 3/50: https://example.com/about
  Tier: playwright
  Time: 12.3s
  Content: 2456 chars
  Attempts: 1
```

## Files Modified

1. **`src/primr/data/scrape.py`**
   - Remove excessive WARNING logs (lines 335-345)
   - Add summary stats at end of `fetch_web_content()`
   - Keep verbose mode for debugging

2. **`src/primr/utils/console.py`**
   - Simplify `scrape_progress()` (lines 216-237)
   - Add inline update support
   - Add color coding helpers

3. **`src/primr/data/scraping/orchestrator.py`**
   - Increase `max_page_time` from 30s to 45s (line 73)
   - Keep other timeout logic unchanged

4. **`.kiro/specs/cli-ux-enhancement/requirements.md`**
   - Requirements document

5. **`.kiro/specs/cli-ux-enhancement/design.md`**
   - This design document

## Success Criteria

- [x] Requirements document created
- [x] Design document created
- [x] Timeout logic reviewed (no changes needed except max_page_time)
- [x] Remove excessive logging (COMPLETED in previous context transfer)
- [x] Simplify progress display (COMPLETED in previous context transfer)
- [x] Add summary stats (COMPLETED in previous context transfer - basic version)
- [x] Increase max_page_time to 45s (COMPLETED)
- [ ] Manual test passes (pending user verification)
- [ ] No UX complaints (pending user feedback)

## Implementation Complete

All core tasks have been completed:

1. **Excessive logging removed** - No more WARNING spam for slow-but-successful pages
2. **Progress display simplified** - Clean inline updates: `Scraping 3/50 /path (9s)`
3. **Summary stats added** - Shows: `✓ 34/50 pages scraped (2m 15s)`
4. **max_page_time increased** - From 30s to 45s (allows vision tier to complete)

**Files modified:**
- `src/primr/data/scrape.py` - Removed excessive logging
- `src/primr/utils/console.py` - Simplified progress display
- `src/primr/data/scraping/orchestrator.py` - Increased max_page_time to 45s
- `src/primr/data/scraping/config.py` - Updated comment

**Ready for testing:** `primr "Torex Gold Resources Inc." https://torexgold.com/`

## Next Steps

1. Implement logging changes in `scrape.py`
2. Implement progress display changes in `console.py`
3. Implement summary stats in `scrape.py`
4. Increase `max_page_time` in `orchestrator.py`
5. Test with `primr "Torex Gold Resources Inc." https://torexgold.com/`
6. Get user feedback

## Core Mission Alignment

This design aligns with Primr's mission:
- **Content Quality > Speed**: Increased `max_page_time` to 45s
- **Professional UX**: Clean, minimal output without noise
- **Consultant-Grade**: Summary stats show quality metrics
- **Patience**: No warnings for slow-but-successful pages
- **Transparency**: Verbose mode still available for debugging

From README:
> "Quality matters more than quantity. 34 pages from a protected site typically yields more useful content than 100 pages from a poorly-structured site."

This design embodies that philosophy.
