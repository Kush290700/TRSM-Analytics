# Troubleshooting Guide - Overview Page "Dies" Issue

## ✅ **FIXED! - Latest Updates**

The overview page "loading data then dying" issue has been resolved with comprehensive error handling.

### **What Was Fixed**

1. ✅ **JavaScript Error Handling** - Added try/catch blocks to all meat metrics functions
2. ✅ **Backend Error Handling** - Wrapped all metric calculations with try/except
3. ✅ **Graceful Degradation** - Page continues to work even if some metrics fail
4. ✅ **Better Logging** - Console warnings show which specific metrics failed

---

## 🔍 **How to Verify the Fix**

### **Step 1: Check Browser Console**

Open browser DevTools (F12) and go to Console tab:

```javascript
// You should see logs like:
"No meat metrics data available"  // If no data
"Meat metrics render failed: ..."  // If calculation error
```

**Good signs:**
- Page loads completely
- No red errors stopping execution
- Yellow warnings are okay (just informational)

**Bad signs:**
- Red errors about undefined functions
- "TypeError: Cannot read property..." errors
- Page stops loading halfway

### **Step 2: Test the Page**

1. **Open the overview page**: http://localhost:5000
2. **Wait for load**: Should complete in 2-5 seconds
3. **Check these sections display:**
   - ✓ Revenue spotlight (hero card)
   - ✓ KPI cards (Customers, Orders, Revenue, AOV, Churn)
   - ✓ Top customers/products/regions/sales reps
   - ✓ Charts (revenue, orders, pareto, etc.)
   - ✓ Operations & margin
   - ✓ Recommendations
   - ✓ **🥩 Meat Industry Performance** (new section)

4. **Apply filters**: Change date range → page should update without dying

### **Step 3: Check Network Tab**

In DevTools Network tab:

1. Look for `/api/overview/data` request
2. Click on it → Preview tab
3. Verify response has `meat_metrics` key:

```json
{
  "kpis": {...},
  "insights": {...},
  "operations": {...},
  "meat_metrics": {
    "protein_mix": {},
    "pack_analysis": {},
    "yield_metrics": {},
    "cold_chain": {},
    "cut_performance": {}
  }
}
```

---

## 🐛 **If Still Having Issues**

### **Issue 1: Page loads then goes blank**

**Symptom**: Page shows loading spinner, data appears briefly, then everything disappears.

**Cause**: JavaScript error after initial render.

**Fix:**
1. Open browser console (F12)
2. Look for red error messages
3. Common errors:

```javascript
// Error: Plotly is not defined
// Fix: Add Plotly CDN to base.html
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>

// Error: $ is not a function
// Fix: jQuery is missing or not loaded before overview.js

// Error: Cannot read property 'meat_metrics' of null
// Fix: Already fixed in latest code with null checks
```

### **Issue 2: Meat metrics section shows "No data"**

**Symptom**: 🥩 section appears but says "No protein data available".

**Diagnosis:**
```python
# Run in Python console:
import data_loader as loader
df = loader.get_fact_df()

# Check if protein column exists:
protein_cols = [c for c in df.columns if 'protein' in c.lower() or 'category' in c.lower()]
print("Protein columns found:", protein_cols)

# If empty list, you need to add the column or update line 724
```

**Fix:** See [MEAT_METRICS_SCHEMA_GUIDE.md](MEAT_METRICS_SCHEMA_GUIDE.md) for schema configuration.

### **Issue 3: Page freezes during load**

**Symptom**: Browser tab says "Loading..." forever, page never finishes.

**Cause**: Large dataset taking too long to process.

**Fix:**
1. Check server logs for slow queries
2. Add database indexes (see [OVERVIEW_ENHANCEMENTS.md](OVERVIEW_ENHANCEMENTS.md))
3. Reduce date range in filter
4. Check parquet snapshot is being used (not direct SQL)

### **Issue 4: Charts don't render**

**Symptom**: Chart areas are empty or show "No data".

**Diagnosis:**
```javascript
// In browser console:
typeof Plotly  // Should return "object", not "undefined"
```

**Fix:**
```html
<!-- Add to app/templates/base.html before closing </body> -->
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
```

### **Issue 5: 500 Server Error**

**Symptom**: Network tab shows red 500 error for `/api/overview/data`.

**Cause**: Backend Python exception.

**Fix:**
1. Check server logs:
   ```bash
   tail -f logs/app.log
   # or
   tail -f /var/log/gunicorn/error.log
   ```

2. Look for error in meat metrics calculation:
   ```
   ERROR: overview.meat_metrics.failed
   Traceback...
   ```

3. Common errors:
   - `KeyError: 'ProteinCategory'` → Column doesn't exist, update line 724
   - `ValueError: Cannot convert float NaN to integer` → Null data, already fixed with pd.notna() checks
   - `AttributeError: 'Series' object has no attribute 'name'` → Already fixed with index-based groupby

---

## 🔧 **Quick Fixes**

### **Fix 1: Clear Browser Cache**

```bash
# Hard refresh:
Ctrl+Shift+R (Windows/Linux)
Cmd+Shift+R (Mac)

# Or clear cache:
DevTools → Network tab → Disable cache checkbox
```

### **Fix 2: Clear Server Cache**

