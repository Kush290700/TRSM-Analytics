#!/usr/bin/env python3
"""Simple test for enhanced analytics endpoints"""
import os
import pytest
import requests
from bs4 import BeautifulSoup

if os.getenv("RUN_LIVE_ENDPOINT_TESTS", "").strip().lower() not in {"1", "true", "yes"}:
    pytest.skip("Live endpoint smoke requires running server at http://127.0.0.1:5000", allow_module_level=True)

BASE_URL = "http://127.0.0.1:5000"

def test_endpoints():
    """Test all endpoints"""
    session = requests.Session()

    # Step 1: Get login page and extract CSRF token
    print("=" * 70)
    print("TESTING ENHANCED ANALYTICS ENDPOINTS")
    print("=" * 70)

    print("\n[1] Getting login page...")
    resp = session.get(f"{BASE_URL}/auth/login")
    if resp.status_code != 200:
        print(f"[FAIL] Could not get login page: {resp.status_code}")
        return

    # Parse CSRF token
    soup = BeautifulSoup(resp.text, 'html.parser')
    csrf_input = soup.find('input', {'name': 'csrf_token'})
    if not csrf_input:
        print("[FAIL] Could not find CSRF token")
        return

    csrf_token = csrf_input.get('value')
    print(f"[OK] Got CSRF token: {csrf_token[:20]}...")

    # Step 2: Login
    print("\n[2] Logging in...")
    login_data = {
        'username': 'admin',
        'password': 'admin',
        'csrf_token': csrf_token
    }

    resp = session.post(f"{BASE_URL}/auth/login", data=login_data, allow_redirects=True)
    if 'admin' not in resp.text.lower() or resp.url.endswith('/auth/login'):
        print(f"[FAIL] Login failed")
        return

    print(f"[OK] Login successful")

    # Step 3: Test each endpoint
    print("\n[3] Testing Enhanced Analytics Endpoints...")
    print("-" * 70)

    endpoints = [
        ("/api/overview/analytics/growth?period=month", "Growth Analytics"),
        ("/api/overview/analytics/weight", "Weight Metrics"),
        ("/api/overview/analytics/predictions?periods=4", "Predictions"),
        ("/api/overview/analytics/customer-insights", "Customer Insights"),
        ("/api/overview/analytics/product-insights", "Product Insights"),
        ("/api/overview/analytics/supplier-insights", "Supplier Insights"),
    ]

    results = []

    for endpoint, name in endpoints:
        url = f"{BASE_URL}{endpoint}"
        print(f"\n{name}:")
        print(f"  URL: {endpoint}")

        try:
            resp = session.get(url, timeout=10)
            print(f"  Status: {resp.status_code}")

            if resp.status_code == 200:
                try:
                    data = resp.json()
                    print(f"  Response keys: {list(data.keys())}")

                    # Check for errors in response
                    if 'error' in data:
                        print(f"  [WARN] API returned error: {data['error']}")
                        results.append((name, "WARN", data['error']))
                    else:
                        # Show sample data
                        if isinstance(data, dict):
                            for key, value in list(data.items())[:2]:
                                if isinstance(value, dict):
                                    print(f"  {key}: {list(value.keys())}")
                                else:
                                    print(f"  {key}: {str(value)[:50]}...")
                        print(f"  [PASS]")
                        results.append((name, "PASS", "OK"))
                except ValueError as e:
                    print(f"  [FAIL] Invalid JSON: {e}")
                    results.append((name, "FAIL", "Invalid JSON"))
            else:
                print(f"  [FAIL] HTTP {resp.status_code}")
                results.append((name, "FAIL", f"HTTP {resp.status_code}"))

        except requests.exceptions.Timeout:
            print(f"  [FAIL] Timeout")
            results.append((name, "FAIL", "Timeout"))
        except Exception as e:
            print(f"  [FAIL] {e}")
            results.append((name, "FAIL", str(e)))

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, status, _ in results if status == "PASS")
    warned = sum(1 for _, status, _ in results if status == "WARN")
    failed = sum(1 for _, status, _ in results if status == "FAIL")

    for name, status, message in results:
        print(f"[{status}] {name}: {message}")

    print(f"\nResults: {passed} PASSED, {warned} WARNINGS, {failed} FAILED")

    if passed == len(results):
        print("\n[SUCCESS] All endpoints are working perfectly!")
        print("\nNext steps:")
        print("1. Open browser to: http://127.0.0.1:5000")
        print("2. Login with admin/admin")
        print("3. Check the Overview page")
        print("4. Open DevTools (F12) and check Console tab")
        print("5. Look for '[Enhanced Analytics] X loaded' messages")
        return True
    elif passed + warned == len(results):
        print("\n[PARTIAL SUCCESS] All endpoints responding, some with warnings")
        print("This may be normal if data is filtered or empty.")
        return True
    else:
        print(f"\n[FAILURE] {failed} endpoint(s) not working")
        return False

if __name__ == "__main__":
    import sys
    success = test_endpoints()
    sys.exit(0 if success else 1)
