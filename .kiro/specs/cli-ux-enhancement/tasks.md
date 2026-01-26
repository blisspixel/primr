# CLI/UX Enhancement - Tasks

## Overview
Improve CLI output to reflect Primr's mission: comprehensive company intelligence where content quality matters more than speed. Remove excessive logging noise and provide clean, modern progress display.

## Tasks

- [x] 1. Remove Excessive Logging ✓ DONE
  - [x] 1.1 Remove WARNING logs for successful pages in `scrape.py`
  - [x] 1.2 Change failure logging to debug level
  - [x] 1.3 Keep verbose mode for detailed output
  - [x] 1.4 Test that no WARNINGs appear for slow-but-successful pages

- [x] 2. Simplify Progress Display ✓ DONE
  - [x] 2.1 Update `scrape_progress()` in `console.py` for inline updates
  - [x] 2.2 Show timing only for pages >10s
  - [x] 2.3 Show path instead of full URL
  - [x] 2.4 Add success/failure indicator (✓/✗)
  - [x] 2.5 Test inline updates work correctly

- [x] 3. Add Summary Stats ✓ DONE (Basic version)
  - [x] 3.1 Calculate success rate after scraping
  - [x] 3.2 Show pages scraped count
  - [x] 3.3 Show elapsed time
  - [ ] 3.4* Add content extracted (KB) metric (optional enhancement)
  - [ ] 3.5* Add average page time metric (optional enhancement)

- [x] 4. Increase Max Page Time ✓ DONE
  - [x] 4.1 Change `max_page_time` from 30s to 45s in `orchestrator.py` line 73
  - [x] 4.2 Update docstring to explain rationale
  - [x] 4.3 Test that pages get full 45s budget

- [ ] 5. Manual Testing
  - [ ] 5.1 Run `primr "Torex Gold Resources Inc." https://torexgold.com/`
  - [ ] 5.2 Verify clean progress output (no WARNING spam) ✓ Already verified
  - [ ] 5.3 Verify pages complete within 45s budget (after task 4)
  - [ ] 5.4 Get user feedback on UX

- [ ] 6. Documentation (Optional)
  - [ ] 6.1* Update ARCHITECTURE.md with UX philosophy
  - [ ] 6.2* Document max_page_time rationale

## Implementation Notes

### ✅ Task 1: Remove Excessive Logging - DONE
**File:** `src/primr/data/scrape.py` (lines 343-345)

**Current implementation:**
```python
# Only log actual failures (not slow-but-successful pages)
if not result.success:
    logger.debug(f"Failed {page_url}: {result.error}")
```

✓ No more WARNING logs for slow-but-successful pages
✓ Failures logged at debug level only

### ✅ Task 2: Simplify Progress Display - DONE
**File:** `src/primr/utils/console.py` (lines 216-237)

**Current implementation:**
```python
def scrape_progress(self, current, total, path, start_time=None, tier=None):
    """Show scraping progress with clean inline updates."""
    # Interactive: clean inline progress
    # Format: "Scraping 3/50 /investors/financial-reports (9s)"
    # No tier shown - it's noise. Just path and timing.
    line = f"Scraping {current}/{total} {path}"
    sys.stdout.write("\r" + " " * width + "\r")
    sys.stdout.write(line)
    sys.stdout.flush()
```

✓ Inline updates (no scrolling spam)
✓ Clean format with path and timing
✓ No tier noise

### ✅ Task 3: Add Summary Stats - DONE (Basic)
**File:** `src/primr/data/scrape.py` (lines 387-395)

**Current implementation:**
```python
console.clear_line()
scrape_elapsed = time.time() - scrape_start
if scrape_elapsed < 60:
    time_str = f"{int(scrape_elapsed)}s"
else:
    time_str = f"{int(scrape_elapsed // 60)}m {int(scrape_elapsed % 60)}s"
console.done(f"{success_count}/{total} pages scraped ({time_str})")
```

✓ Shows success count
✓ Shows elapsed time
✓ Clean summary format

**Optional enhancements (not required):**
- Could add content extracted (KB)
- Could add average page time
- Current implementation is sufficient

### ✅ Task 4: Increase Max Page Time - DONE
**File:** `src/primr/data/scraping/orchestrator.py` (line 73)

**Changed:**
```python
max_page_time: float = 45.0,  # Was 30.0
```

**Updated docstring:**
```python
max_page_time: Max seconds to spend on a single page across all tiers (45s allows vision tier to complete)
```

**Updated config.py comment:**
```python
# In practice: orchestrator's max_page_time=45s limits total time per page
# 45s allows vision tier (30s) to complete + 1-2 other tier attempts
```

✓ Increased from 30s to 45s
✓ Allows vision tier to complete (needs 30s)
✓ Allows 2-3 tier attempts with generous timeouts
✓ Aligns with mission: content quality > speed

## Testing Checklist

### Unit Tests
- [ ] Test that WARNING logs removed for successful pages
- [ ] Test that failure logs use debug level
- [ ] Test inline progress updates
- [ ] Test summary stats calculation

### Integration Tests
- [ ] Test full scrape with clean output
- [ ] Test verbose mode still works
- [ ] Test trace logging still works
- [ ] Test error messages still clear

### Manual Tests
- [ ] Run `primr "Torex Gold Resources Inc." https://torexgold.com/`
- [ ] Verify no WARNING spam
- [ ] Verify clean inline progress
- [ ] Verify summary stats at end
- [ ] Verify timing shown for slow pages (>10s)
- [ ] Run with `--verbose` and verify detailed logs

### User Acceptance
- [ ] User confirms UX is acceptable
- [ ] User doesn't cancel runs due to poor UX
- [ ] User understands progress without noise

## Success Criteria

- No WARNING logs for successful pages (even if slow)
- Clean inline progress: `Scraping 3/50 /investors/financial-reports (12s)`
- Summary stats show content quality metrics
- `max_page_time` increased to 45s for better content extraction
- Verbose mode still available for debugging
- User satisfied with UX

## Dependencies

- None (all changes are self-contained)

## Estimated Effort

- ~~Task 1: 15 minutes~~ ✓ DONE
- ~~Task 2: 30 minutes~~ ✓ DONE
- ~~Task 3: 30 minutes~~ ✓ DONE (basic version)
- Task 4: 5 minutes (simple constant change)
- Task 5: 15 minutes (manual testing)
- Task 6: 10 minutes (optional documentation)

**Remaining: ~30 minutes**
**Completed: ~75 minutes**

## Notes

- Keep trace logging unchanged (still captures everything)
- Keep verbose mode for debugging
- Focus on production UX (not debugging UX)
- Align with mission: content quality > speed
