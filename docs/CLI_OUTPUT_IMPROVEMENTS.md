# CLI Output Improvements - January 2026

## Overview

This document tracks improvements made to the CLI output system to reduce noise, improve clarity, and provide better user experience during long-running research operations.

## Issues Identified

From user-provided CLI output (68-minute Lilly run), we identified:

1. **Interleaved status messages** - "Deep Research in progress" interrupts other operations
2. **Excessive WARNING spam** - 10 WARNING messages for API retries (too verbose)
3. **Duplicate/redundant messages** - "Research started" appears 3 times
4. **Inconsistent formatting** - Mix of `+`, `>`, `.` prefixes
5. **Missing context for long waits** - No reassurance during API errors
6. **Unclear phase boundaries** - Relationship between phases unclear

## Changes Implemented

### Phase 1: High Priority Fixes

#### 1. Reduced Retry Noise (`src/primr/ai/deep_research.py`)

**Before:**
```
WARNING: Transient error during polling (attempt 1/5), waiting 10s: Error code: 500
API hiccup, retrying in 10s
WARNING: Transient error during polling (attempt 2/5), waiting 20s: Error code: 500
API hiccup, retrying in 20s
WARNING: Transient error during polling (attempt 3/5), waiting 30s: Error code: 500
API hiccup, retrying in 30s
```

**After:**
```
API delays detected, retrying...
```

**Changes:**
- Only show progress message on first retry (not all 5 attempts)
- Changed message from "API hiccup, retrying in Xs (N/5)..." to "API delays detected, retrying..."
- Applied to both occurrences in deep_research.py (lines ~627 and ~2547)

#### 2. Increased Heartbeat Interval (`src/primr/core/research_agent.py`)

**Before:** 30 seconds
**After:** 90 seconds

**Rationale:** Reduces frequency of ". Deep Research in progress (Xm Ys)" messages during long operations

#### 3. Enhanced Phase Banners (`src/primr/utils/console.py`)

**Before:**
```
> Phase 1: Data Collection
```

**After:**
```
===============================================================
PHASE 1: DATA COLLECTION
===============================================================

Website scraping + web search + AI analysis
```

**Changes:**
- Added ASCII separator lines (63 `=` characters)
- Format: `PHASE N: TITLE` in bold/cyan
- Includes description below separator
- Consistent visual hierarchy

#### 4. Removed Duplicate "Research started" Messages (`src/primr/ai/deep_research.py`)

**Before:** "Research started" appeared 3 times in output
**After:** Single "Research started" message

**Changes:**
- Removed redundant progress callbacks that showed "Research started (ID: ...)"
- Added comments explaining why messages are skipped
- Kept single message at the start of research

### Phase 2: Standardization (Planned)

#### Message Prefix Standards

- `>` - Starting operations (e.g., "> Working folder: ...")
- `+` - Completions (e.g., "+ 15 sections complete")
- `.` - Progress updates (e.g., ". Searching sources")
- `!` - Warnings (user-actionable only)

#### Indentation

- Main operations: No indentation
- Sub-operations: 2 spaces
- Progress details: 4 spaces

### Phase 3: Polish (Planned)

- Add blank lines between major sections
- Consider color support for phase headers
- Add visual hierarchy with indentation

## Files Modified

1. `src/primr/ai/deep_research.py`
   - Reduced retry noise (2 locations)
   - Removed duplicate "Research started" messages (4 locations)

2. `src/primr/core/research_agent.py`
   - Increased heartbeat interval from 30s to 90s

3. `src/primr/utils/console.py`
   - Enhanced `phase_banner()` method with ASCII separators

## Testing

To verify improvements:

```bash
# Run a complete research job
primr "Test Company" https://example.com --mode complete

# Expected improvements:
# - Cleaner phase transitions with visual separators
# - Less frequent heartbeat messages (90s vs 30s)
# - Single "Research started" message
# - Minimal retry noise during API errors
```

## Backward Compatibility

All changes maintain backward compatibility:
- Existing `phase_banner()` calls work without modification
- Console methods remain unchanged
- No breaking changes to public APIs

## Future Improvements

1. Add `console.phase_complete()` calls with visual separators
2. Standardize all message prefixes throughout codebase
3. Add indentation for sub-operations
4. Consider adding progress bars for long operations
5. Add color support for better visual hierarchy

## Related Documentation

- `src/primr/utils/console.py` - Console utility implementation
- `docs/ARCHITECTURE.md` - System architecture
- `ROADMAP.md` - Version history and planned features
