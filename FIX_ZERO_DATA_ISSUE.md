# Fix: Overview Page Shows All Zeros (But Backend Has Data)

## Problem

- Backend has data (6,149,761.36 revenue, 6,975 orders)
- Overview page shows all zeros
- Backend calculation works (tested with diagnose_overview.py)

## Root Cause

The issue is **NOT in the backend**. The backend is working correctly. The problem is one of these:

1. **Authentication issue** - Not logged in or session expired
2. **JavaScript error** - Blocking data display
3. **API endpoint not being called** - Network issue
4. **CORS/CSP blocking** - Security headers blocking requests

---

## Solution Steps

### Step 1: Check Flask App is Running

```bash
python run.py
```

You should see:
```
Local server running at:
  http://127.0.0.1:5000
```

### Step 2: Login First

**IMPORTANT:** You must be logged in to see data!

1. Go to: http://localhost:5000/login
2. Login with:
   - Username: `admin`
   - Password: `admin`

3. Then go to overview: http://localhost:5000/

### Step 3: Open Browser DevTools

Press **F12** to open DevTools, then:

#### A. Check Console Tab

Look for errors (red text):

**Common Errors & Fixes:**

```javascript
// Error: "Failed to fetch"
// Fix: Flask app not running - run: python run.py

// Error: "401 Unauthorized"
// Fix: Not logged in - go to /login

// Error: "Plotly is not defined"
// Fix: Add to base.html:
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>

// Error: "overview data failed"
// Fix: Check Network tab for API error
```

#### B. Check Network Tab

1. Refresh the page (Ctrl+R)
2. Look for these requests:

```
GET  /api/overview/filters  -> Should be 200 OK
POST /api/overview/data     -> Should be 200 OK
GET  /api/overview/series   -> Should be 200 OK
```

**If you see 401 Unauthorized:**
- You're not logged in
- Go to /login and login first

**If you see 500 Server Error:**
- Check Flask terminal for error messages
- Check logs/app.log

**If you see 0 byte responses:**
- Check Flask is actually running
- Try: curl http://localhost:5000/api/overview/filters

#### C. Check Response Data

1. In Network tab, click on `/api/overview/data`
2. Click "Preview" or "Response" tab
3. You should see JSON like:

```json
{
  "kpis": {
    "total_revenue": 6149761.36,
    "total_orders": 6975,
    "total_customers": 655
  },
  "meat_metrics": {
    "protein_mix": {},
    "pack_analysis": {...},
    ...
  }
}
```

**If response is null or {}:**
- Check Flask logs for Python errors
- The error is in backend compute_overview()

**If response looks good but page shows zeros:**
- JavaScript rendering error
- Check Console for JS errors

---

## Quick Fixes

### Fix 1: Clear Browser Cache

```
Ctrl + Shift + R  (hard refresh)
```

Or:
1. F12 -> Network tab
2. Check "Disable cache"
3. Refresh page

### Fix 2: Check Login Session

```javascript
// In browser console:
fetch('/api/overview/filters')
  .then(r => r.json())
  .then(d => console.log('Filters:', d))
  .catch(e => console.error('Error:', e))
```

If you get 401 error, you need to login.

### Fix 3: Test API Directly

```bash
# Test filters endpoint
curl http://localhost:5000/api/overview/filters

# Should return JSON with regions, customers, etc.
```

### Fix 4: Check Flask is Serving Files

```bash
# In browser, go to:
http://localhost:5000/static/js/overview.js

# Should show JavaScript code, not 404
```

---

## Debugging Checklist

Run through this checklist:

- [ ] Flask app is running (python run.py shows server started)
- [ ] Logged in at /login (username: admin, password: admin)
- [ ] Browser DevTools Console shows no red errors
- [ ] Network tab shows /api/overview/data returns 200 OK
- [ ] Network tab response has actual data (not null/empty)
- [ ] overview.js file loads (check Sources tab)
- [ ] No CORS errors in console
- [ ] Cache cleared (Ctrl+Shift+R)

---

## Still Not Working?

### Debug with Console Commands

Open browser console (F12) and type:

```javascript
// 1. Check if data is being loaded
window.__OVERVIEW_DEBUG__
// Should show load metadata

// 2. Manually trigger data load
fetch('/api/overview/data', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({start: '2024-01-01', end: '2024-12-31'})
})
.then(r => r.json())
.then(d => {
  console.log('KPIs:', d.kpis);
  console.log('Meat metrics:', d.meat_metrics);
})
```

### Check Flask Logs

```bash
# Check for errors in terminal where Flask is running
# Look for lines like:
ERROR in overview: ...
Exception on /api/overview/data ...
```

### Enable Verbose Logging

In `.env` or `.env.dev`:
```
FLASK_ENV=development
FLASK_DEBUG=1
LOG_LEVEL=DEBUG
```

Restart Flask and check logs for more details.

---

## Common Scenarios

### Scenario 1: Shows Zeros for 2 Seconds, Then Blanks Out

**Cause:** JavaScript error after initial render

**Fix:**
1. Check browser console for red errors
2. Likely a Plotly or rendering error
3. See TROUBLESHOOTING_OVERVIEW.md

### Scenario 2: Infinite Loading Spinner

**Cause:** API request hanging or failing silently

**Fix:**
1. Check Network tab for stuck requests
2. Check Flask is responding: curl http://localhost:5000/
3. Restart Flask app

### Scenario 3: 401 Unauthorized

**Cause:** Not logged in or session expired

**Fix:**
1. Go to http://localhost:5000/login
2. Login with admin/admin
3. Then navigate to overview page

### Scenario 4: All Sections Work Except Meat Metrics

**Cause:** Meat metrics calculation error

**Fix:**
1. Check Flask logs for "meat_metrics.failed"
2. See MEAT_METRICS_SCHEMA_GUIDE.md
3. Your data might not have protein/category column

---

## Test Script Results

When you ran `diagnose_overview.py`, it showed:

```
SUCCESS - Backend data is working!
Revenue: $6,149,761.36
Orders: 6,975
Customers: 655
```

This proves the backend is fine. The issue is **frontend/authentication**.

**Next steps:**
1. Make sure you're logged in
2. Check browser console for errors
3. Check Network tab for 401/500 errors

---

## Contact Info

If still stuck after trying all above:

1. Share screenshot of browser DevTools Console tab
2. Share screenshot of Network tab showing /api/overview/data request
3. Copy Flask terminal output showing any errors

---

## Quick Test Command

Run this in your browser console (F12):

```javascript
// Test if you're logged in and API works
fetch('/api/overview/data', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({})
})
.then(r => {
  console.log('Status:', r.status);
  return r.json();
})
.then(d => {
  console.log('Revenue:', d.kpis?.total_revenue);
  console.log('Orders:', d.kpis?.total_orders);
  if (d.kpis?.total_revenue === 0) {
    console.error('API returns zeros - backend filter issue');
  } else {
    console.log('API returns data - frontend display issue');
  }
})
.catch(e => console.error('Fetch error:', e));
```

This will tell you if the issue is:
- **Network/Auth** (fetch fails)
- **Backend** (API returns zeros)
- **Frontend** (API returns data but page shows zeros)

---

**Last Updated:** 2025-01-15
**Status:** Backend verified working, issue is in frontend/auth
