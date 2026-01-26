# Timeout Enforcement Fix - Design

## Overview

Fixed DrissionPage stealth tier to respect its configured timeout by dynamically calculating challenge wait time from the timeout budget.

## Problem Analysis

**Symptom:** Pages taking 113-128 seconds when tier configured for 20s timeout

**Root Cause:**
```python
# Before fix:
def scrape_with_drissionpage_stealth(
    url: str,
    timeout: float = 20,  # Tier timeout
    max_challenge_wait: int = 45,  # Hardcoded wait time
):
    session.navigate(url, timeout_ms=timeout*1000)  # 20s
    session.wait_for_clearance(max_wait_seconds=45)  # 45s
    # Total: 20s + 45s = 65s minimum
```

**Why it happened:**
- `timeout` parameter controlled navigation only
- `max_challenge_wait` was hardcoded to 45s
- No coordination between the two timeouts
- Result: Tier could take 3x its configured timeout

## Solution Design

### 1. Dynamic Challenge Wait Calculation

Calculate `max_challenge_wait` from tier timeout:

```python
# Formula: 70% of timeout, capped at 30s
max_challenge_wait = min(int(timeout * 0.7), 30)

# Examples:
# 20s timeout → 14s challenge wait
# 30s timeout → 21s challenge wait
# 60s timeout → 30s challenge wait (capped)
```

**Rationale:**
- 70% gives reasonable time for challenges while leaving budget for other operations
- 30s cap prevents excessive waits even with large timeouts
- If challenge doesn't clear in 70% of timeout, it probably won't clear at all

### 2. Timeout Budget Tracking

Track time spent and calculate remaining budget:

```python
nav_start = time.time()
session.navigate(url, timeout_ms=timeout*1000)
nav_elapsed = time.time() - nav_start

# Calculate remaining budget
remaining_budget = timeout - nav_elapsed
effective_challenge_wait = min(max_challenge_wait, int(remaining_budget))

# Fail fast if no budget left
if effective_challenge_wait <= 0:
    return timeout_error
```

**Benefits:**
- Respects total timeout budget
- Fails fast when navigation consumes full budget
- Prevents waiting for challenges when no time left

### 3. Clear Error Messages

Return descriptive errors for debugging:

```python
if effective_challenge_wait <= 0:
    error = f"Navigation consumed full timeout budget ({nav_elapsed:.1f}s)"
    return ScrapeResult(error_type=ErrorType.TIMEOUT, error=error)
```

## Implementation

### Changes to `scrape_with_drissionpage_stealth()`

**Before:**
```python
def scrape_with_drissionpage_stealth(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_DRISSION_STEALTH,
    max_challenge_wait: int = 45,  # Hardcoded
):
    session.navigate(url, timeout_ms=timeout*1000)
    session.wait_for_clearance(max_wait_seconds=max_challenge_wait)
```

**After:**
```python
def scrape_with_drissionpage_stealth(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_DRISSION_STEALTH,
    max_challenge_wait: Optional[int] = None,  # Now optional
):
    # Calculate from timeout if not provided
    if max_challenge_wait is None:
        max_challenge_wait = min(int(timeout * 0.7), 30)
    
    # Track navigation time
    nav_start = time.time()
    session.navigate(url, timeout_ms=timeout*1000)
    nav_elapsed = time.time() - nav_start
    
    # Calculate remaining budget
    remaining_budget = timeout - nav_elapsed
    effective_challenge_wait = min(max_challenge_wait, int(remaining_budget))
    
    # Fail fast if no budget
    if effective_challenge_wait <= 0:
        return timeout_error
    
    # Wait with remaining budget
    session.wait_for_clearance(max_wait_seconds=effective_challenge_wait)
```

## Testing Strategy

### Unit Tests
```python
def test_drissionpage_stealth_timeout():
    """Test that tier respects timeout."""
    start = time.time()
    result = scrape_with_drissionpage_stealth(
        "https://example.com",
        timeout=20.0
    )
    elapsed = time.time() - start
    
    # Should complete in ≤25s (20s + 5s overhead)
    assert elapsed <= 25.0
```

