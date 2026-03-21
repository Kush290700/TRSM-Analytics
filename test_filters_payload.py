"""
Test what happens when we send different filter payloads.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 70)
print("TESTING FILTER PAYLOADS")
print("=" * 70)

from app.services.filters import parse_filters, apply_filters
import data_loader as loader

# Load data
df = loader.get_fact_df()
print(f"\nOriginal data: {len(df):,} rows")

# Test Case 1: Empty payload (should use defaults)
print("\n[1] Empty payload {}...")
filters1 = parse_filters({})
dff1 = apply_filters(df, filters1)
print(f"    Result: {len(dff1):,} rows")
if len(dff1) > 0 and 'revenue_shipped' in dff1.columns:
    print(f"    Revenue: ${dff1['revenue_shipped'].sum():,.2f}")

# Test Case 2: Payload with ['All'] arrays (what frontend sends)
print("\n[2] Payload with ['All'] arrays...")
payload2 = {
    'start': None,
    'end': None,
    'regions': ['All'],
    'methods': ['All'],
    'customers': ['All'],
    'suppliers': ['All']
}
filters2 = parse_filters(payload2)
print(f"    Parsed regions: {filters2.regions}")
print(f"    Parsed methods: {filters2.methods}")
print(f"    Parsed customers: {filters2.customers}")
dff2 = apply_filters(df, filters2)
print(f"    Result: {len(dff2):,} rows")
if len(dff2) > 0 and 'revenue_shipped' in dff2.columns:
    print(f"    Revenue: ${dff2['revenue_shipped'].sum():,.2f}")

# Test Case 3: Payload with objects (possible frontend issue)
print("\n[3] Payload with {name, count} objects...")
payload3 = {
    'start': None,
    'end': None,
    'regions': [{'name': 'West', 'count': 100}],
    'methods': ['All'],
    'customers': ['All'],
    'suppliers': ['All']
}
try:
    filters3 = parse_filters(payload3)
    print(f"    Parsed regions: {filters3.regions}")
    dff3 = apply_filters(df, filters3)
    print(f"    Result: {len(dff3):,} rows")
except Exception as e:
    print(f"    ERROR: {e}")

# Test Case 4: Specific date range that might exclude data
print("\n[4] Recent date range (last 30 days)...")
import pandas as pd
today = pd.Timestamp.now().normalize()
thirty_days_ago = today - pd.Timedelta(days=30)
payload4 = {
    'start': thirty_days_ago.isoformat(),
    'end': today.isoformat(),
    'regions': ['All'],
    'methods': ['All'],
    'customers': ['All']
}
filters4 = parse_filters(payload4)
print(f"    Start: {filters4.start}")
print(f"    End: {filters4.end}")
dff4 = apply_filters(df, filters4)
print(f"    Result: {len(dff4):,} rows")
if len(dff4) > 0 and 'revenue_shipped' in dff4.columns:
    print(f"    Revenue: ${dff4['revenue_shipped'].sum():,.2f}")
elif len(dff4) == 0:
    print("    ** NO DATA in this date range! **")

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)
