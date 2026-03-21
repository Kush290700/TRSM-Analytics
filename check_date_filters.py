"""
Check default date filters - likely cause of zeros.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 70)
print("DATE FILTER DIAGNOSTIC")
print("=" * 70)

# 1. Load data and check date range
print("\n[1] Checking data date range...")
try:
    import data_loader as loader
    import pandas as pd

    df = loader.get_fact_df()
    if 'Date' in df.columns:
        dates = pd.to_datetime(df['Date'], errors='coerce').dropna()
        if not dates.empty:
            data_min = dates.min()
            data_max = dates.max()
            print(f"    Data MIN date: {data_min.date()}")
            print(f"    Data MAX date: {data_max.date()}")
            print(f"    Data span: {(data_max - data_min).days} days")
        else:
            print("    ERROR: No valid dates in data!")
    else:
        print("    ERROR: No 'Date' column in data!")
except Exception as e:
    print(f"    ERROR: {e}")
    import traceback
    traceback.print_exc()

# 2. Check default filter window
print("\n[2] Checking default filter window...")
try:
    from app.services.filters import parse_filters
    import os

    # Check environment variable
    default_months = os.getenv('FILTER_DEFAULT_MONTHS') or os.getenv('DEFAULT_MONTH_WINDOW') or '12'
    print(f"    FILTER_DEFAULT_MONTHS: {default_months}")

    # Parse empty filters (should use defaults)
    filters = parse_filters({})
    if filters.start and filters.end:
        print(f"    Default START: {filters.start.date()}")
        print(f"    Default END: {filters.end.date()}")
        print(f"    Default span: {(filters.end - filters.start).days} days")
    else:
        print("    ERROR: Default filters have no start/end!")

except Exception as e:
    print(f"    ERROR: {e}")
    import traceback
    traceback.print_exc()

# 3. Check if default filter excludes all data
print("\n[3] Testing filter application...")
try:
    import data_loader as loader
    from app.services.filters import parse_filters, apply_filters
    import pandas as pd

    df = loader.get_fact_df()
    rows_before = len(df)
    print(f"    Rows before filters: {rows_before:,}")

    # Apply default filters
    filters = parse_filters({})
    dff = apply_filters(df, filters)
    rows_after = len(dff)
    print(f"    Rows after default filters: {rows_after:,}")

    if rows_after == 0 and rows_before > 0:
        print("    ** FOUND THE PROBLEM! **")
        print("    Default date filter is excluding ALL data!")

        # Show why
        if 'Date' in df.columns:
            dates = pd.to_datetime(df['Date'], errors='coerce').dropna()
            data_min = dates.min()
            data_max = dates.max()
            filter_start = filters.start
            filter_end = filters.end

            print(f"\n    Data range: {data_min.date()} to {data_max.date()}")
            print(f"    Filter range: {filter_start.date()} to {filter_end.date()}")

            if data_max < filter_start:
                print(f"    ** Data ends BEFORE filter starts! **")
                print(f"    Gap: {(filter_start - data_max).days} days")
            elif data_min > filter_end:
                print(f"    ** Data starts AFTER filter ends! **")
                print(f"    Gap: {(data_min - filter_end).days} days")

    elif rows_after > 0:
        print("    Filter is working - data passes through.")

        # Check revenue
        if 'revenue_shipped' in dff.columns:
            total_rev = dff['revenue_shipped'].sum()
            print(f"    Total revenue after filters: ${total_rev:,.2f}")

except Exception as e:
    print(f"    ERROR: {e}")
    import traceback
    traceback.print_exc()

# 4. Suggest fix
print("\n[4] SOLUTION:")
print("    If default filter excludes all data, you need to either:")
print("    a) Update the default date window in .env:")
print("       FILTER_DEFAULT_MONTHS=24  (or larger)")
print("    b) Or change the code to use data's actual date range")
print("    c) Or pass explicit start/end dates from frontend")

print("\n" + "=" * 70)
print("DIAGNOSTIC COMPLETE")
print("=" * 70)
