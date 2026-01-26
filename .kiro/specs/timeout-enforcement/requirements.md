# Timeout Enforcement Fix - Requirements

## Problem Statement

DrissionPage stealth tier is taking 113-128 seconds per page when configured for 20s timeout. This makes scraping unacceptably slow.

**Root Cause:**
- Tier has `timeout=20s` parameter
- But `wait_for_clearance()` uses `max_challenge_wait=45s` (hardcoded default)
- Result: 20s navigate + 45s wait = 65s minimum per page
- With retries and overhead: 113-128s actual

**User Impact:**
- "this looks like shit?" - User cancelled run due to poor performance
- Pages taking 2+ minutes each is unacceptable
- Orchestrator's `max_page_time=45s` is not enforced within tiers

## User Stories

### 1. Respect Tier Timeout
**As a** Primr user  
**I want** each tier to respect its configured timeout  
**So that** slow tiers don't waste time on pages that won't work

**Acceptance Criteria:**
- 1.1. DrissionPage stealth tier with `timeout=20s` completes in ≤25s (20s + 5s overhead)
- 1.2. `wait_for_clearance()` respects the tier's timeout budget
- 1.3. No hardcoded waits that exceed tier timeout
- 1.4. Timeout warnings show actual vs expected time

### 2. Enforce Max Page Time
**As a** Primr user  
**I want** the orchestrator to enforce `max_page_time` within tier execution  
**So that** no single page hangs the entire scraping run

**Acceptance Criteria:**
- 2.1. If tier exceeds remaining page time budget, it's interrupted
- 2.2. Orchestrator logs which tier was interrupted and why
- 2.3. Next tier gets remaining time budget (if any)
- 2.4. If no time left, page fails with clear timeout message

### 3. Fast Failure Detection
**As a** Primr user  
**I want** tiers to fail fast when they won't work  
**So that** we can try the next tier quickly

**Acceptance Criteria:**
- 3.1. Challenge wait time is capped at tier timeout
- 3.2. If challenge doesn't clear in timeout, fail immediately
- 3.3. Don't wait full 45s if tier timeout is 20s
- 3.4. Log why challenge wait was cut short

## Technical Requirements

### 1. Fix DrissionPage Stealth Tier
- Calculate `max_challenge_wait` from tier timeout
- Formula: `max_challenge_wait = min(timeout * 0.7, 30)` (70% of timeout, max 30s)
- Example: 20s timeout → 14s challenge wait
- Example: 60s timeout → 30s challenge wait (capped)

### 2. Add Timeout Budget Tracking
- Track time spent in tier so far
- Calculate remaining budget before each operation
- Pass remaining budget to operations (navigate, wait_for_clearance, etc.)

### 3. Add Timeout Enforcement Wrapper
- Wrap tier execution in timeout handler
- If tier exceeds timeout, interrupt and return timeout error
- Log which operation was interrupted

## Non-Goals

- Don't change orchestrator's tier selection logic
- Don't change circuit breaker logic
- Don't change rate limiting
- Don't change other tiers (only DrissionPage stealth for now)

## Success Metrics

- DrissionPage stealth tier completes in ≤25s (down from 113s)
- Pages complete within `max_page_time=45s` budget
- No timeout warnings for tiers that complete within budget
- Clear timeout messages when budget exceeded

## Files to Modify

1. `src/primr/data/scraping/browsers.py` - Fix `scrape_with_drissionpage_stealth()`
2. `src/primr/data/scraping/orchestrator.py` - Add timeout enforcement (optional)
3. `tests/test_scrape.py` - Add timeout enforcement tests

## Testing Strategy

1. **Unit Tests:**
   - Test `scrape_with_drissionpage_stealth()` with 20s timeout
   - Verify it completes in ≤25s
   - Verify `wait_for_clearance()` uses calculated timeout

2. **Integration Tests:**
   - Test against real site with challenges (e.g., Cloudflare)
   - Verify tier respects timeout even with challenges
   - Verify orchestrator enforces `max_page_time`

3. **Manual Tests:**
   - Run `primr "Torex Gold Resources Inc." https://torexgold.com/`
   - Verify pages complete in reasonable time
   - Verify no "this looks like shit?" performance issues
