"""
Simulate the exact API call that the overview page makes.
This tests the full pipeline: data load -> RBAC -> filters -> compute.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 70)
print("SIMULATING OVERVIEW API CALL")
print("=" * 70)

try:
    from app.blueprints.overview import _load_for, CARDS_COLUMNS, SERIES_COLUMNS
    from app.services.filters import parse_filters, apply_filters
    from app.services.overview_query import compute_overview
    from app.core.rbac import scope_dataframe
    from app.auth.models import User, get_session
    import pandas as pd

    # Simulate what the endpoint does
    print("\n[1] Loading data for overview endpoint...")
    cols = list(set(CARDS_COLUMNS) | set(SERIES_COLUMNS) | {"ProductName", "SkuName"})

    # This is what _load_for does
    import data_loader as loader
    try:
        df = loader.get_fact_df(columns=cols)
    except TypeError:
        df = loader.get_fact_df()
    print(f"    Raw data: {len(df):,} rows")

    # Get admin user
    s = get_session()
    admin = s.query(User).filter_by(username='admin').first()

    # Apply RBAC scoping (what the endpoint does at line 424)
    print("\n[2] Applying RBAC scoping for admin user...")
    scoped = scope_dataframe(df, admin)
    print(f"    After RBAC: {len(scoped):,} rows")

    if len(scoped) == 0:
        print("    ** ERROR: RBAC filtered out all data! **")
        s.close()
        sys.exit(1)

    # Test different payloads that frontend might send
    test_cases = [
        ("Empty payload {}", {}),
        ("With ['All'] arrays", {
            'start': None,
            'end': None,
            'regions': ['All'],
            'methods': ['All'],
            'customers': ['All'],
            'suppliers': ['All']
        }),
        ("With empty arrays", {
            'start': None,
            'end': None,
            'regions': [],
            'methods': [],
            'customers': [],
            'suppliers': []
        }),
    ]

    for name, payload in test_cases:
        print(f"\n[3] Testing {name}...")

        # Parse filters (what endpoint does)
        params = parse_filters(payload)
        print(f"    Parsed start: {params.start}")
        print(f"    Parsed end: {params.end}")
        print(f"    Parsed regions: {params.regions}")
        print(f"    Parsed customers: {params.customers}")

        # Apply filters
        dff = apply_filters(scoped, params)
        print(f"    After filters: {len(dff):,} rows")

        if len(dff) == 0:
            print(f"    ** ERROR: All data filtered out with {name}! **")

            # Debug: Check date range
            if 'Date' in scoped.columns:
                dates = pd.to_datetime(scoped['Date'], errors='coerce').dropna()
                if not dates.empty:
                    print(f"    Data date range: {dates.min().date()} to {dates.max().date()}")
                    if params.start and params.end:
                        print(f"    Filter range: {params.start.date()} to {params.end.date()}")
            continue

        # Compute overview (what endpoint does)
        result = compute_overview(dff)
        kpis = result.get('kpis', {})

        print(f"    ** SUCCESS! **")
        print(f"    Revenue: ${kpis.get('total_revenue', 0):,.2f}")
        print(f"    Orders: {kpis.get('total_orders', 0):,}")
        print(f"    Customers: {kpis.get('total_customers', 0):,}")

    s.close()

    print("\n" + "=" * 70)
    print("SIMULATION COMPLETE")
    print("=" * 70)
    print("\nIf all tests show SUCCESS, the backend is working correctly.")
    print("The issue must be in how the frontend calls the API.")
    print("\nPlease check the browser Network tab to see actual payload sent.")

except Exception as e:
    print(f"\nERROR: {e}")
    import traceback
    traceback.print_exc()
