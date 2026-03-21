"""
Test the overview API endpoint directly with authentication.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 70)
print("TESTING OVERVIEW API ENDPOINT")
print("=" * 70)

# Test the Flask app context
print("\n[1] Testing with Flask app context...")
try:
    from app import create_app
    from app.auth.models import User, get_session
    from flask import g
    from flask_login import login_user

    app = create_app()

    with app.app_context():
        with app.test_request_context():
            # Get admin user
            s = get_session()
            admin = s.query(User).filter_by(username='admin').first()

            if admin:
                print(f"    Found admin user: {admin.username}")

                # Simulate login
                login_user(admin)
                print(f"    Admin logged in: {admin.is_authenticated}")

                # Now test the overview data endpoint
                from app.blueprints.overview import _load_for, _payload_and_params, CARDS_COLUMNS, SERIES_COLUMNS
                from app.services.filters import parse_filters, apply_filters
                from app.services.overview_query import compute_overview

                print("\n[2] Loading data...")
                df = _load_for(CARDS_COLUMNS + SERIES_COLUMNS + ("ProductName", "SkuName"))
                print(f"    Loaded {len(df):,} rows")

                print("\n[3] Applying filters...")
                # Empty filters (no restrictions)
                params = parse_filters({})
                print(f"    Filter start: {params.start}")
                print(f"    Filter end: {params.end}")
                print(f"    Filter regions: {params.regions}")
                print(f"    Filter customers: {params.customers}")

                dff = apply_filters(df, params)
                print(f"    After filters: {len(dff):,} rows")

                if len(dff) == 0:
                    print("    ERROR: All data filtered out!")
                    print("    This is why you see zeros!")

                    # Check date range
                    if 'Date' in df.columns:
                        import pandas as pd
                        dates = pd.to_datetime(df['Date'], errors='coerce').dropna()
                        if not dates.empty:
                            print(f"    Data date range: {dates.min()} to {dates.max()}")
                            print(f"    Filter date range: {params.start} to {params.end}")
                else:
                    print("\n[4] Computing overview...")
                    result = compute_overview(dff)
                    kpis = result.get('kpis', {})
                    print(f"    Total Revenue: ${kpis.get('total_revenue', 0):,.2f}")
                    print(f"    Total Orders: {kpis.get('total_orders', 0):,}")
                    print(f"    Total Customers: {kpis.get('total_customers', 0):,}")

                    if kpis.get('total_revenue', 0) == 0:
                        print("    ERROR: KPIs show zero despite having filtered data!")
                    else:
                        print("    SUCCESS: Backend returns correct data!")

            s.close()

except Exception as e:
    print(f"    ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)
