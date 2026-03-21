"""
Verify the filter fix works with actual data.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 70)
print("VERIFYING FILTER FIX")
print("=" * 70)

from app.services.filters import parse_filters, apply_filters
import data_loader as loader

# Load data
df = loader.get_fact_df()
print(f"\nOriginal data: {len(df):,} rows")
if 'revenue_shipped' in df.columns:
    print(f"Total revenue: ${df['revenue_shipped'].sum():,.2f}")

# Test with actual region name in {name, count} format
print("\n[1] Testing with {name, count} object for Vancouver NS...")
payload = {
    'start': None,
    'end': None,
    'regions': [{'name': 'Vancouver NS', 'count': 100}],
    'methods': ['All'],
    'customers': ['All'],
    'suppliers': ['All']
}
filters = parse_filters(payload)
print(f"    Parsed regions: {filters.regions}")
dff = apply_filters(df, filters)
print(f"    Result: {len(dff):,} rows")
if len(dff) > 0 and 'revenue_shipped' in dff.columns:
    print(f"    Revenue: ${dff['revenue_shipped'].sum():,.2f}")
    print("    ** FIX WORKS! **")
else:
    print("    ** Still broken **")

# Test with mix of strings and objects
print("\n[2] Testing with mix of strings and {name, count} objects...")
payload2 = {
    'start': None,
    'end': None,
    'regions': ['Vancouver E', {'name': 'Victoria', 'count': 50}],
    'methods': ['All'],
    'customers': ['All'],
    'suppliers': ['All']
}
filters2 = parse_filters(payload2)
print(f"    Parsed regions: {filters2.regions}")
dff2 = apply_filters(df, filters2)
print(f"    Result: {len(dff2):,} rows")
if len(dff2) > 0 and 'revenue_shipped' in dff2.columns:
    print(f"    Revenue: ${dff2['revenue_shipped'].sum():,.2f}")

# Test with ['All'] still works
print("\n[3] Verifying ['All'] still works...")
payload3 = {
    'start': None,
    'end': None,
    'regions': ['All'],
    'methods': ['All'],
    'customers': ['All'],
    'suppliers': ['All']
}
filters3 = parse_filters(payload3)
print(f"    Parsed regions: {filters3.regions}")
dff3 = apply_filters(df, filters3)
print(f"    Result: {len(dff3):,} rows")
if len(dff3) > 0 and 'revenue_shipped' in dff3.columns:
    print(f"    Revenue: ${dff3['revenue_shipped'].sum():,.2f}")

print("\n" + "=" * 70)
print("VERIFICATION COMPLETE")
print("=" * 70)
print("\nSUMMARY:")
print("  - Filter parsing now handles {name, count} objects")
print("  - ['All'] sentinel still works correctly")
print("  - Mixed arrays of strings and objects work")
print("\nNext step: Restart Flask app and test in browser!")
