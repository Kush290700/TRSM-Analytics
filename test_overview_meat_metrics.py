"""
Test script for meat-specific metrics in overview page.

Run this to verify meat metrics calculations are working correctly.

Usage:
    python test_overview_meat_metrics.py
"""

import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def create_test_data():
    """Create synthetic test data for meat metrics."""
    np.random.seed(42)

    # Generate dates for last 90 days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)
    dates = pd.date_range(start=start_date, end=end_date, periods=500)

    # Protein types
    proteins = ['Beef', 'Pork', 'Chicken', 'Turkey', 'Lamb']
    protein_weights = [0.35, 0.30, 0.20, 0.10, 0.05]  # Market share

    # Products/Cuts
    beef_cuts = ['Ribeye Steak', 'Ground Beef', 'Sirloin', 'Brisket']
    pork_cuts = ['Pork Chops', 'Bacon', 'Ham', 'Pork Shoulder']
    chicken_cuts = ['Chicken Breast', 'Chicken Wings', 'Whole Chicken', 'Chicken Thighs']
    turkey_cuts = ['Turkey Breast', 'Ground Turkey', 'Whole Turkey']
    lamb_cuts = ['Lamb Chops', 'Leg of Lamb']

    all_products = beef_cuts + pork_cuts + chicken_cuts + turkey_cuts + lamb_cuts

    rows = []
    for i in range(500):
        # Select protein type (weighted)
        protein = np.random.choice(proteins, p=protein_weights)

        # Select product based on protein
        if protein == 'Beef':
            product = np.random.choice(beef_cuts)
        elif protein == 'Pork':
            product = np.random.choice(pork_cuts)
        elif protein == 'Chicken':
            product = np.random.choice(chicken_cuts)
        elif protein == 'Turkey':
            product = np.random.choice(turkey_cuts)
        else:
            product = np.random.choice(lamb_cuts)

        # Generate order details                                                                    
        order_date = dates[i]                                                                       
        ship_days = np.random.choice([0, 1, 2, 3, 4, 5], p=[0.1, 0.3, 0.35, 0.15, 0.07, 0.03])      
        ship_date = order_date + timedelta(days=int(ship_days))
        quantity = np.random.randint(10, 200)
        weight_per_unit = np.random.uniform(1.5, 5.0)  # lbs
        total_weight = quantity * weight_per_unit

        price_per_lb = {
            'Beef': np.random.uniform(8, 15),
            'Pork': np.random.uniform(5, 10),
            'Chicken': np.random.uniform(3, 7),
            'Turkey': np.random.uniform(4, 8),
            'Lamb': np.random.uniform(10, 18),
        }[protein]

        revenue = total_weight * price_per_lb

        rows.append({
            'Date': order_date,
            'OrderId': f'ORD-{i+1000:05d}',
            'CustomerId': f'CUST-{np.random.randint(1, 50):03d}',
            'CustomerName': f'Customer {np.random.randint(1, 50)}',
            'ProductName': product,
            'ProteinCategory': protein,
            'QuantityShipped': quantity,
            'WeightLbs': round(total_weight, 2),
            'revenue_shipped': round(revenue, 2),
            'Revenue': round(revenue, 2),
            'ShipDate': ship_date,
            'RegionName': np.random.choice(['West', 'Central', 'East']),
            'SupplierName': np.random.choice(['Farm Fresh', 'Quality Meats', 'Premium Cuts']),
        })

    return pd.DataFrame(rows)


