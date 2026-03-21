# Debug Frontend Payload

Since the overview page is still showing zeros, we need to see what the frontend is actually sending.

## Steps to Debug

### 1. Open Browser DevTools

1. Open the overview page: http://localhost:5000
2. Press **F12** to open DevTools
3. Go to **Network** tab
4. Refresh the page (Ctrl+R)

### 2. Find the API Request

Look for these requests in the Network tab:

- `GET /api/overview/filters` - Should return 200 OK
- `POST /api/overview/data` - This is the important one!

### 3. Inspect the Request Payload

Click on `POST /api/overview/data` request:

1. Click on the **Payload** or **Request** tab
2. Look at the JSON being sent

**Copy the entire payload and share it with me.**

It should look something like:
```json
{
  "start": "2024-01-01",
  "end": "2024-12-31",
  "regions": [...],
  "methods": [...],
  "customers": [...]
}
```

### 4. Check the Response

Click on the **Response** or **Preview** tab:

1. Does it show data or empty `{}`?
2. Are the KPIs zeros or actual numbers?

Example response:
```json
{
  "kpis": {
    "total_revenue": 6149761.36,  // <-- Should NOT be 0
    "total_orders": 6975,
    "total_customers": 655
  }
}
```

### 5. Check Console Errors

Go to **Console** tab in DevTools:

- Are there any red errors?
- Any warnings about "overview data failed"?

---

## Quick Test in Console

Open the browser console (F12 → Console tab) and paste this:

```javascript
// Test the API directly
fetch('/api/overview/data', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    start: null,
    end: null,
    regions: ['All'],
    methods: ['All'],
    customers: ['All'],
    suppliers: ['All']
  })
})
.then(r => r.json())
.then(d => {
  console.log('Revenue:', d.kpis?.total_revenue);
  console.log('Orders:', d.kpis?.total_orders);
  console.log('Full response:', d);
})
.catch(e => console.error('Error:', e));
```

**What does this return?**

- If it returns zeros → Backend is still filtering wrong
- If it returns real numbers → Frontend display issue
- If it returns error → Authentication or route issue

---

## Alternative: Check Flask Logs

If Flask is running in a terminal, check the output for errors:

```bash
# Look for lines like:
# ERROR in overview: ...
# overview.data.failed: ...
# overview.scope_empty: ...
```

Share any error messages you see.

---

## What to Share

Please provide:

1. **The request payload** from Network tab
2. **The response data** from Network tab
3. **Any console errors** (red text)
4. **Flask log errors** (if visible)
5. **What the console test returns**

This will help me identify exactly what's going wrong!