```bash
# If using Redis:
redis-cli FLUSHDB

# If using file cache:
rm -rf app/__pycache__/*
rm -rf app/services/__pycache__/*
```

### **Fix 3: Restart Application**

```bash
# Kill and restart:
pkill -f gunicorn
python run.py

# Or with systemd:
systemctl restart gunicorn
```

### **Fix 4: Verify Dependencies**

```bash
# Check Plotly is accessible:
curl -I https://cdn.plot.ly/plotly-2.27.0.min.js

# Check Flask app is running:
curl http://localhost:5000/api/overview/filters

# Should return JSON, not error
```

---

## 📝 **Debugging Checklist**

Use this checklist to systematically diagnose issues:

- [ ] Browser console shows no red errors
- [ ] Network tab shows 200 OK for `/api/overview/data`
- [ ] Response includes `meat_metrics` key
- [ ] Plotly CDN is loaded (check Sources tab)
- [ ] jQuery is loaded before overview.js
- [ ] Bootstrap 5 CSS is loaded
- [ ] Server logs show no exceptions
- [ ] Database connection is working
- [ ] Parquet file exists and is recent
- [ ] All required columns exist in data
- [ ] No CORS errors in console

---

## 🆘 **Emergency Rollback**

If all else fails, temporarily hide meat metrics:

### **Option 1: CSS Hide**

Add to `overview.html`:
```html
<style>
  #meatMetricsSection { display: none !important; }
</style>
```

### **Option 2: Comment Out Section**

In `overview.html` lines 224-310:
```html
<!-- Temporarily disabled
<div class="row g-3 mb-4" id="meatMetricsSection">
  ...
</div>
-->
```

### **Option 3: Disable Backend Calculation**

In `overview_query.py`:
```python
# Line 823-832: Comment out meat metrics
# meat_metrics: Dict[str, Any] = {}
# try:
#     meat_metrics = _meat_specific_metrics(df, revenue)
# except Exception:
#     ...

# Just return empty:
meat_metrics = {}
```

---

## 📊 **Performance Monitoring**

### **What to Monitor**

1. **Page Load Time**
   ```javascript
   // In browser console:
   performance.timing.loadEventEnd - performance.timing.navigationStart
   // Should be < 5000ms (5 seconds)
   ```

2. **API Response Time**
   ```bash
   # In terminal:
   curl -w "@-" -o /dev/null -s "http://localhost:5000/api/overview/data" <<'EOF'
   time_total: %{time_total}
   EOF
   # Should be < 2 seconds
   ```

3. **Memory Usage**
   ```bash
   # Check Python process:
   ps aux | grep python
   # RSS column should be < 1GB for overview page
   ```

---

## ✅ **Validation Tests**

Run these to verify everything works:

### **Test 1: Smoke Test**

```bash
# Run the test suite:
python test_overview_meat_metrics.py

# Should output:
# ✓ Backend Metrics: PASS
# ✓ Frontend Elements: PASS
# ✓ JavaScript Functions: PASS
```

### **Test 2: Manual API Test**

```bash
# Test API endpoint:
curl -X POST http://localhost:5000/api/overview/data \
  -H "Content-Type: application/json" \
  -d '{"start":"2024-01-01","end":"2024-12-31"}' \
  | jq '.meat_metrics'

# Should return JSON object, not null
```

### **Test 3: Browser Test**

1. Open http://localhost:5000
2. Open DevTools console (F12)
3. Type:
   ```javascript
   // Should show meat metrics data:
   console.log(window.__OVERVIEW_DEBUG__);
   ```

---

## 📞 **Getting Help**

If you're still stuck:

1. **Collect Debug Info**:
   ```bash
   # Server logs:
   tail -100 logs/app.log > debug_logs.txt

   # Browser console:
   # Right-click console → Save as... → console_errors.log

   # Network requests:
   # DevTools → Network → Right-click → Save all as HAR
   ```

2. **Check Documentation**:
   - [OVERVIEW_SUMMARY.md](OVERVIEW_SUMMARY.md) - Quick start
   - [OVERVIEW_ENHANCEMENTS.md](OVERVIEW_ENHANCEMENTS.md) - Full technical docs
   - [MEAT_METRICS_SCHEMA_GUIDE.md](MEAT_METRICS_SCHEMA_GUIDE.md) - Schema config

3. **Common Error Messages**:

| Error | Meaning | Fix |
|-------|---------|-----|
| `Plotly is not defined` | CDN not loaded | Add Plotly script tag |
| `Cannot read property 'meat_metrics' of null` | API returned null | Check server logs |
| `$ is not a function` | jQuery missing | Load jQuery before overview.js |
| `Failed to fetch` | Server not running | Start Flask app |
| `404 Not Found` | Route missing | Check blueprints registered |

---

## 🎉 **Success Indicators**

You'll know everything is working when:

✅ Page loads in < 5 seconds
✅ All KPI cards show numbers
✅ 🥩 Meat Industry Performance section displays
✅ Charts render without errors
✅ Filters update the page smoothly
✅ Browser console has no red errors
✅ Network tab shows all API calls succeed (200 OK)

---

**Last Updated**: 2025-01-15
**Version**: 1.1.0 (Fixed "dies" issue)
**Status**: ✅ Production Ready
