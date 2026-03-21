# Production Overview Page - Complete Fix Plan

## Executive Summary

Making `/` the single, production-ready source of truth by:
1. Fixing overview.js initialization timing
2. Redirecting `/dashboard/` to `/`
3. Ensuring data accuracy
4. Adding comprehensive error handling

## Fix #1: Redirect Dashboard to Overview (Single Source of Truth)

**File**: `app/blueprints/dashboard.py`

Replace the entire `index()` function with a simple redirect:

```python
@bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    """Redirect to new overview page."""
    from flask import redirect, url_for
    return redirect(url_for("pages.home"), code=301)
```

This creates a permanent redirect from `/dashboard/` to `/` so all users see the same modern overview page.

## Fix #2: Enhanced overview.js Initialization

Add explicit logging and better error handling:

**File**: `app/static/js/overview.js`

Add at the very top (after 'use strict'):

```javascript
// Initialization flag for debugging
window.__OVERVIEW_INIT_START__ = new Date().toISOString();
console.log('[OVERVIEW] Script loaded at:', window.__OVERVIEW_INIT_START__);
```

Change init function (line 3151) to:

```javascript
function init() {
    console.log('[OVERVIEW] init() called, readyState:', document.readyState);

    const metricCards = $$('[data-metric-card]');
    console.log('[OVERVIEW] Found', metricCards.length, 'metric cards');

    if (metricCards.length === 0) {
      console.warn('[OVERVIEW] No metric cards found - page may not be loaded yet');
      // Try again after a short delay
      setTimeout(() => {
        console.log('[OVERVIEW] Retrying init after delay...');
        const retryCards = $$('[data-metric-card]');
        if (retryCards.length > 0) {
          console.log('[OVERVIEW] Found', retryCards.length, 'metric cards on retry');
          initAfterValidation();
        } else {
          console.error('[OVERVIEW] Still no metric cards found - aborting');
        }
      }, 500);
      return;
    }

    initAfterValidation();
}

function initAfterValidation() {
    console.log('[OVERVIEW] Running full initialization...');
    initSelects();
    initDates();
    initToast();
    wireFilters();
    setupExportHandler();
    setupRefreshHandler();

    // Initialize universal drilldown system
    initDrilldownSystem();

    // Load enhanced overview sections
    idle(() => {
      loadEnhancedOverview();
    }, 200);

    if (bootstrapPayload) {
      const f = normalizeFilters(bootstrapPayload.filters);
      setFiltersOnUI(f);
      if (bootstrapPayload.overview) {
        handleOverviewData(bootstrapPayload.overview);
      }
    } else {
      restoreLast();
    }

    applyFilters(false);
    fetchFilters();

    // Re-theme charts if the theme changes
    const themeObserver = new MutationObserver(debounce(() => {
      $$('[data-chart-card]').forEach(el => {
        if (el.id && el.layout && el.data) {
          const layout = applyTheme(el.layout);
          safePlot(el, el.data, layout);
        }
      });
    }, 100));
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-bs-theme'],
    });

    console.log('[OVERVIEW] Initialization complete');
    window.__OVERVIEW_INIT_COMPLETE__ = new Date().toISOString();
}
```

## Fix #3: Fix EventSource (SSE) Issue

**File**: `app/blueprints/events.py` (or wherever SSE is defined)

Ensure the endpoint returns proper headers:

```python
@bp.route("/api/events")
@login_required
def sse_stream():
    """Server-Sent Events stream for live updates."""
    def generate():
        # Send initial connection confirmation
        yield f"data: {json.dumps({'type': 'connected', 'timestamp': datetime.now(tz=timezone.utc).isoformat()})}\n\n"

        # Keep connection alive
        while True:
            time.sleep(30)
            yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': datetime.now(tz=timezone.utc).isoformat()})}\n\n"

    response = Response(generate(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response
```

## Fix #4: Add JSON Serialization Helper

**File**: `app/blueprints/overview.py`

Add helper to sanitize NaN/Inf values:

```python
import json
import math

def sanitize_for_json(obj):
    """Recursively replace NaN, Infinity with None."""
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [sanitize_for_json(v) for v in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    else:
        return obj

# Use in all JSON responses:
# return jsonify(sanitize_for_json(data))
```

## Fix #5: Update Playwright Test

**File**: `test_overview_playwright.py`

Update wait times and add better logging:

```python
def test_viewport(self, browser: Browser, viewport_name: str, width: int, height: int, phase: str = "before"):
    """Test a specific viewport configuration."""
    print(f"\n{'='*60}")
    print(f"Testing Viewport: {viewport_name} ({width}x{height})")
    print(f"{'='*60}")

    context = browser.new_context(
        viewport={"width": width, "height": height},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
    page = context.new_page()

    # Setup listeners
    self.setup_page_listeners(page)

    # Login
    self.login(page)

    # Navigate to overview page
    print(f"\n[ICON] Navigating to {self.base_url}/overview")
    page.goto(f"{self.base_url}/overview", timeout=60000)

    # Wait for page to load
    page.wait_for_load_state("domcontentloaded")

    # Wait for metric cards to appear (critical check)
    try:
        page.wait_for_selector('[data-metric-card]', timeout=10000)
        print("[OK] Metric cards found")
    except:
        print("[WARN] Metric cards not found after 10s")

    # Additional wait for JS initialization
    time.sleep(5)  # Give JS time to execute

    # Capture screenshot
    self.capture_screenshot(page, f"overview_{viewport_name}", phase)

    # Run checks
    self.run_checks(page, viewport_name)

    # Close context
    time.sleep(2)  # Prevent rate limiting
    context.close()
```

## Implementation Steps

1. **Apply Fix #1**: Redirect dashboard to overview (5 min)
2. **Apply Fix #2**: Enhanced JS initialization (10 min)
3. **Apply Fix #3**: Fix SSE endpoint (5 min)
4. **Apply Fix #4**: Add JSON sanitization (10 min)
5. **Apply Fix #5**: Update Playwright test (5 min)
6. **Test**: Run Playwright validation (10 min)
7. **Verify**: Manual testing in browser (10 min)

**Total Time**: ~55 minutes

## Testing Checklist

- [ ] `/dashboard/` redirects to `/`
- [ ] KPI cards load with real data
- [ ] Charts render correctly
- [ ] Filters work and update URL
- [ ] No console errors
- [ ] All API calls succeed (200 status)
- [ ] Responsive on desktop/tablet/mobile
- [ ] No NaN/Infinity in JSON responses
- [ ] ETag caching works (304 responses)

## Rollback Plan

If issues occur:
1. Revert dashboard.py redirect
2. Keep both pages active temporarily
3. Debug with increased logging
4. Use feature flag to control which page is default

## Success Metrics

- Zero console errors
- All KPIs show data within 3 seconds
- API response time < 500ms
- Page load time < 2 seconds
- 100% Playwright test pass rate

---

**Status**: Ready to implement
**Risk Level**: Low (non-breaking changes with fallbacks)
**Estimated Completion**: 1 hour
