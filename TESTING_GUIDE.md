# Overview Page Testing Guide

## Quick Start Testing

### 1. Start the Application
```bash
# From the amw_analytics directory
python run.py --fast
```

### 2. Access Overview Page
- Open browser to: http://127.0.0.1:5000/
- Login with: `admin` / `admin`

### 3. Check Browser Console
Press F12 (DevTools) → Console tab and verify:
- ✅ No red error messages
- ✅ Data loads successfully
- ✅ All charts render

## Detailed Test Scenarios

### Scenario 1: Normal Page Load
**Steps:**
1. Navigate to overview page
2. Wait for all content to load

**Expected Results:**
- KPI cards show data or zeros
- All 6 charts render or show "No data" message
- Meat metrics section displays
- No JavaScript errors in console
- Loading spinner disappears

**Pass Criteria:** Page fully loads within 5 seconds

---

### Scenario 2: Filter Application
**Steps:**
1. Change date range filter
2. Select a region from dropdown
3. Click "Apply Filters"

**Expected Results:**
- Loading spinner appears
- Data updates within 3 seconds
- Charts refresh with new data
- Filter chip shows selected filters
- No console errors

**Pass Criteria:** Filters apply without errors

---

### Scenario 3: Network Failure Simulation
**Steps:**
1. Open DevTools → Network tab
2. Set throttling to "Offline"
3. Click "Apply Filters"
4. Set throttling back to "No throttling"
5. Click "Apply Filters" again

**Expected Results:**
- Error message appears on offline attempt
- Error message is user-friendly (not technical stack trace)
- Page recovers when network restored
- No page crash or infinite loading

**Pass Criteria:** Graceful error handling and recovery

---

### Scenario 4: Empty Data Response
**Steps:**
1. Apply very restrictive filters (e.g., old date range)
2. Verify page handles empty results

**Expected Results:**
- KPIs show 0 values
- Charts show "No data for current filters"
- No JavaScript errors
- Page remains functional

**Pass Criteria:** Empty states display correctly

---

### Scenario 5: Rapid Filter Changes
**Steps:**
1. Rapidly change filters multiple times
2. Click apply before previous request completes

**Expected Results:**
- Only latest filter request completes
- Previous requests are cancelled
- No duplicate data loads
- UI updates correctly

**Pass Criteria:** Debouncing works correctly

---

### Scenario 6: Page Refresh During Load
**Steps:**
1. Start applying filters
2. Immediately refresh page (F5)
3. Let page load completely

**Expected Results:**
- Page loads cleanly after refresh
- No lingering errors from interrupted requests
- All sections render properly

**Pass Criteria:** Clean recovery from interruption

---

## Console Error Checklist

### ❌ **FAIL Indicators** (Fix if you see these):
- `Uncaught (in promise)`
- `TypeError: Cannot read property`
- `ReferenceError`
- `Infinite loop` or page freeze
- `Failed to fetch` without recovery

### ✅ **PASS Indicators** (These are OK):
- `console.warn` messages (informational)
- `console.error` with clear error handling
- API 404/500 errors with graceful degradation

## Performance Benchmarks

| Metric | Target | Critical |
|--------|--------|----------|
| Initial page load | < 3s | < 5s |
| Filter application | < 2s | < 4s |
| Chart rendering | < 1s | < 2s |
| Memory usage | < 150MB | < 250MB |

## Browser Compatibility

Test in:
- ✅ Chrome/Edge (latest)
- ✅ Firefox (latest)
- ✅ Safari (latest)
- ⚠️ Mobile browsers (responsive)

## Common Issues & Solutions

### Issue: "Page stuck loading"
**Solution:**
1. Check browser console for errors
2. Verify API endpoint is responding
3. Check for CORS issues
4. Verify parquet file exists

### Issue: "Charts not rendering"
**Solution:**
1. Verify Plotly.js is loaded
2. Check if data is empty
3. Look for JavaScript errors
4. Try hard refresh (Ctrl+F5)

### Issue: "Filters not applying"
**Solution:**
1. Check network tab for failed requests
2. Verify authentication
3. Check RBAC permissions
4. Verify data in backend

### Issue: "Meat metrics blank"
**Solution:**
- This is normal if data doesn't have meat-specific columns
- Check backend logs for warnings
- Verify data structure includes: ProductName, QuantityShipped, etc.

## Automated Testing Commands

```bash
# Run Python unit tests
pytest tests/ -v

# Run specific test file
pytest tests/test_overview.py -v

# Run with coverage
pytest --cov=app tests/

# Run smoke tests
python scripts/smoke.py
```

## Reporting Bugs

When reporting issues, include:
1. Browser and version
2. Full console error log
3. Network tab screenshot
4. Steps to reproduce
5. Expected vs actual behavior

## Success Criteria Summary

**The overview page is production-ready when:**
- ✅ All 7 test scenarios pass
- ✅ No critical console errors
- ✅ Performance meets targets
- ✅ Works in all major browsers
- ✅ Gracefully handles all error conditions
- ✅ User-friendly error messages
- ✅ Data loads reliably

---

**Last Updated**: 2025-11-03
**Test Version**: 1.0
