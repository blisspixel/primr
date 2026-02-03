# Vendor Research Reuse Fix

**Date:** January 21, 2026  
**Version:** 1.2.4  
**Issue:** Vendor research files were being regenerated even when current month's file already existed

## Problem

When running Primr with AI Strategy generation, the system was regenerating vendor research files (e.g., `vendor-research-azure-2026-01.txt`) even when a file for the current month already existed in the `docs/` directory. This resulted in:

- Unnecessary 7+ minute delays per run
- Wasted API costs (~$0.10 per regeneration)
- Duplicate work when the existing research was already current

### Example

User ran Primr for Providence at 4:56 PM. The system had already generated `vendor-research-azure-2026-01.txt` at 4:03 PM (same day, same month), but it regenerated the file anyway:

```
Generating fresh AZURE AI research...
Estimated: 5-10 min, ~$0.50
...
+ Vendor research saved: vendor-research-azure-2026-01.txt (7.2m, ~$0.10)
```

## Root Cause

The vendor research reuse logic was working correctly in `vendor_research.py`, but there were two issues:

1. **Missing console feedback**: When reusing existing files, there was no console message to indicate the file was being reused (making it unclear if the logic was working)

2. **Missing force_refresh parameter**: In `ai_strategy.py`, the call to `get_or_generate_vendor_research()` was not explicitly passing `force_refresh=False`, relying on the default parameter value

## Solution

### Changes Made

**File: `src/primr/core/vendor_research.py`**

1. Added console message when reusing existing vendor research:
   ```python
   if research_path.exists() and not force_refresh:
       # Reuse existing research from this month
       files.append(VendorResearchFile(...))
       console.info(f"Using existing vendor research: {research_path.name}")
       logger.info(f"Reusing vendor research file: {research_path}")
   ```

2. Added clarifying comments to explain the generation logic:
   ```python
   elif not files or force_refresh:
       # Generate fresh research only if:
       # 1. No files at all (not even manual), OR
       # 2. Force refresh requested
   ```

**File: `src/primr/core/ai_strategy.py`**

3. Explicitly pass `force_refresh=False` parameter:
   ```python
   result = await get_or_generate_vendor_research(
       vendor_str, 
       force_refresh=False,  # Explicitly pass force_refresh
       on_progress=on_progress
   )
   ```

### Verification

After the fix, running the vendor research check shows:

```
Using existing vendor research: vendor-research-azure-2026-01.txt
Generated: False
Files: ['C:\\Users\\nicks\\OneDrive\\primr\\docs\\vendor-research-azure-2026-01.txt']
```

## Benefits

- **Time savings**: ~7 minutes saved per run when vendor research already exists
- **Cost savings**: ~$0.10 saved per run (adds up with multiple runs per day)
- **Better UX**: Clear console feedback showing when files are being reused
- **Reliability**: Explicit parameter passing makes the code more maintainable

## File Naming Convention

Vendor research files follow this pattern:
```
vendor-research-{vendor}-{YYYY-MM}.txt
```

Examples:
- `vendor-research-azure-2026-01.txt` (January 2026)
- `vendor-research-aws-2026-01.txt` (January 2026)
- `vendor-research-gcp-2026-02.txt` (February 2026)

Files are automatically reused within the same month. A new file is generated when:
1. No file exists for the current month
2. User explicitly requests force refresh with `--force-refresh-vendor` flag

## Testing

To test vendor research reuse:

```python
import asyncio
from primr.core.vendor_research import get_or_generate_vendor_research

# Should reuse existing file (if current month exists)
result = asyncio.run(get_or_generate_vendor_research('azure', force_refresh=False))
print(f"Generated: {result.generated}")  # Should be False if file exists
print(f"Files: {[str(p) for p in result.paths]}")
```

Expected output when file exists:
```
Using existing vendor research: vendor-research-azure-2026-01.txt
Generated: False
Files: ['C:\\Users\\nicks\\OneDrive\\primr\\docs\\vendor-research-azure-2026-01.txt']
```

## Related Files

- `src/primr/core/vendor_research.py` - Vendor research generation and caching
- `src/primr/core/ai_strategy.py` - AI strategy generation (uses vendor research)
- `vendor-research/vendor-research-*.txt` - Generated vendor research files (gitignored)