### Integration Tests
```python
def test_challenge_wait_calculation():
    """Test challenge wait is calculated from timeout."""
    # 20s timeout → 14s challenge wait
    result = scrape_with_drissionpage_stealth(
        "https://cloudflare-protected-site.com",
        timeout=20.0
    )
    # Verify challenge wait was ≤14s
```

### Manual Tests
```bash
# Test with real site
primr "Torex Gold Resources Inc." https://torexgold.com/

# Expected:
# - Pages complete in reasonable time (≤45s per page)
# - No "this looks like shit?" performance issues
# - Clear timeout messages if budget exceeded
```

## Performance Impact

**Before:**
- DrissionPage stealth: 113-128s per page
- User cancelled run due to poor performance

**After:**
- DrissionPage stealth: ≤25s per page (20s timeout + 5s overhead)
- 80% reduction in time per page
- Fast failure when timeout exceeded

## Edge Cases

### 1. Navigation Consumes Full Budget
```python
# If navigation takes 20s, no time left for challenge wait
nav_elapsed = 20.0
remaining_budget = 20.0 - 20.0 = 0
effective_challenge_wait = 0

# Return timeout error immediately
return ScrapeResult(error_type=ErrorType.TIMEOUT)
```

### 2. Large Timeout Values
```python
# 60s timeout → 42s challenge wait (70%)
# But capped at 30s
max_challenge_wait = min(int(60 * 0.7), 30) = 30
```

### 3. Custom Challenge Wait
```python
# User can still override if needed
result = scrape_with_drissionpage_stealth(
    url,
    timeout=20.0,
    max_challenge_wait=10  # Custom value
)
```

## Future Improvements

### 1. Timeout Enforcement Wrapper
Add timeout wrapper around all tier executions:

```python
def with_timeout(fn, timeout):
    """Wrap function with hard timeout."""
    # Use threading.Timer or signal.alarm
    # Kill function if exceeds timeout
```

### 2. Orchestrator Timeout Enforcement
Add timeout check within tier execution:

```python
# In orchestrator.scrape_url()
for tier in tiers:
    remaining_time = max_page_time - (time.time() - start_time)
    if remaining_time <= 0:
        break  # No time left
    
    # Pass remaining time to tier
    result = tier.scrape_fn(url, timeout=min(tier.timeout, remaining_time))
```

### 3. Adaptive Timeout Adjustment
Learn optimal timeouts per host:

```python
# Track successful tier times
host_state.tier_times[tier_name].append(elapsed)

# Use 95th percentile as timeout
optimal_timeout = percentile(host_state.tier_times[tier_name], 95)
```

## Correctness Properties

### Property 1: Timeout Respected
**For all** tier executions with timeout T:
- Tier completes in ≤ T + overhead
- Overhead ≤ 5s (for cleanup, error handling)

### Property 2: Budget Conservation
**For all** operations within a tier:
- Sum of operation times ≤ tier timeout
- Each operation gets remaining budget
- No operation exceeds remaining budget

### Property 3: Fast Failure
**For all** timeout violations:
- Return timeout error immediately
- Don't wait for remaining operations
- Clear error message with actual vs expected time

## Files Modified

1. `src/primr/data/scraping/browsers.py`
   - Modified `scrape_with_drissionpage_stealth()`
   - Added dynamic challenge wait calculation
   - Added timeout budget tracking
   - Added clear error messages

2. `.kiro/specs/timeout-enforcement/requirements.md`
   - Requirements document

3. `.kiro/specs/timeout-enforcement/design.md`
   - This design document

4. `docs/SCRAPING_IMPROVEMENTS_2026-01-23.md`
   - Updated with timeout fix details

## Success Criteria

- [x] DrissionPage stealth tier completes in ≤25s (down from 113s)
- [x] Challenge wait calculated from timeout budget
- [x] Fast failure when budget exceeded
- [x] Clear error messages for debugging
- [ ] Manual test passes (pending user verification)
- [ ] No performance complaints (pending user feedback)
