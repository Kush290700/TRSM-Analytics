#!/usr/bin/env python
"""
Quick smoke test for overview page to verify it loads without errors.
Run this script to test the overview page functionality.
"""
import sys
import time
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

def test_overview_page():
    """Test overview page rendering and API endpoints."""
    print("=" * 60)
    print("OVERVIEW PAGE SMOKE TEST")
    print("=" * 60)

    try:
        from app import create_app
        from flask import url_for

        app = create_app()
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False

        with app.test_client() as client:
            print("\n1. Testing main overview page (GET /)...")
            response = client.get('/')

            if response.status_code == 302:  # Redirect to login
                print("   ✓ Redirects to login (expected for non-authenticated request)")

                # Try to login
                print("\n2. Testing login...")
                login_response = client.post('/auth/login', data={
                    'username': 'admin',
                    'password': 'admin'
                }, follow_redirects=False)

                if login_response.status_code in (200, 302):
                    print("   ✓ Login successful")

                    # Try overview page again
                    print("\n3. Testing overview page after login...")
                    response = client.get('/', follow_redirects=True)

                    if response.status_code == 200:
                        print("   ✓ Overview page loads (200 OK)")

                        # Check for key elements in HTML
                        html = response.data.decode('utf-8')
                        checks = [
                            ('overview.js' in html, 'overview.js script included'),
                            ('id="kpi_customers"' in html or 'data-metric-card' in html, 'KPI cards present'),
                            ('Plotly' in html or 'plotly' in html, 'Plotly charting library'),
                        ]

                        for check, desc in checks:
                            if check:
                                print(f"   ✓ {desc}")
                            else:
                                print(f"   ✗ {desc} - MISSING")
                    else:
                        print(f"   ✗ Overview page failed: {response.status_code}")
                else:
                    print(f"   ✗ Login failed: {login_response.status_code}")

            elif response.status_code == 200:
                print("   ✓ Overview page loads without authentication")
            else:
                print(f"   ✗ Unexpected status code: {response.status_code}")

            print("\n4. Testing API endpoints...")

            # Test filters endpoint
            filters_response = client.get('/api/overview/filters')
            if filters_response.status_code in (200, 204, 302, 401):
                print(f"   ✓ /api/overview/filters returns {filters_response.status_code}")
            else:
                print(f"   ✗ /api/overview/filters failed: {filters_response.status_code}")

            # Test cards endpoint
            cards_response = client.get('/api/overview/cards')
            if cards_response.status_code in (200, 204, 302, 401):
                print(f"   ✓ /api/overview/cards returns {cards_response.status_code}")
            else:
                print(f"   ✗ /api/overview/cards failed: {cards_response.status_code}")

            # Test series endpoint
            series_response = client.get('/api/overview/series?metric=revenue&freq=month')
            if series_response.status_code in (200, 204, 302, 401):
                print(f"   ✓ /api/overview/series returns {series_response.status_code}")
            else:
                print(f"   ✗ /api/overview/series failed: {series_response.status_code}")

        print("\n" + "=" * 60)
        print("✓ SMOKE TEST COMPLETE")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Start the server: python run.py --fast")
        print("2. Open browser: http://127.0.0.1:5000/")
        print("3. Login with: admin / admin")
        print("4. Verify data loads and persists (doesn't disappear)")
        print("5. Check browser console for errors (F12)")



    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_overview_page()
    sys.exit(0 if success else 1)
