"""Quick overview API diagnostic - no Unicode."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

print("\n" + "=" * 70)
print("OVERVIEW DATA TEST")
print("=" * 70)

try:
    # Test 1: Load data
    print("\n[1] Loading data...")
    import data_loader
    df = data_loader.get_fact_df()
    print(f"    OK - Loaded {len(df)} rows")

    # Test 2: Check revenue
    print("\n[2] Checking revenue column...")
    if 'revenue_shipped' in df.columns:
        total_rev = df['revenue_shipped'].sum()
        print(f"    OK - Total revenue: ${total_rev:,.2f}")
    else:
        print("    ERROR - No 'revenue_shipped' column")
        print(f"    Available: {list(df.columns)[:10]}")

    # Test 3: Compute overview
    print("\n[3] Computing overview...")
    from app.services.overview_query import compute_overview
    result = compute_overview(df)
    print(f"    OK - Result keys: {list(result.keys())}")

    # Test 4: Check KPIs
    print("\n[4] Checking KPIs...")
    kpis = result.get('kpis', {})
    print(f"    Revenue: ${kpis.get('total_revenue', 0):,.2f}")
    print(f"    Orders: {kpis.get('total_orders', 0):,}")
    print(f"    Customers: {kpis.get('total_customers', 0):,}")
    print(f"    AOV: ${kpis.get('aov', 0):,.2f}")

    # Test 5: Check meat metrics
    print("\n[5] Checking meat metrics...")
    meat = result.get('meat_metrics', {})
    print(f"    Keys: {list(meat.keys())}")

    if meat.get('protein_mix'):
        print(f"    Protein mix: {list(meat['protein_mix'].keys())}")
    else:
        print("    Protein mix: Empty")

    if meat.get('pack_analysis'):
        pack = meat['pack_analysis']
        print(f"    Pack: {pack.get('avg_units_per_order', 0):.1f} units, {pack.get('total_units', 0):,} total")

    if meat.get('cold_chain'):
        cc = meat['cold_chain']
        print(f"    Cold chain: {cc.get('fast_ship_rate', 0):.1f}% fast ship")

    if meat.get('cut_performance'):
        cuts = meat['cut_performance'].get('top_cuts', [])
        print(f"    Top cuts: {len(cuts)} found")
        if cuts:
            print(f"       #1: {cuts[0]['name']} - ${cuts[0]['revenue']:,.2f}")

    print("\n" + "=" * 70)
    print("SUCCESS - Backend data is working!")
    print("=" * 70)
    print("\nNow check if Flask app is returning this data...")
    print("1. Start Flask: python run.py")
    print("2. Login at: http://localhost:5000/login")
    print("3. Go to: http://localhost:5000")
    print("4. Open browser DevTools (F12) and check Console for errors")

except Exception as e:
    print(f"\nERROR: {e}")
    import traceback
    traceback.print_exc()
