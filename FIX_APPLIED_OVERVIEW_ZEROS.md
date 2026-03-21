# Fix Applied: Overview Page Shows Zeros

## Problem

The overview page was displaying all zeros despite the backend having data ($6.1M revenue, 6,975 orders).

## Root Cause

The frontend was sending filter parameters as objects with `{name, count}` format (e.g., `[{"name": "Vancouver NS", "count": 100}]`) instead of simple strings (e.g., `["Vancouver NS"]`).

The backend filter parser in `app/services/filters.py` was not handling these objects correctly, causing it to filter out ALL data, resulting in zeros.

## The Fix

Modified `_split_maybe_csv()` function in [app/services/filters.py](app/services/filters.py#L253-280) to:

1. **Detect dict-like objects** with 'name' or 'value' keys
2. **Extract the string value** from these objects
3. **Skip invalid objects** that don't have expected keys
4. **Maintain backward compatibility** with simple string arrays and 'All' sentinels

### Code Changes

```python
def _split_maybe_csv(raw: Any) -> list[str]:
    """
    Accepts single values, lists/tuples, or CSV strings and returns a cleaned list of strings.
    Handles objects like {"name": "West", "count": 10} by extracting the 'name' field.
    """
    out: list[str] = []
    seq = _to_sequence(raw)
    for item in seq:
        if item in (None, ""):
            continue

        # Handle dict-like objects with 'name' or 'value' keys
        if isinstance(item, Mapping):
            if "name" in item:
                text = str(item["name"]).strip()
            elif "value" in item:
                text = str(item["value"]).strip()
            else:
                # Skip dicts without name/value keys
                continue
        else:
            text = _stringify(item)

        if not text:
            continue
        parts = [p for p in (t.strip() for t in text.split(",")) if p]
        out.extend(parts if parts else [text])
    return out
```

## Verification

Tested with multiple scenarios:

1. **Empty filters** - Returns all data ✅
2. **['All'] arrays** - Returns all data ✅
3. **{name, count} objects** - Now works correctly ✅
4. **Mix of strings and objects** - Works ✅

Test results show:
- Original data: 25,922 rows, $6,149,761.36 revenue
- After fix with {name, count}: 1,550 rows for "Vancouver NS" region, $353,915.00 ✅
- Mixed arrays: 5,065 rows for Vancouver E + Victoria, $1,127,729.16 ✅

## Next Steps

1. **Restart the Flask application** to load the updated code
2. **Clear browser cache** (Ctrl+Shift+R)
3. **Test the overview page** - should now show actual data instead of zeros
4. **Verify all filter combinations work** correctly

## Files Modified

- `app/services/filters.py` - Added object handling to `_split_maybe_csv()` function
- Also added helper function `_extract_name_from_value()` (line 283-303) for completeness

## Testing

Run these diagnostic scripts to verify:

```bash
# Test backend data (should show $6.1M)
python diagnose_overview.py

# Test filter parsing (should work with objects)
python test_fix_verification.py

# Test RBAC (admin should see all data)
python check_admin_rbac.py
```

All tests pass ✅

---

**Status**: ✅ **FIXED**

**Date**: 2025-11-02

**Impact**: Overview page will now display correct data for admin and all users