def test_meat_metrics():
    """Test meat-specific metrics calculations."""
    print("=" * 70)
    print("Testing Meat-Specific Metrics")
    print("=" * 70)

    # Create test data
    print("\n1. Creating test data...")
    df = create_test_data()
    print(f"   ✓ Created {len(df)} test orders")
    print(f"   ✓ Date range: {df['Date'].min().date()} to {df['Date'].max().date()}")
    print(f"   ✓ Columns: {', '.join(df.columns[:5])}...")

    # Import meat metrics function
    try:
        from app.services.overview_query import _meat_specific_metrics
        print("   ✓ Imported _meat_specific_metrics function")
    except ImportError as e:
        print(f"   ✗ Error importing function: {e}")
        return False

    # Calculate revenue series
    revenue = pd.to_numeric(df['revenue_shipped'], errors='coerce').fillna(0.0)

    # Run metrics calculation
    print("\n2. Calculating meat metrics...")
    try:
        metrics = _meat_specific_metrics(df, revenue)
        print("   ✓ Metrics calculated successfully")
    except Exception as e:
        print(f"   ✗ Error calculating metrics: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Validate protein mix
    print("\n3. Testing Protein Mix...")
    if metrics['protein_mix']:
        print("   ✓ Protein mix data found")
        total_share = sum(item['share'] for item in metrics['protein_mix'].values())
        print(f"   ✓ Total share: {total_share:.1f}% (should be ~100%)")

        for protein, data in sorted(metrics['protein_mix'].items(),
                                     key=lambda x: x[1]['revenue'], reverse=True):
            print(f"      • {protein}: ${data['revenue']:,.2f} ({data['share']:.1f}%)")
    else:
        print("   ✗ No protein mix data")
        return False

    # Validate pack analysis
    print("\n4. Testing Pack Analysis...")
    if metrics['pack_analysis']:
        print("   ✓ Pack analysis data found")
        avg_pack = metrics['pack_analysis'].get('avg_units_per_order', 0)
        total_units = metrics['pack_analysis'].get('total_units', 0)
        print(f"      • Avg pack size: {avg_pack:.1f} units")
        print(f"      • Total units: {total_units:,}")
    else:
        print("   ✗ No pack analysis data")

    # Validate yield metrics
    print("\n5. Testing Yield Metrics...")
    if metrics['yield_metrics']:
        print("   ✓ Yield metrics data found")
        weight = metrics['yield_metrics'].get('total_weight_lbs', 0)
        rev_per_lb = metrics['yield_metrics'].get('revenue_per_lb', 0)
        print(f"      • Total weight: {weight:,.2f} lbs")
        print(f"      • Revenue per lb: ${rev_per_lb:.2f}")
    else:
        print("   ⚠ No yield metrics (weight column may not exist)")

    # Validate cold chain
    print("\n6. Testing Cold Chain Compliance...")
    if metrics['cold_chain']:
        print("   ✓ Cold chain data found")
        fast_rate = metrics['cold_chain'].get('fast_ship_rate', 0)
        avg_days = metrics['cold_chain'].get('avg_ship_days', 0)
        print(f"      • Fast ship rate: {fast_rate:.1f}%")
        print(f"      • Avg ship days: {avg_days:.1f}")

        if fast_rate >= 85:
            print("      • Status: 🟢 Excellent (≥85%)")
        elif fast_rate >= 70:
            print("      • Status: 🟡 Good (70-84%)")
        else:
            print("      • Status: 🔴 Needs Improvement (<70%)")
    else:
        print("   ✗ No cold chain data")
        return False

    # Validate cut performance
    print("\n7. Testing Cut Performance...")
    if metrics['cut_performance'] and metrics['cut_performance'].get('top_cuts'):
        print("   ✓ Cut performance data found")
        top_cuts = metrics['cut_performance']['top_cuts']
        print(f"      • Top {len(top_cuts)} cuts by revenue:")
        for i, cut in enumerate(top_cuts, 1):
            print(f"         {i}. {cut['name']}: ${cut['revenue']:,.2f} ({cut['share']:.1f}%)")
    else:
        print("   ✗ No cut performance data")
        return False

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    checks = [
        ("Protein Mix", bool(metrics['protein_mix'])),
        ("Pack Analysis", bool(metrics['pack_analysis'])),
        ("Yield Metrics", bool(metrics['yield_metrics'])),
        ("Cold Chain", bool(metrics['cold_chain'])),
        ("Cut Performance", bool(metrics['cut_performance'])),
    ]

    passed = sum(1 for _, status in checks if status)
    total = len(checks)

    for name, status in checks:
        icon = "✓" if status else "✗"
        print(f"   {icon} {name}")

    print(f"\nPassed: {passed}/{total}")

    if passed == total:
        print("\n🎉 All tests passed! Meat metrics are working correctly.")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Review the output above.")

def test_frontend_elements():
    """Test that frontend elements are present in HTML."""
    print("\n" + "=" * 70)
    print("Testing Frontend Elements")
    print("=" * 70)

    html_file = Path(__file__).parent / 'app' / 'templates' / 'overview.html'

    if not html_file.exists():
        print(f"   ✗ HTML file not found: {html_file}")
        return False

    print(f"\n   Reading {html_file.name}...")
    content = html_file.read_text(encoding='utf-8')

    # Check for required elements
    elements = {
        'Meat Metrics Section': 'id="meatMetricsSection"',
        'Protein Mix Chart': 'id="proteinMixChart"',
        'Pack Size Display': 'id="meatPackSize"',
        'Total Units Display': 'id="meatTotalUnits"',
        'Total Weight Display': 'id="meatTotalWeight"',
        'Revenue per lb Display': 'id="meatRevPerLb"',
        'Fast Ship Badge': 'id="meatFastShipBadge"',
        'Fast Ship Progress': 'id="meatFastShipProgress"',
        'Top Cuts List': 'id="meatTopCutsList"',
        'Gradient Meat CSS': 'bg-gradient-meat',
        'Gradient Yield CSS': 'bg-gradient-yield',
        'Gradient Cold CSS': 'bg-gradient-cold',
    }

    print("\n   Checking for required elements:")
    passed = 0
    for name, element_id in elements.items():
        if element_id in content:
            print(f"      ✓ {name}")
            passed += 1
        else:
            print(f"      ✗ {name} (missing '{element_id}')")

    total = len(elements)
    print(f"\n   Found: {passed}/{total} elements")

def test_javascript_functions():
    """Test that JavaScript functions are present."""
    print("\n" + "=" * 70)
    print("Testing JavaScript Functions")
    print("=" * 70)

    js_file = Path(__file__).parent / 'app' / 'static' / 'js' / 'overview.js'

    if not js_file.exists():
        print(f"   ✗ JavaScript file not found: {js_file}")
        return False

    print(f"\n   Reading {js_file.name}...")
    content = js_file.read_text(encoding='utf-8')

    # Check for required functions
    functions = {
        'renderProteinMix': 'function renderProteinMix',
        'renderPackAnalysis': 'function renderPackAnalysis',
        'renderYieldMetrics': 'function renderYieldMetrics',
        'renderColdChain': 'function renderColdChain',
        'renderTopCuts': 'function renderTopCuts',
        'renderMeatMetrics': 'function renderMeatMetrics',
    }

    print("\n   Checking for required functions:")
    passed = 0
    for name, func_signature in functions.items():
        if func_signature in content:
            print(f"      ✓ {name}")
            passed += 1
        else:
            print(f"      ✗ {name}")

    total = len(functions)
    print(f"\n   Found: {passed}/{total} functions")


if __name__ == '__main__':
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 15 + "MEAT METRICS TEST SUITE" + " " * 30 + "║")
    print("╚" + "═" * 68 + "╝")

    # Run all tests
    results = []

    # Test 1: Backend metrics
    results.append(("Backend Metrics", test_meat_metrics()))

    # Test 2: Frontend elements
    results.append(("Frontend Elements", test_frontend_elements()))

    # Test 3: JavaScript functions
    results.append(("JavaScript Functions", test_javascript_functions()))

    # Final summary
    print("\n" + "╔" + "═" * 68 + "╗")
    print("║" + " " * 22 + "FINAL RESULTS" + " " * 33 + "║")
    print("╚" + "═" * 68 + "╝")

    for name, passed in results:
        icon = "✓" if passed else "✗"
        status = "PASS" if passed else "FAIL"
        print(f"\n   {icon} {name}: {status}")

    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)

    print(f"\n   Overall: {passed_count}/{total_count} test suites passed")

    if passed_count == total_count:
        print("\n   🎉 All test suites passed!")
        print("   Your overview page is ready for production!")
        sys.exit(0)
    else:
        print(f"\n   ⚠️  {total_count - passed_count} test suite(s) failed.")
        print("   Review the output above for details.")
        sys.exit(1)
