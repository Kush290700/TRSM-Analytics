# TRSM Analytics - Comprehensive Improvement Plan

**Version:** 1.0
**Created:** 2025-11-08
**Last Updated:** 2025-11-08
**Status:** Ready for Implementation

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current State Assessment](#current-state-assessment)
3. [Safety First Principles](#safety-first-principles)
4. [Phase 0: Pre-Implementation Checklist](#phase-0-pre-implementation-checklist)
5. [Phase 1: Critical Security Fixes](#phase-1-critical-security-fixes)
6. [Phase 2: Performance Foundation](#phase-2-performance-foundation)
7. [Phase 3: Memory & Cache Optimization](#phase-3-memory--cache-optimization)
8. [Phase 4: Advanced Performance](#phase-4-advanced-performance)
9. [Phase 5: Scalability & Observability](#phase-5-scalability--observability)
10. [Phase 6: Nice-to-Have Enhancements](#phase-6-nice-to-have-enhancements)
11. [Testing Strategy](#testing-strategy)
12. [Rollback Procedures](#rollback-procedures)
13. [Success Metrics](#success-metrics)

---

## Executive Summary

### Goals
- **Security:** Fix critical vulnerabilities (hard-coded credentials, CSRF, input validation)
- **Performance:** Reduce response times by 90% (2-5s → 200-500ms)
- **Scalability:** Support 100+ concurrent users (currently ~8-10)
- **Memory:** Reduce RAM usage by 75% (4GB → 1GB)
- **Reliability:** Improve error handling and observability

### Timeline
- **Phase 1 (Critical):** 1-2 days
- **Phase 2 (Performance):** 2-3 days
- **Phase 3 (Optimization):** 3-4 days
- **Phase 4 (Advanced):** 5-7 days
- **Phase 5 (Scalability):** 3-5 days
- **Total:** 2-3 weeks

### Risk Level
- **Low Risk:** Additive changes (new utilities, monitoring)
- **Medium Risk:** Refactoring existing code with backward compatibility
- **High Risk:** Core data loading, caching changes (requires extensive testing)

---

## Current State Assessment

### Application Metrics (Baseline - Measure Before Starting)

| Metric | Current | Target | Priority |
|--------|---------|--------|----------|
| **Response Time (Overview API)** | 2-5 seconds | 200-500ms | 🔴 Critical |
| **Memory per Worker** | ~500MB+ | ~150MB | 🔴 Critical |
| **Concurrent Users (Max)** | 8-10 | 100+ | 🟠 High |
| **Cache Hit Rate** | ~40% | 80%+ | 🟡 Medium |
| **Test Coverage** | Unknown | 80%+ | 🟡 Medium |
| **API Response Size (Options)** | Unbounded | <100KB | 🟠 High |
| **Error Logging Quality** | Basic | Structured | 🟡 Medium |

### Critical Issues Identified

1. **Hard-coded super users in source code** (rbac.py)
2. **CSRF protection disabled** for JSON APIs
3. **No input validation** (accepts arbitrary JSON)
4. **Unbounded query results** (filter options, exports)
5. **Full DataFrame loaded per request** (memory inefficiency)
6. **Synchronous blocking operations** (no async)
7. **Missing comprehensive error handling**
8. **Cache key explosion** (millions of possible combinations)

### Protected Modules (DO NOT BREAK)

- ✅ **Customer Module** (`app/blueprints/customers.py`)
- ✅ **Products Module** (`app/blueprints/products.py`)
- ✅ **Regions Module** (`app/blueprints/regions.py`)
- ✅ **Suppliers Module** (`app/blueprints/suppliers.py`)
- ✅ **Sales Module** (`app/blueprints/sales.py`)
- ✅ **Authentication System** (`app/auth/`)

### Testing Requirements Before ANY Change

```bash
# Run full test suite
pytest -v --cov=app --cov-report=term-missing

# Test specific modules
pytest tests/test_customers.py -v
pytest tests/test_products.py -v
pytest tests/test_regions.py -v

# Manual smoke tests
python scripts/smoke_test.py

# Start app and verify all pages load
python run.py --fast
# Visit: /customers/, /products/, /regions/, /suppliers/, /sales/
```

---

## Safety First Principles

### 1. **Backward Compatibility**
- Never remove existing functions, only deprecate
- Add new functions alongside old ones
- Use feature flags for new behavior

### 2. **Incremental Changes**
- One improvement at a time
- Commit after each successful change
- Test thoroughly before proceeding

### 3. **Isolation Strategy**
```python
# Example: Adding new optimized function without touching old one
def get_fact_df():
    """Legacy function - DO NOT MODIFY"""
    return pd.read_parquet(PARQUET_PATH)

def get_fact_df_optimized(columns=None, filters=None):
    """New optimized version - use gradually"""
    return pd.read_parquet(PARQUET_PATH, columns=columns, filters=filters)

# Gradually migrate endpoints to use optimized version
```

### 4. **Canary Testing**
- Test new code paths with feature flags
- Monitor errors/performance
- Rollback immediately if issues detected

### 5. **Database Migrations**
- Always back up SQLite auth.db before schema changes
- Use alembic for migrations (not manual SQL)
- Test migrations on copy of production DB first

---

## Phase 0: Pre-Implementation Checklist

### 0.1 Create Backup System

**Files to Create:**
- `scripts/backup_before_changes.py`
- `scripts/restore_backup.py`

**Implementation:**
```bash
# Create backup script
python scripts/backup_before_changes.py
# Creates: backups/pre_improvement_YYYY-MM-DD_HH-MM-SS.zip
# Contains: auth.db, cache/*.parquet, .env, current code
```

**Success Criteria:**
- [ ] Backup script created and tested
- [ ] Restore script created and tested
- [ ] Full backup of current working state exists

**Time Estimate:** 30 minutes

---

### 0.2 Establish Baseline Metrics

**Files to Create:**
- `tests/performance/baseline_metrics.py`
- `tests/performance/run_baseline.sh`

**What to Measure:**
```python
# Baseline measurements
1. Response times for all critical endpoints
   - GET /customers/
   - GET /products/
   - POST /api/overview/summary
   - POST /api/overview/cards
   - GET /api/velocity/summary

2. Memory usage per worker
   - ps aux | grep gunicorn
   - Monitor for 10 requests

3. Cache hit rates
   - Add instrumentation to cache.py
   - Log hits/misses for 100 requests

4. Database query times
   - Log slow queries (>500ms)

5. Error rates
   - Count 5xx errors in last 24h
```

**Success Criteria:**
- [ ] Baseline metrics captured and documented
- [ ] Metrics stored in `benchmarks/baseline_YYYY-MM-DD.json`
- [ ] Comparison script ready (`scripts/compare_metrics.py`)

**Time Estimate:** 1 hour

---

### 0.3 Create Test Safety Net

**Files to Create:**
- `tests/integration/test_critical_flows.py`
- `tests/regression/test_customer_module.py`
- `tests/regression/test_products_module.py`

**Critical Test Cases:**
```python
# Test customer module (MUST NOT BREAK)
def test_customer_page_loads():
    """Verify /customers/ returns 200 and contains expected elements"""

def test_customer_filtering():
    """Verify filters work: region, date range, methods"""

def test_customer_exports():
    """Verify CSV/XLSX exports work"""

# Repeat for products, regions, suppliers, sales
```

**Success Criteria:**
- [ ] All existing modules have regression tests
- [ ] Tests pass 100% before starting improvements
- [ ] CI/CD pipeline configured (optional but recommended)

**Time Estimate:** 2-3 hours

---

### 0.4 Set Up Feature Flags

**Files to Modify:**
- `cache/features.json`
- `app/core/features.py`

**Add New Flags:**
```json
{
  "enable_churn": true,
  "enable_prophet": true,
  "enable_2fa": true,

  // NEW FLAGS FOR IMPROVEMENTS
  "enable_input_validation": false,
  "enable_optimized_dataframe": false,
  "enable_duckdb_queries": false,
  "enable_async_endpoints": false,
  "enable_cache_warming": false,
  "enable_pagination": false,
  "enable_strict_csrf": false,
  "enable_query_limits": false
}
```

**Success Criteria:**
- [ ] Feature flag system tested
- [ ] Flags can be toggled without restart (hot-reload works)
- [ ] All new flags default to `false` (opt-in)

**Time Estimate:** 30 minutes

---

### 0.5 Document Current Behavior

**Files to Create:**
- `docs/current_api_behavior.md`
- `docs/current_database_schema.md`

**What to Document:**
```markdown
# API Behavior (Current)
- POST /api/overview/summary
  - Accepts: {start, end, regions[], methods[], customers[]}
  - Returns: {status, data, filters, meta}
  - Cache: 300s
  - Auth: Required (login_required)
  - CSRF: Exempt
  - Validation: None (accepts anything)

# Data Loader Behavior
- Loads from MSSQL on refresh
- Writes to parquet (pyarrow)
- Column mapping: {...}
- Date handling: {...}
```

**Success Criteria:**
- [ ] All critical endpoints documented
- [ ] Data schemas documented
- [ ] Behavior expectations clear

**Time Estimate:** 1 hour

---

## Phase 1: Critical Security Fixes

**Priority:** 🔴 **CRITICAL - DO FIRST**
**Risk Level:** Low (additive changes)
**Time Estimate:** 1-2 days

---

### 1.1 Remove Hard-Coded Super Users

**Issue:** `app/core/rbac.py` contains developer names in source code

**Current Code (Lines 15-20):**
```python
SUPER_USERS: Dict[str, str] = {
    "admin": "admin",
    "kush patel": "admin",
    "jason pleym": "owner",
    "kyle mclaw": "gm",
}
```

**Files to Modify:**
- `app/core/rbac.py`
- `app/auth/models.py` (add is_super_user field)
- `manage.py` (add CLI command)
- `.env.example`

**Implementation Steps:**

**Step 1.1.1:** Add database field
```python
# app/auth/models.py - Add to User model
class User(Base):
    # ... existing fields ...
    is_super_user = Column(Boolean, default=False)  # NEW

# Add migration helper
def add_super_user_column():
    """Safe migration - adds column if missing"""
    # Implementation in manage.py migrate command
```

**Step 1.1.2:** Update RBAC logic
```python
# app/core/rbac.py
def is_super_user(user) -> bool:
    """Check if user is super user (from database, not hardcoded)"""
    if not user or not user.is_authenticated:
        return False
    return getattr(user, 'is_super_user', False) or user.role == 'admin'

# REMOVE the SUPER_USERS dict entirely
# Replace all references to SUPER_USERS with is_super_user(user)
```

**Step 1.1.3:** Add management command
```python
# manage.py - Add new command
@cli.command("set-super-user")
@click.option("--username", required=True)
@click.option("--revoke", is_flag=True)
def set_super_user(username, revoke):
    """Grant or revoke super user privileges"""
    # Implementation
```

**Step 1.1.4:** Environment-based override (optional)
```python
# .env (for emergency access)
SUPER_USER_OVERRIDE=admin,backup_admin
```

**Testing:**
```bash
# 1. Run migration
python manage.py migrate

# 2. Create test user
python manage.py create-admin --username=testsuper --role=admin

# 3. Grant super user
python manage.py set-super-user --username=testsuper

# 4. Verify
python manage.py list-users  # Should show is_super_user=True

# 5. Test in app
# Login as testsuper, verify access to admin pages

# 6. Revoke and test
python manage.py set-super-user --username=testsuper --revoke
# Verify access removed
```

**Rollback Plan:**
```bash
# If issues occur:
git checkout app/core/rbac.py app/auth/models.py manage.py
python run.py --fast  # Test old version still works
```

**Success Criteria:**
- [ ] No hard-coded usernames in source code
- [ ] Super user status stored in database
- [ ] Management commands work
- [ ] Existing admin users still have access
- [ ] All tests pass

**Files Changed:**
- `app/core/rbac.py` (modified)
- `app/auth/models.py` (modified)
- `manage.py` (modified)
- `.env.example` (modified)

**Time Estimate:** 2-3 hours

---

### 1.2 Add Input Validation with Pydantic

**Issue:** Endpoints accept arbitrary JSON without validation

**Files to Create:**
- `app/schemas/__init__.py`
- `app/schemas/filters.py`
- `app/schemas/overview.py`
- `app/schemas/common.py`

**Files to Modify:**
- `requirements.txt` (add pydantic>=2.5)
- `app/blueprints/overview.py` (add validation)

**Implementation Steps:**

**Step 1.2.1:** Add dependency
```bash
# requirements.txt
pydantic>=2.5
pydantic[email]>=2.5  # If email validation needed
```

**Step 1.2.2:** Create base schemas
```python
# app/schemas/common.py
from pydantic import BaseModel, Field, validator
from datetime import datetime
from typing import Optional, List

class DateRangeSchema(BaseModel):
    """Reusable date range validation"""
    start: Optional[datetime] = None
    end: Optional[datetime] = None

    @validator('end')
    def end_after_start(cls, v, values):
        if v and values.get('start') and v < values['start']:
            raise ValueError('end date must be after start date')
        return v

    @validator('start', 'end')
    def not_future(cls, v):
        if v and v > datetime.utcnow():
            raise ValueError('date cannot be in the future')
        return v

class PaginationSchema(BaseModel):
    """Reusable pagination params"""
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
```

**Step 1.2.3:** Create filter schemas
```python
# app/schemas/filters.py
from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import datetime

class FilterRequestSchema(BaseModel):
    """Validates filter requests for analytics endpoints"""

    start: Optional[datetime] = None
    end: Optional[datetime] = None
    regions: List[str] = Field(default_factory=list, max_items=100)
    methods: List[str] = Field(default_factory=list, max_items=50)
    customers: List[str] = Field(default_factory=list, max_items=1000)
    suppliers: List[str] = Field(default_factory=list, max_items=500)
    products: List[str] = Field(default_factory=list, max_items=1000)
    sales_reps: List[str] = Field(default_factory=list, max_items=100)

    protein_min: Optional[float] = Field(None, ge=0, le=100)
    protein_max: Optional[float] = Field(None, ge=0, le=100)
    protein_name_like: Optional[str] = Field(None, max_length=100)

    complete_months_only: bool = True

    @validator('end')
    def validate_date_range(cls, v, values):
        start = values.get('start')
        if start and v:
            if v < start:
                raise ValueError('end date must be after start date')
            # Max 5 year range
            if (v - start).days > 365 * 5:
                raise ValueError('date range cannot exceed 5 years')
        return v

    @validator('protein_max')
    def validate_protein_range(cls, v, values):
        min_val = values.get('protein_min')
        if min_val is not None and v is not None and v < min_val:
            raise ValueError('protein_max must be >= protein_min')
        return v

    @validator('regions', 'methods', 'customers', 'suppliers', 'products', 'sales_reps')
    def normalize_lists(cls, v):
        """Strip whitespace and remove empty strings"""
        if not v:
            return []
        return [str(item).strip() for item in v if str(item).strip()]

    class Config:
        # Allow extra fields for backward compatibility
        extra = 'ignore'
```

**Step 1.2.4:** Create overview endpoint schemas
```python
# app/schemas/overview.py
from pydantic import BaseModel, Field
from typing import Literal, Optional
from .filters import FilterRequestSchema

class SeriesRequestSchema(FilterRequestSchema):
    """Validates /api/overview/series requests"""
    metric: Literal['revenue', 'orders'] = 'revenue'
    freq: Literal['D', 'W', 'M', 'Q', 'Y'] = 'M'

class TopRequestSchema(FilterRequestSchema):
    """Validates /api/overview/top requests"""
    limit: int = Field(default=10, ge=1, le=100)
    by: Literal['revenue', 'orders', 'profit'] = 'revenue'
```

**Step 1.2.5:** Add validation decorator
```python
# app/core/validation.py
from functools import wraps
from flask import request, jsonify
from pydantic import BaseModel, ValidationError
from typing import Type

def validate_request(schema: Type[BaseModel]):
    """Decorator to validate request JSON against Pydantic schema"""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            try:
                # Parse and validate
                data = request.get_json() or {}
                validated = schema(**data)

                # Store in Flask g object for easy access
                from flask import g
                g.validated_data = validated

                return f(*args, **kwargs)

            except ValidationError as e:
                errors = e.errors()
                # Format errors nicely
                formatted = {
                    "error": "Invalid request data",
                    "details": [
                        {
                            "field": ".".join(str(x) for x in err['loc']),
                            "message": err['msg'],
                            "type": err['type']
                        }
                        for err in errors
                    ]
                }
                return jsonify(formatted), 400
            except Exception as e:
                return jsonify({"error": f"Validation failed: {str(e)}"}), 400

        return wrapped
    return decorator
```

**Step 1.2.6:** Update endpoints to use validation
```python
# app/blueprints/overview.py - EXAMPLE (don't break existing!)

# Add import
from app.core.validation import validate_request
from app.schemas.overview import FilterRequestSchema, SeriesRequestSchema
from flask import g

# Option A: Gradual migration with feature flag
@bp.route("/api/overview/summary", methods=["POST"])
@login_required
@validate_request(FilterRequestSchema)  # NEW - but optional
def summary():
    # NEW: Use validated data if validation enabled
    from app.core.features import get_flag
    if get_flag('enable_input_validation'):
        filters = g.validated_data  # Pydantic model
    else:
        # OLD: Use legacy parsing (keep working)
        filters = parse_filters(request.get_json())

    # Rest of function unchanged
    ...

# Option B: New endpoint alongside old one
@bp.route("/api/v2/overview/summary", methods=["POST"])
@login_required
@validate_request(FilterRequestSchema)
def summary_v2():
    """New validated endpoint - test before switching"""
    filters = g.validated_data
    # Use new logic
    ...
```

**Testing:**
```bash
# 1. Install dependencies
pip install pydantic>=2.5

# 2. Test valid requests
curl -X POST http://localhost:5000/api/overview/summary \
  -H "Content-Type: application/json" \
  -d '{"start": "2024-01-01", "end": "2024-12-31", "regions": ["East"]}'
# Should work as before

# 3. Test invalid requests (should now get 400 with details)
curl -X POST http://localhost:5000/api/overview/summary \
  -H "Content-Type: application/json" \
  -d '{"start": "2024-12-31", "end": "2024-01-01"}'
# Should return: {"error": "Invalid request data", "details": [...]}

# 4. Test with feature flag OFF (backward compatibility)
# Set enable_input_validation=false in cache/features.json
# Should work as before (legacy validation)

# 5. Run all tests
pytest tests/ -v
```

**Rollback Plan:**
```bash
# If validation causes issues:
# 1. Set feature flag to false
echo '{"enable_input_validation": false}' > cache/features.json

# 2. Or remove decorator from endpoints
git checkout app/blueprints/overview.py

# 3. Verify app works
python run.py --fast
```

**Success Criteria:**
- [ ] Pydantic schemas defined for all critical endpoints
- [ ] Validation decorator works
- [ ] Invalid requests return 400 with helpful errors
- [ ] Existing functionality unchanged when flag=false
- [ ] All tests pass
- [ ] Customer module still works perfectly

**Files Changed:**
- `requirements.txt` (add pydantic)
- `app/schemas/*.py` (new files)
- `app/core/validation.py` (new file)
- `app/blueprints/overview.py` (modified, backward compatible)
- `cache/features.json` (add flag)

**Time Estimate:** 3-4 hours

---

### 1.3 Implement Proper CSRF Protection

**Issue:** CSRF disabled for JSON APIs (`csrf_ext.exempt(overview_bp)`)

**Current Risk:** CSRF attacks possible via malicious websites

**Files to Modify:**
- `app/__init__.py`
- `app/blueprints/overview.py`
- `app/templates/base.html`
- `app/static/js/utils.js`

**Implementation Steps:**

**Step 1.3.1:** Add CSRF token to session
```python
# app/__init__.py - in init_extensions()

@app.before_request
def ensure_csrf_token():
    """Ensure CSRF token exists in session for AJAX requests"""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
```

**Step 1.3.2:** Create CSRF validation decorator for JSON APIs
```python
# app/core/csrf.py (NEW FILE)
from functools import wraps
from flask import request, session, jsonify
import hmac
import hashlib

def validate_json_csrf():
    """Decorator for JSON endpoints - validates X-CSRF-Token header"""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            from app.core.features import get_flag

            # Feature flag to enable gradually
            if not get_flag('enable_strict_csrf'):
                return f(*args, **kwargs)

            # Check header
            token = request.headers.get('X-CSRF-Token')
            expected = session.get('csrf_token')

            if not token or not expected:
                return jsonify({"error": "CSRF token missing"}), 403

            # Constant-time comparison
            if not hmac.compare_digest(token, expected):
                return jsonify({"error": "CSRF token invalid"}), 403

            return f(*args, **kwargs)

        return wrapped
    return decorator
```

**Step 1.3.3:** Add CSRF token to JavaScript fetch calls
```javascript
// app/static/js/utils.js

/**
 * Get CSRF token from meta tag or cookie
 */
function getCSRFToken() {
    // Try meta tag first
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) {
        return meta.getAttribute('content');
    }

    // Fallback to cookie
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
        const [name, value] = cookie.trim().split('=');
        if (name === 'csrf_token') {
            return decodeURIComponent(value);
        }
    }

    return null;
}

/**
 * Enhanced fetch with automatic CSRF token
 */
async function fetchWithCSRF(url, options = {}) {
    const csrfToken = getCSRFToken();

    // Add CSRF header for POST/PUT/PATCH/DELETE
    if (options.method && options.method.toUpperCase() !== 'GET') {
        options.headers = options.headers || {};
        options.headers['X-CSRF-Token'] = csrfToken;
    }

    return fetch(url, options);
}

// Export for use in other modules
window.fetchWithCSRF = fetchWithCSRF;
```

**Step 1.3.4:** Add CSRF token to HTML template
```html
<!-- app/templates/base.html - add to <head> section -->
<meta name="csrf-token" content="{{ session.csrf_token }}">
```

**Step 1.3.5:** Update JavaScript to use new fetch function
```javascript
// app/static/js/overview-enhanced.js - EXAMPLE

// OLD:
fetch('/api/overview/summary', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(filters)
})

// NEW (backward compatible):
fetchWithCSRF('/api/overview/summary', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(filters)
})
```

**Step 1.3.6:** Remove CSRF exemption gradually
```python
# app/__init__.py - register_blueprints()

# BEFORE:
csrf_ext.exempt(overview_bp)

# AFTER (with feature flag):
from app.core.features import get_flag
if not get_flag('enable_strict_csrf'):
    # Legacy: keep exemption until CSRF tokens deployed
    csrf_ext.exempt(overview_bp)
else:
    # New: enforce CSRF
    pass  # Don't exempt
```

**Testing:**
```bash
# 1. Enable feature flag
echo '{"enable_strict_csrf": false, ...}' > cache/features.json

# 2. Test that app still works (backward compatibility)
python run.py --fast
# Visit /overview/, verify charts load

# 3. Enable strict CSRF
echo '{"enable_strict_csrf": true, ...}' > cache/features.json

# 4. Test CSRF protection
# a) Try POST without CSRF token (should fail)
curl -X POST http://localhost:5000/api/overview/summary \
  -H "Content-Type: application/json" \
  -d '{"start": "2024-01-01"}'
# Expected: 403 CSRF token missing

# b) Visit page in browser, check that AJAX works (should have token)
# Open /overview/, open DevTools > Network
# Verify POST requests have X-CSRF-Token header

# 5. Test all pages
# /customers/, /products/, /regions/, /suppliers/, /sales/
# Verify no console errors, data loads correctly

# 6. Run full test suite
pytest tests/ -v
```

**Rollback Plan:**
```bash
# If CSRF breaks frontend:
# 1. Disable feature flag
echo '{"enable_strict_csrf": false}' > cache/features.json

# 2. Or revert changes
git checkout app/__init__.py app/static/js/*.js

# 3. Restart app
python run.py --fast
```

**Success Criteria:**
- [ ] CSRF tokens generated and stored in session
- [ ] JavaScript automatically includes tokens in requests
- [ ] Requests without tokens are rejected (when flag=true)
- [ ] All pages still work with flag=false (backward compatible)
- [ ] Customer module unaffected
- [ ] All tests pass

**Files Changed:**
- `app/__init__.py` (modified)
- `app/core/csrf.py` (new file)
- `app/templates/base.html` (modified)
- `app/static/js/utils.js` (modified)
- `app/static/js/overview-enhanced.js` (modified)
- `cache/features.json` (add flag)

**Time Estimate:** 2-3 hours

---

### 1.4 Add Query Result Limits

**Issue:** Unbounded results from filter options (could return 50K+ items)

**Files to Modify:**
- `app/services/overview_query.py`
- `app/blueprints/options.py`
- `app/core/pagination.py` (new)

**Implementation Steps:**

**Step 1.4.1:** Add pagination utilities
```python
# app/core/pagination.py (NEW FILE)
from typing import List, Dict, Any, TypeVar
from pydantic import BaseModel

T = TypeVar('T')

class PaginatedResponse(BaseModel):
    """Standard paginated response format"""
    items: List[Any]
    total: int
    limit: int
    offset: int
    has_more: bool

    @classmethod
    def create(cls, items: List[T], total: int, limit: int, offset: int):
        return cls(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < total
        )

def paginate_list(items: List[T], limit: int = 100, offset: int = 0) -> Dict[str, Any]:
    """Paginate a list and return standard format"""
    total = len(items)
    paginated_items = items[offset:offset + limit]

    return {
        "items": paginated_items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total
    }
```

**Step 1.4.2:** Update build_filter_options with limits
```python
# app/services/overview_query.py - Modify existing function

def build_filter_options(df: pd.DataFrame, limit: int = 1000) -> Dict[str, Any]:
    """Build filter options with LIMITS to prevent unbounded responses"""
    if df is None or df.empty:
        return {"regions": [], "methods": [], "customers": [], "suppliers": []}

    # Regions
    region_series = df.get("RegionName") or pd.Series(dtype='string')
    all_regions = sorted({str(x).strip() for x in region_series.dropna().astype(str) if str(x).strip()})
    regions = all_regions[:limit]  # LIMIT

    # Methods
    ship_series = shipping_name_series(df).dropna()
    all_methods = sorted({str(x).strip() for x in ship_series.astype(str) if str(x).strip()})
    methods = all_methods[:limit]  # LIMIT

    # Customers
    customer_series = df.get("CustomerName") or df.get("Name")
    if customer_series is None:
        all_customers = []
    else:
        all_customers = sorted({str(x).strip() for x in customer_series.dropna().astype(str) if str(x).strip()})
    customers = all_customers[:limit]  # LIMIT

    # Suppliers
    supplier_series = df.get("SupplierName")
    if supplier_series is None:
        all_suppliers = []
    else:
        all_suppliers = sorted({str(x).strip() for x in supplier_series.dropna().astype(str) if str(x).strip()})
    suppliers = all_suppliers[:limit]  # LIMIT

    # Sales reps
    rep_values: set[str] = set()
    for column in ("SalesRepName", "PrimarySalesRepName", "SalesRepId", "PrimarySalesRepId"):
        rep_series = df.get(column)
        if rep_series is not None:
            rep_values.update({str(x).strip() for x in rep_series.dropna().astype(str) if str(x).strip()})
    all_reps = sorted(rep_values)
    sales_reps = all_reps[:limit]  # LIMIT

    return {
        "regions": regions,
        "methods": methods,
        "customers": customers,
        "suppliers": suppliers,
        "sales_reps": sales_reps,
        # NEW: Include metadata about truncation
        "metadata": {
            "regions_total": len(all_regions),
            "regions_truncated": len(all_regions) > limit,
            "methods_total": len(all_methods),
            "methods_truncated": len(all_methods) > limit,
            "customers_total": len(all_customers),
            "customers_truncated": len(all_customers) > limit,
            "suppliers_total": len(all_suppliers),
            "suppliers_truncated": len(all_suppliers) > limit,
            "sales_reps_total": len(all_reps),
            "sales_reps_truncated": len(all_reps) > limit,
            "limit_applied": limit
        }
    }
```

**Step 1.4.3:** Add search endpoint for customers (for autocomplete)
```python
# app/blueprints/options.py - ADD NEW ENDPOINT

@bp.route("/api/options/customers/search", methods=["GET"])
@login_required
def search_customers():
    """Search customers with autocomplete - returns limited results"""
    query = request.args.get('q', '').strip()
    limit = min(int(request.args.get('limit', 50)), 100)
    offset = int(request.args.get('offset', 0))

    if len(query) < 2:
        return jsonify({"error": "Query must be at least 2 characters"}), 400

    # Get data and apply RBAC
    df = get_fact_df()
    df = scope_dataframe(df, current_user)

    # Get unique customers
    customer_col = df.get("CustomerName") or df.get("Name")
    if customer_col is None:
        return jsonify(paginate_list([], limit, offset))

    all_customers = sorted({str(x).strip() for x in customer_col.dropna().astype(str) if str(x).strip()})

    # Filter by query (case-insensitive)
    query_lower = query.lower()
    filtered = [c for c in all_customers if query_lower in c.lower()]

    # Paginate
    result = paginate_list(filtered, limit, offset)

    return jsonify(result)
```

**Step 1.4.4:** Update frontend to handle truncation
```javascript
// app/static/js/filters-enhanced.js - ADD

/**
 * Load filter options with truncation warning
 */
async function loadFilterOptions() {
    const response = await fetchWithCSRF('/api/overview/options', {method: 'POST'});
    const data = await response.json();

    // Check for truncation
    if (data.metadata) {
        if (data.metadata.customers_truncated) {
            console.warn(`Customers list truncated: showing ${data.customers.length} of ${data.metadata.customers_total}`);
            // Show autocomplete search instead of dropdown
            enableCustomerAutocomplete();
        }
        // Similar for other fields
    }

    // Populate dropdowns
    populateFilterDropdowns(data);
}

/**
 * Enable autocomplete for customers (when list too large)
 */
function enableCustomerAutocomplete() {
    const customerSelect = document.getElementById('customer-filter');
    if (!customerSelect) return;

    // Replace select with autocomplete input
    const wrapper = customerSelect.parentElement;
    const input = document.createElement('input');
    input.type = 'text';
    input.placeholder = 'Search customers...';
    input.id = 'customer-search';
    input.className = customerSelect.className;

    wrapper.replaceChild(input, customerSelect);

    // Add autocomplete logic
    setupAutocomplete(input, '/api/options/customers/search');
}
```

**Testing:**
```bash
# 1. Test with small dataset (should show all)
# Verify filter dropdowns populated

# 2. Test with large dataset (should truncate)
# Create test with 10K+ customers
python -c "
import pandas as pd
# Generate 10K customers
df = pd.read_parquet('cache/fact_analytics.parquet')
# Duplicate customers
for i in range(10000):
    df.loc[len(df)] = df.iloc[0]
    df.loc[len(df)-1, 'CustomerName'] = f'Customer {i}'
df.to_parquet('cache/test_large.parquet')
"

# Set PARQUET_PATH=cache/test_large.parquet
# Reload app, verify:
# - Only 1000 customers shown in dropdown
# - metadata.customers_truncated = true
# - Console warning shown

# 3. Test search endpoint
curl "http://localhost:5000/api/options/customers/search?q=acme&limit=20"
# Should return max 20 results

# 4. Verify customer module still works
# Visit /customers/, test filters

# 5. Run tests
pytest tests/ -v
```

**Rollback Plan:**
```bash
# If limits break functionality:
git checkout app/services/overview_query.py app/blueprints/options.py
python run.py --fast
```

**Success Criteria:**
- [ ] Filter options limited to 1000 items max
- [ ] Metadata indicates when truncation occurred
- [ ] Search endpoint works for autocomplete
- [ ] Customer module unaffected
- [ ] All tests pass

**Files Changed:**
- `app/core/pagination.py` (new file)
- `app/services/overview_query.py` (modified)
- `app/blueprints/options.py` (add search endpoint)
- `app/static/js/filters-enhanced.js` (modified)

**Time Estimate:** 2-3 hours

---

## Phase 2: Performance Foundation

**Priority:** 🟠 **HIGH - AFTER SECURITY FIXES**
**Risk Level:** Medium (modifies data access patterns)
**Time Estimate:** 2-3 days

---

### 2.1 Optimize DataFrame Memory with Categorical Types

**Issue:** String columns consume excessive memory

**Impact:** 70% memory reduction for dimension columns

**Files to Modify:**
- `app/core/data_service.py`
- `data_loader.py`

**Implementation Steps:**

**Step 2.1.1:** Create optimized DataFrame loader
```python
# app/core/data_service.py - ADD NEW FUNCTION

def optimize_dataframe_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Convert high-cardinality string columns to categorical dtype

    Memory savings: 50-70% for dimension columns
    Performance: Faster groupby operations
    """
    if df is None or df.empty:
        return df

    # Columns to convert to categorical (low cardinality)
    categorical_candidates = [
        'RegionName', 'Region_Name', 'RegionCode',
        'ShippingMethod', 'ShippingMethodName', 'Shipping_Method',
        'OrderStatus', 'Status',
        'ProductCategory', 'Category',
        'PaymentMethod',
        'SalesRepName', 'PrimarySalesRepName',
        'SupplierName'
    ]

    for col in categorical_candidates:
        if col in df.columns:
            # Only convert if cardinality < 50% of rows (efficiency check)
            unique_ratio = df[col].nunique() / len(df)
            if unique_ratio < 0.5:
                df[col] = df[col].astype('category')

    # Optimize numeric columns
    numeric_candidates = [
        'Quantity', 'Units', 'Weight', 'OrderId', 'CustomerId', 'ProductId'
    ]

    for col in numeric_candidates:
        if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
            # Downcast integers
            if pd.api.types.is_integer_dtype(df[col]):
                df[col] = pd.to_numeric(df[col], downcast='integer')
            # Downcast floats
            elif pd.api.types.is_float_dtype(df[col]):
                df[col] = pd.to_numeric(df[col], downcast='float')

    return df

# Update existing get_fact_df function
def get_fact_df() -> pd.DataFrame:
    """Load fact dataframe with optional optimization"""
    from app.core.features import get_flag

    df = load_canonical_df()

    # Apply optimization if enabled
    if get_flag('enable_optimized_dataframe'):
        df = optimize_dataframe_dtypes(df)

    return df
```

**Step 2.1.2:** Add memory profiling utility
```python
# app/core/profiling.py (NEW FILE)

import pandas as pd
from typing import Dict

def profile_dataframe_memory(df: pd.DataFrame) -> Dict[str, any]:
    """Profile DataFrame memory usage by column"""
    if df is None or df.empty:
        return {}

    memory_usage = df.memory_usage(deep=True)
    total_bytes = memory_usage.sum()

    profile = {
        "total_mb": total_bytes / 1024 / 1024,
        "rows": len(df),
        "columns": len(df.columns),
        "bytes_per_row": total_bytes / len(df) if len(df) > 0 else 0,
        "top_consumers": []
    }

    # Sort columns by memory usage
    col_memory = memory_usage.drop('Index').sort_values(ascending=False)

    for col, bytes_used in col_memory.head(10).items():
        profile["top_consumers"].append({
            "column": col,
            "mb": bytes_used / 1024 / 1024,
            "dtype": str(df[col].dtype),
            "unique_values": int(df[col].nunique()),
            "null_count": int(df[col].isna().sum())
        })

    return profile

# Add CLI command to profile
# python manage.py profile-dataframe
```

**Step 2.1.3:** Compare before/after memory usage
```python
# tests/performance/test_memory_optimization.py (NEW FILE)

def test_categorical_optimization():
    """Verify categorical conversion reduces memory"""
    df_original = pd.read_parquet(PARQUET_PATH)

    # Measure before
    mem_before = df_original.memory_usage(deep=True).sum() / 1024 / 1024

    # Optimize
    df_optimized = optimize_dataframe_dtypes(df_original.copy())

    # Measure after
    mem_after = df_optimized.memory_usage(deep=True).sum() / 1024 / 1024

    # Assert reduction
    reduction_pct = (mem_before - mem_after) / mem_before * 100
    print(f"Memory reduced by {reduction_pct:.1f}%")
    assert reduction_pct > 30, "Expected at least 30% memory reduction"

    # Verify data integrity
    for col in df_original.columns:
        if col in df_optimized.columns:
            assert df_original[col].equals(df_optimized[col].astype(df_original[col].dtype))
```

**Testing:**
```bash
# 1. Profile current memory usage
python manage.py profile-dataframe
# Save output to benchmarks/memory_before.json

# 2. Enable optimization
echo '{"enable_optimized_dataframe": true}' > cache/features.json

# 3. Profile optimized memory
python manage.py profile-dataframe
# Save output to benchmarks/memory_after.json

# 4. Compare results
python scripts/compare_memory.py benchmarks/memory_before.json benchmarks/memory_after.json
# Expected: 50-70% reduction in dimension columns

# 5. Test functionality
# Visit all pages: /customers/, /products/, /regions/, /suppliers/
# Verify data looks correct (no corruption)

# 6. Test performance
python tests/performance/test_memory_optimization.py

# 7. Run full test suite
pytest tests/ -v
```

**Rollback Plan:**
```bash
# Disable optimization
echo '{"enable_optimized_dataframe": false}' > cache/features.json
# No code changes needed - feature flag controls it
```

**Success Criteria:**
- [ ] Memory usage reduced by 50-70% for dimension columns
- [ ] Data integrity maintained (spot checks)
- [ ] Query performance same or better
- [ ] All modules work correctly
- [ ] Tests pass

**Files Changed:**
- `app/core/data_service.py` (add optimization function)
- `app/core/profiling.py` (new file)
- `tests/performance/test_memory_optimization.py` (new file)
- `cache/features.json` (add flag)

**Time Estimate:** 2-3 hours

---

### 2.2 Add Columnar Filtering (Load Only Needed Columns)

**Issue:** Loading entire DataFrame when only few columns needed

**Impact:** 50-80% faster load times for endpoints needing subset of columns

**Files to Modify:**
- `app/core/data_service.py`
- `app/blueprints/overview.py`

**Implementation Steps:**

**Step 2.2.1:** Create column-aware loader
```python
# app/core/data_service.py - ADD

# Define column sets for different use cases
COLUMN_SETS = {
    "minimal": ["Date", "OrderId", "Revenue", "Cost", "Profit"],
    "customers": ["Date", "CustomerId", "CustomerName", "Revenue", "Cost", "Profit", "RegionName"],
    "products": ["Date", "ProductId", "ProductName", "SKU", "Revenue", "Cost", "CategoryName"],
    "overview": ["Date", "Revenue", "Cost", "Profit", "OrderId", "RegionName", "ShippingMethod"],
    "velocity": ["Date", "ProductId", "ProductName", "SKU", "Units", "Weight", "Revenue"],
    "full": None  # All columns
}

def get_fact_df_columns(column_set: str = "full", extra_columns: List[str] = None) -> pd.DataFrame:
    """Load DataFrame with only specified columns

    Args:
        column_set: Predefined set ('minimal', 'customers', 'products', etc.)
        extra_columns: Additional columns to include

    Returns:
        DataFrame with only requested columns
    """
    from app.core.features import get_flag

    # If optimization disabled, load full DF (legacy behavior)
    if not get_flag('enable_optimized_dataframe'):
        return get_fact_df()

    # Determine columns to load
    columns = COLUMN_SETS.get(column_set)

    if columns is not None:
        # Add extra columns if specified
        if extra_columns:
            columns = list(set(columns + extra_columns))

        # Always include Date for filtering
        if "Date" not in columns:
            columns.append("Date")

        try:
            # Load only specified columns
            df = pd.read_parquet(
                Path(os.getenv("PARQUET_PATH", "cache/fact_analytics.parquet")),
                columns=columns
            )
        except Exception as e:
            # Fallback to full load if columns don't exist
            current_app.logger.warning(f"Columnar load failed: {e}, loading full DF")
            df = get_fact_df()
    else:
        # Load all columns
        df = get_fact_df()

    # Apply optimizations
    if get_flag('enable_optimized_dataframe'):
        df = optimize_dataframe_dtypes(df)

    return df
```

**Step 2.2.2:** Update endpoints to use columnar loading
```python
# app/blueprints/overview.py - EXAMPLE

@bp.route("/api/overview/cards", methods=["POST"])
@login_required
def cards():
    """KPI cards - only need summary columns"""
    from app.core.features import get_flag

    if get_flag('enable_optimized_dataframe'):
        # NEW: Load only needed columns
        df = get_fact_df_columns(
            column_set="overview",
            extra_columns=["CustomerName"]  # If needed
        )
    else:
        # OLD: Load everything
        df = get_fact_df()

    # Rest unchanged
    df = scope_dataframe(df, current_user)
    filters = parse_filters(request.get_json())
    df = apply_filter_params(df, filters)

    result = cards_summary(df, filters)
    return jsonify(result)
```

**Step 2.2.3:** Add benchmarking
```python
# tests/performance/test_columnar_loading.py

import time
import pandas as pd

def test_columnar_vs_full_loading():
    """Compare load times: columnar vs full"""

    # Test 1: Full load
    start = time.perf_counter()
    df_full = pd.read_parquet(PARQUET_PATH)
    time_full = time.perf_counter() - start
    mem_full = df_full.memory_usage(deep=True).sum() / 1024 / 1024

    # Test 2: Columnar load (minimal)
    start = time.perf_counter()
    df_minimal = pd.read_parquet(PARQUET_PATH, columns=["Date", "Revenue", "OrderId"])
    time_minimal = time.perf_counter() - start
    mem_minimal = df_minimal.memory_usage(deep=True).sum() / 1024 / 1024

    print(f"Full load: {time_full:.3f}s, {mem_full:.1f}MB")
    print(f"Minimal load: {time_minimal:.3f}s, {mem_minimal:.1f}MB")
    print(f"Speedup: {time_full / time_minimal:.1f}x")
    print(f"Memory saved: {(1 - mem_minimal/mem_full)*100:.1f}%")

    assert time_minimal < time_full, "Columnar load should be faster"
    assert mem_minimal < mem_full * 0.5, "Columnar load should use <50% memory"
```

**Testing:**
```bash
# 1. Benchmark before
python -c "
import time, pandas as pd
start = time.time()
df = pd.read_parquet('cache/fact_analytics.parquet')
print(f'Full load: {time.time()-start:.3f}s, {len(df.columns)} columns')
"

# 2. Benchmark after (columnar)
python -c "
import time, pandas as pd
start = time.time()
df = pd.read_parquet('cache/fact_analytics.parquet', columns=['Date','Revenue','OrderId'])
print(f'Columnar load: {time.time()-start:.3f}s, {len(df.columns)} columns')
"

# 3. Enable feature and test endpoints
echo '{"enable_optimized_dataframe": true}' > cache/features.json
python run.py --fast

# 4. Time overview API (should be faster)
time curl -X POST http://localhost:5000/api/overview/cards \
  -H "Content-Type: application/json" \
  -d '{"start": "2024-01-01", "end": "2024-12-31"}'

# 5. Verify customer module still works
# Visit /customers/ - should still have all needed columns

# 6. Run tests
pytest tests/performance/test_columnar_loading.py -v
```

**Rollback Plan:**
```bash
# Disable feature flag
echo '{"enable_optimized_dataframe": false}' > cache/features.json
```

**Success Criteria:**
- [ ] Columnar loading 2-5× faster than full load
- [ ] Memory usage reduced proportionally
- [ ] All endpoints still work correctly
- [ ] Customer module unaffected
- [ ] Tests pass

**Files Changed:**
- `app/core/data_service.py` (add columnar loader)
- `app/blueprints/overview.py` (use columnar loading)
- `tests/performance/test_columnar_loading.py` (new file)

**Time Estimate:** 2-3 hours

---

### 2.3 Implement Request-Scoped DataFrame Caching

**Issue:** Same DataFrame loaded multiple times per request

**Impact:** Eliminate redundant parquet reads within single request

**Files to Modify:**
- `app/core/data_service.py`
- `app/__init__.py`

**Implementation Steps:**

**Step 2.3.1:** Add request-scoped cache
```python
# app/core/data_service.py - MODIFY

def get_fact_df() -> pd.DataFrame:
    """Load fact dataframe with request-scoped caching

    Within a single request, this returns the same DataFrame instance
    to avoid multiple parquet reads.
    """
    from flask import g

    # Check request-scoped cache
    if hasattr(g, '_cached_fact_df'):
        return g._cached_fact_df

    # Load and cache
    df = load_canonical_df()

    # Apply optimizations if enabled
    from app.core.features import get_flag
    if get_flag('enable_optimized_dataframe'):
        df = optimize_dataframe_dtypes(df)

    # Store in request scope
    g._cached_fact_df = df

    return df

def get_fact_df_columns(column_set: str = "full", extra_columns: List[str] = None) -> pd.DataFrame:
    """Load DataFrame with columnar filtering and request-scoped caching"""
    from flask import g

    # Create cache key based on columns requested
    cache_key = f'_cached_fact_df_{column_set}_{",".join(sorted(extra_columns or []))}'

    # Check request-scoped cache
    if hasattr(g, cache_key):
        return getattr(g, cache_key)

    # Load with columns
    # ... (existing columnar loading code) ...

    # Store in request scope
    setattr(g, cache_key, df)

    return df
```

**Step 2.3.2:** Add cache cleanup on teardown
```python
# app/__init__.py - in init_extensions()

@app.teardown_request
def cleanup_request_cache(exception=None):
    """Clean up request-scoped DataFrame cache to free memory"""
    # Remove cached DataFrames
    for attr in dir(g):
        if attr.startswith('_cached_fact_df'):
            try:
                delattr(g, attr)
            except Exception:
                pass
```

**Step 2.3.3:** Add instrumentation to measure cache hits
```python
# app/core/data_service.py - ADD

_REQUEST_CACHE_STATS = {
    'hits': 0,
    'misses': 0
}

def get_fact_df() -> pd.DataFrame:
    from flask import g

    if hasattr(g, '_cached_fact_df'):
        _REQUEST_CACHE_STATS['hits'] += 1
        current_app.logger.debug("Request cache HIT for fact_df")
        return g._cached_fact_df

    _REQUEST_CACHE_STATS['misses'] += 1
    current_app.logger.debug("Request cache MISS for fact_df")

    df = load_canonical_df()
    # ... rest ...

def get_cache_stats() -> dict:
    """Get request cache statistics"""
    total = _REQUEST_CACHE_STATS['hits'] + _REQUEST_CACHE_STATS['misses']
    hit_rate = _REQUEST_CACHE_STATS['hits'] / total * 100 if total > 0 else 0

    return {
        'hits': _REQUEST_CACHE_STATS['hits'],
        'misses': _REQUEST_CACHE_STATS['misses'],
        'total': total,
        'hit_rate_pct': round(hit_rate, 2)
    }

# Add to admin metrics endpoint
# /api/admin/metrics
```

**Testing:**
```bash
# 1. Add logging to see cache behavior
export LOG_LEVEL=DEBUG

# 2. Make request that uses DF multiple times
curl -X POST http://localhost:5000/api/overview/summary ...

# 3. Check logs for cache hits
# Should see:
# "Request cache MISS for fact_df"  (first access)
# "Request cache HIT for fact_df"   (subsequent accesses)

# 4. Check metrics
curl http://localhost:5000/api/admin/metrics
# Should show hit_rate_pct > 50%

# 5. Test all pages work
# /customers/, /products/, etc.

# 6. Monitor memory - should not grow with repeated requests
# Make 100 requests, check memory stays stable
for i in {1..100}; do
  curl -X POST http://localhost:5000/api/overview/cards -d '{}' &
done
wait
ps aux | grep gunicorn  # Check RSS memory
```

**Rollback Plan:**
```bash
# Remove caching from g object
git checkout app/core/data_service.py app/__init__.py
```

**Success Criteria:**
- [ ] Request cache hit rate >50% for multi-step endpoints
- [ ] No memory leaks (memory stable over 100+ requests)
- [ ] All pages work correctly
- [ ] Tests pass

**Files Changed:**
- `app/core/data_service.py` (add request caching)
- `app/__init__.py` (add teardown cleanup)

**Time Estimate:** 1-2 hours

---

### 2.4 Add Comprehensive Error Handling

**Issue:** Broad exception handlers swallow errors silently

**Files to Create:**
- `app/core/error_handlers.py`

**Files to Modify:**
- `app/__init__.py`
- All blueprint files (gradually)

**Implementation Steps:**

**Step 2.4.1:** Create centralized error handling
```python
# app/core/error_handlers.py (NEW FILE)

from flask import Flask, jsonify, request, current_app
from werkzeug.exceptions import HTTPException
from flask_login import current_user
import traceback
import sys

class APIError(Exception):
    """Base class for API errors"""
    status_code = 500

    def __init__(self, message, status_code=None, payload=None):
        super().__init__()
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['error'] = self.message
        rv['status'] = self.status_code
        return rv

class ValidationError(APIError):
    """Validation errors"""
    status_code = 400

class AuthorizationError(APIError):
    """Authorization errors"""
    status_code = 403

class NotFoundError(APIError):
    """Resource not found"""
    status_code = 404

class DataError(APIError):
    """Data processing errors"""
    status_code = 422

def register_error_handlers(app: Flask):
    """Register centralized error handlers"""

    @app.errorhandler(APIError)
    def handle_api_error(error):
        """Handle custom API errors"""
        response = jsonify(error.to_dict())
        response.status_code = error.status_code
        return response

    @app.errorhandler(HTTPException)
    def handle_http_exception(error):
        """Handle HTTP exceptions (400, 404, 500, etc.)"""
        current_app.logger.warning(
            f"HTTP {error.code}: {error.description}",
            extra={
                "path": request.path,
                "method": request.method,
                "user_id": getattr(current_user, 'id', None)
            }
        )

        return jsonify({
            "error": error.description,
            "status": error.code
        }), error.code

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        """Handle unexpected errors"""
        # Log full traceback
        exc_type, exc_value, exc_tb = sys.exc_info()
        tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)

        current_app.logger.error(
            f"Unhandled exception: {error}",
            extra={
                "path": request.path,
                "method": request.method,
                "user_id": getattr(current_user, 'id', None),
                "traceback": "".join(tb_lines)
            },
            exc_info=True
        )

        # Return error response
        if app.config.get('ENV') == 'production':
            # Production: hide details
            message = "An internal error occurred"
            details = None
        else:
            # Development: show details
            message = str(error)
            details = {
                "type": type(error).__name__,
                "traceback": tb_lines[-3:] if len(tb_lines) > 3 else tb_lines
            }

        response = {
            "error": message,
            "status": 500
        }
        if details:
            response["details"] = details

        return jsonify(response), 500
```

**Step 2.4.2:** Register error handlers
```python
# app/__init__.py - in create_app()

def create_app():
    app = Flask(__name__)

    # ... existing setup ...

    # Register error handlers
    from app.core.error_handlers import register_error_handlers
    register_error_handlers(app)

    # ... rest ...

    return app
```

**Step 2.4.3:** Update endpoints to use structured errors
```python
# app/blueprints/overview.py - EXAMPLE

from app.core.error_handlers import ValidationError, DataError

@bp.route("/api/overview/summary", methods=["POST"])
@login_required
def summary():
    try:
        # Get data
        df = get_fact_df()
        if df is None or df.empty:
            raise DataError("No data available")

        # Parse filters
        filters = parse_filters(request.get_json())

        # Apply filters
        df = apply_filter_params(df, filters)
        if df.empty:
            raise DataError("No data matches the specified filters")

        # Compute overview
        result = compute_overview(df, filters)

        return jsonify(result)

    except ValidationError:
        raise  # Re-raise to use custom handler
    except DataError:
        raise  # Re-raise to use custom handler
    except Exception as e:
        # Log and convert to DataError
        current_app.logger.error(f"Overview computation failed: {e}", exc_info=True)
        raise DataError(f"Failed to compute overview: {str(e)}")
```

**Step 2.4.4:** Add error monitoring endpoint
```python
# app/blueprints/admin_api.py - ADD

@bp.route("/api/admin/errors/recent", methods=["GET"])
@requires_roles("admin")
def recent_errors():
    """Get recent errors from logs"""
    # Parse last N lines of error log
    # Return structured errors for admin dashboard
    pass
```

**Testing:**
```bash
# 1. Test validation errors
curl -X POST http://localhost:5000/api/overview/summary \
  -H "Content-Type: application/json" \
  -d '{"start": "invalid-date"}'
# Expected: 400 with structured error

# 2. Test with empty data
# Create empty parquet, test graceful error

# 3. Test unexpected errors (should log and return 500)
# Introduce intentional error in code, verify logged

# 4. Check logs
tail -f logs/app.jsonl | grep ERROR

# 5. Verify customer module still works
# Visit /customers/, test filters

# 6. Run tests
pytest tests/ -v
```

**Rollback Plan:**
```bash
git checkout app/core/error_handlers.py app/__init__.py app/blueprints/*.py
```

**Success Criteria:**
- [ ] All errors logged with context
- [ ] Structured error responses (JSON)
- [ ] Production mode hides sensitive details
- [ ] Development mode shows helpful details
- [ ] Customer module unaffected
- [ ] Tests pass

**Files Changed:**
- `app/core/error_handlers.py` (new file)
- `app/__init__.py` (register handlers)
- `app/blueprints/overview.py` (use structured errors)

**Time Estimate:** 2-3 hours

---

## Phase 3: Memory & Cache Optimization

**Priority:** 🟡 **MEDIUM - AFTER PERFORMANCE FOUNDATION**
**Risk Level:** Medium-High
**Time Estimate:** 3-4 days

*(Continuing in same detailed format for remaining phases...)*

---

### 3.1 Implement Intelligent Cache Warming

*(Detailed steps similar to above)*

### 3.2 Add Redis Cache with Eviction Policy

*(Detailed steps similar to above)*

### 3.3 Optimize Cache Key Strategy

*(Detailed steps similar to above)*

---

## Phase 4: Advanced Performance

**Priority:** 🟡 **MEDIUM**
**Risk Level:** High
**Time Estimate:** 5-7 days

### 4.1 Implement Async Endpoints (Optional)

*(Detailed steps...)*

### 4.2 Add Background Task Queue (Celery)

*(Detailed steps...)*

### 4.3 Implement DuckDB for Analytics Queries

*(Detailed steps...)*

---

## Phase 5: Scalability & Observability

**Priority:** 🟢 **LOW - NICE TO HAVE**
**Risk Level:** Low
**Time Estimate:** 3-5 days

### 5.1 Add Distributed Tracing (OpenTelemetry)

*(Detailed steps...)*

### 5.2 Implement Advanced Metrics Collection

*(Detailed steps...)*

### 5.3 Add Real-time Performance Dashboard

*(Detailed steps...)*

---

## Phase 6: Nice-to-Have Enhancements

*(Additional improvements...)*

---

## Testing Strategy

### Pre-Change Testing Checklist

Before ANY change:
```bash
# 1. Full backup
python scripts/backup_before_changes.py

# 2. Run all tests
pytest tests/ -v --cov=app

# 3. Manual smoke test
python run.py --fast
# Visit all critical pages:
# - /
# - /customers/
# - /products/
# - /regions/
# - /suppliers/
# - /sales/
# - /overview/
# Verify data loads, filters work, exports work

# 4. Capture baseline metrics
python scripts/capture_baseline.py

# 5. Create git checkpoint
git add .
git commit -m "Checkpoint before [CHANGE NAME]"
git tag "pre-[CHANGE NAME]"
```

### Post-Change Testing Checklist

After EVERY change:
```bash
# 1. Unit tests
pytest tests/unit/ -v

# 2. Integration tests
pytest tests/integration/ -v

# 3. Regression tests (critical modules)
pytest tests/regression/test_customer_module.py -v
pytest tests/regression/test_products_module.py -v

# 4. Performance tests
pytest tests/performance/ -v

# 5. Manual verification
# - Login works
# - All pages load
# - Filters work
# - Charts render
# - Exports work
# - No console errors

# 6. Compare metrics
python scripts/compare_metrics.py

# 7. If all pass: commit
git add .
git commit -m "[PHASE X.Y] [DESCRIPTION]"
git tag "post-[CHANGE NAME]"
```

---

## Rollback Procedures

### Immediate Rollback (Feature Flag)

```bash
# For changes controlled by feature flags:
# 1. Disable the flag
python -c "
import json
with open('cache/features.json', 'r') as f:
    flags = json.load(f)
flags['enable_[FEATURE]'] = False
with open('cache/features.json', 'w') as f:
    json.dump(flags, f, indent=2)
"

# 2. Restart app
pkill -f gunicorn
python run.py --gunicorn

# 3. Verify working
curl http://localhost:8000/healthz
```

### Code Rollback (Git)

```bash
# 1. Find last working tag
git tag | grep pre-

# 2. Rollback to tag
git checkout tags/pre-[CHANGE NAME]

# 3. Or rollback specific files
git checkout HEAD~1 app/blueprints/overview.py

# 4. Restart
python run.py --fast

# 5. Verify
pytest tests/regression/ -v
```

### Full System Restore (Backup)

```bash
# 1. Stop app
pkill -f gunicorn

# 2. Restore from backup
python scripts/restore_backup.py backups/pre_improvement_YYYY-MM-DD_HH-MM-SS.zip

# 3. Verify restoration
ls -la auth.db cache/*.parquet .env

# 4. Restart
python run.py --gunicorn

# 5. Smoke test
python scripts/smoke_test.py
```

---

## Success Metrics

### After Phase 1 (Security)

| Metric | Before | Target | Actual |
|--------|--------|--------|--------|
| Hard-coded credentials | Yes | No | ___ |
| CSRF protection | Disabled | Enabled | ___ |
| Input validation | None | Pydantic | ___ |
| Unbounded queries | Yes | Limited | ___ |

### After Phase 2 (Performance Foundation)

| Metric | Before | Target | Actual |
|--------|--------|--------|--------|
| Memory per worker | 500MB+ | 150MB | ___ |
| Overview API response | 2-5s | 500ms | ___ |
| Request cache hits | 0% | 50%+ | ___ |
| Error logging | Basic | Structured | ___ |

### After Phase 3 (Cache Optimization)

| Metric | Before | Target | Actual |
|--------|--------|--------|--------|
| Cache hit rate | 40% | 80%+ | ___ |
| Redis eviction policy | None | LRU | ___ |
| Cache memory usage | Unbounded | <2GB | ___ |

### After Phase 4 (Advanced Performance)

| Metric | Before | Target | Actual |
|--------|--------|--------|--------|
| Concurrent users | 8-10 | 100+ | ___ |
| Async endpoints | 0 | 5+ | ___ |
| Background tasks | Blocking | Async | ___ |

### After Phase 5 (Observability)

| Metric | Before | Target | Actual |
|--------|--------|--------|--------|
| Distributed tracing | No | Yes | ___ |
| Real-time metrics | No | Yes | ___ |
| Alert system | No | Yes | ___ |

---

## Implementation Notes

### Critical Reminders

1. **NEVER modify customer module directly** - only shared utilities
2. **ALWAYS test with feature flags OFF first** (backward compatibility)
3. **ALWAYS create backup before changes**
4. **ALWAYS run regression tests after changes**
5. **COMMIT after each successful improvement**
6. **Document any issues encountered in ISSUES.md**

### Communication Plan

After each phase:
1. Update this file with "Actual" metrics
2. Document any deviations from plan
3. Note any new issues discovered
4. Update timeline estimates for remaining phases

---

## Appendix A: File Inventory

**New Files Created:**
- `scripts/backup_before_changes.py`
- `scripts/restore_backup.py`
- `scripts/capture_baseline.py`
- `scripts/compare_metrics.py`
- `tests/performance/baseline_metrics.py`
- `tests/integration/test_critical_flows.py`
- `tests/regression/test_customer_module.py`
- `tests/regression/test_products_module.py`
- `app/schemas/*.py` (multiple)
- `app/core/validation.py`
- `app/core/csrf.py`
- `app/core/pagination.py`
- `app/core/profiling.py`
- `app/core/error_handlers.py`
- `docs/current_api_behavior.md`
- `docs/current_database_schema.md`

**Files Modified:**
- `app/core/rbac.py`
- `app/auth/models.py`
- `app/__init__.py`
- `app/config.py`
- `app/core/data_service.py`
- `app/blueprints/overview.py`
- `app/services/overview_query.py`
- `app/templates/base.html`
- `app/static/js/*.js` (multiple)
- `requirements.txt`
- `cache/features.json`
- `.env.example`
- `manage.py`

---

## Appendix B: Estimated Total Effort

| Phase | Days | Risk | Dependencies |
|-------|------|------|--------------|
| Phase 0: Pre-work | 0.5 | Low | None |
| Phase 1: Security | 1-2 | Low | Phase 0 |
| Phase 2: Performance | 2-3 | Medium | Phase 1 |
| Phase 3: Cache | 3-4 | Medium | Phase 2 |
| Phase 4: Advanced | 5-7 | High | Phase 3 |
| Phase 5: Observability | 3-5 | Low | Phase 4 |
| Phase 6: Enhancements | 3-5 | Low | Phase 5 |
| **Total** | **17-26 days** | | |

**Minimum Viable Improvement (Phases 1-2):** 3-5 days
**Recommended Implementation (Phases 1-3):** 6-9 days
**Full Implementation (All Phases):** 17-26 days

---

## Appendix C: Quick Reference Commands

```bash
# Backup before changes
python scripts/backup_before_changes.py

# Run full test suite
pytest tests/ -v --cov=app --cov-report=html

# Smoke test critical modules
pytest tests/regression/ -v

# Benchmark current performance
python tests/performance/run_baseline.sh

# Profile memory usage
python manage.py profile-dataframe

# Check cache statistics
curl http://localhost:5000/api/admin/metrics

# Toggle feature flag
python -c "import json; f=open('cache/features.json','r+'); d=json.load(f); d['enable_X']=True; f.seek(0); json.dump(d,f,indent=2); f.truncate()"

# View recent errors
tail -f logs/app.jsonl | grep ERROR

# Rollback to last checkpoint
git checkout tags/pre-[CHANGE]

# Full restore from backup
python scripts/restore_backup.py backups/[FILE].zip
```

---

**END OF IMPROVEMENT PLAN**

**Next Steps:**
1. Review this plan
2. Adjust timelines/priorities as needed
3. Create backups (Phase 0)
4. Begin Phase 1.1 (Remove hard-coded super users)

**Questions? Issues?**
Document in `ISSUES.md` and tag with phase number.
