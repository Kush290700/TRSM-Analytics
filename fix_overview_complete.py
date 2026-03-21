#!/usr/bin/env python3
"""
Complete fix script for overview page enhanced analytics
This script will:
1. Check if server is accessible
2. Test all API endpoints
3. Generate a comprehensive report
4. Provide fix recommendations

Run with: python fix_overview_complete.py
"""

import sys
import time
import requests
from pathlib import Path

BASE_URL = "http://127.0.0.1:5000"
USERNAME = "admin"
PASSWORD = "admin"

def print_section(title):
    """Print a section header"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print('='*70)

def check_server_running():
    """Check if server is accessible"""
    print_section("1. Checking Server")
    try:
        resp = requests.get(f"{BASE_URL}/auth/login", timeout=5)
        if resp.status_code == 200:
            print("[OK] Server is running and accessible")
            return True
        else:
            print(f"[WARN] Server responded with status {resp.status_code}")
            return True  # Still accessible
    except requests.exceptions.ConnectionError:
        print("[FAIL] Server is NOT running!")
        print("\nTo start server, run:")
        print("  python run.py --fast")
        return False
    except Exception as e:
        print(f"[ERROR] {e}")
        return False

def test_login():
    """Test login functionality"""
    print_section("2. Testing Login")
    session = requests.Session()

    try:
        # Get login page
        resp = session.get(f"{BASE_URL}/auth/login")

        # Try to login
        login_data = {
            'username': USERNAME,
            'password': PASSWORD
        }
        resp = session.post(f"{BASE_URL}/auth/login", data=login_data, allow_redirects=False)

        if resp.status_code in [200, 302]:
            print(f"[OK] Login successful (status {resp.status_code})")
            return session
        else:
            print(f"[FAIL] Login failed with status {resp.status_code}")
            return None
    except Exception as e:
        print(f"[ERROR] {e}")
        return None

def test_enhanced_endpoints(session):
    """Test all enhanced analytics endpoints"""
    print_section("3. Testing Enhanced Analytics Endpoints")

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
        print(f"\nTesting: {name}")
        print(f"URL: {url}")

        try:
            resp = session.get(url, timeout=10)
            print(f"  Status: {resp.status_code}")

            if resp.status_code == 200:
                try:
                    data = resp.json()
                    print(f"  [OK] Response keys: {list(data.keys())}")

                    # Check for errors in response
                    if 'error' in data:
                        print(f"  [WARN] API returned error: {data['error']}")
                        results.append((name, False, data['error']))
                    else:
                        results.append((name, True, "OK"))
                except ValueError as e:
                    print(f"  [FAIL] Invalid JSON: {e}")
                    results.append((name, False, "Invalid JSON"))
            else:
                print(f"  [FAIL] Status {resp.status_code}")
                results.append((name, False, f"HTTP {resp.status_code}"))

        except requests.exceptions.Timeout:
            print(f"  [FAIL] Timeout")
            results.append((name, False, "Timeout"))
        except Exception as e:
            print(f"  [FAIL] {e}")
            results.append((name, False, str(e)))

    return results

def check_files_exist():
    """Check if required files exist"""
    print_section("4. Checking Required Files")

    files_to_check = [
        ("app/services/enhanced_analytics.py", "Enhanced Analytics Service"),
        ("app/static/js/overview-enhanced.js", "Enhanced Analytics JavaScript"),
        ("app/templates/overview.html", "Overview Template"),
        ("cache/fact_analytics.parquet", "Data Cache (Parquet)"),
    ]

    all_exist = True
    for filepath, description in files_to_check:
        full_path = Path(filepath)
        if full_path.exists():
            print(f"[OK] {description}: {filepath}")
        else:
            print(f"[FAIL] Missing: {filepath}")
            all_exist = False

    return all_exist

def print_summary(results):
    """Print test summary"""
    print_section("SUMMARY")

    passed = sum(1 for _, success, _ in results if success)
    total = len(results)

    for name, success, message in results:
        status = "[PASS]" if success else "[FAIL]"
        print(f"{status} {name}: {message}")

    print(f"\nTotal: {passed}/{total} endpoints working")

    if passed == total:
        print("\n[SUCCESS] All endpoints are working!")
        print("\nNext steps:")
        print("1. Open browser to: http://127.0.0.1:5000")
        print("2. Login and check overview page")
        print("3. Verify all sections load properly")
        return True
    else:
        print(f"\n[FAILURE] {total - passed} endpoint(s) not working")
        print("\nTroubleshooting:")
        print("1. Check logs: logs/app.log")
        print("2. Verify database connection")
        print("3. Ensure parquet cache exists")
        print("4. Check Python error output above")
        return False

def main():
    """Main execution"""
    print_section("OVERVIEW PAGE DIAGNOSTIC")
    print("This script will test all enhanced analytics components")

    # Step 1: Check server
    if not check_server_running():
        print("\n[ABORT] Cannot continue - server not running")
        return 1

    # Step 2: Test login
    session = test_login()
    if not session:
        print("\n[ABORT] Cannot continue - login failed")
        return 1

    # Step 3: Check files
    check_files_exist()

    # Step 4: Test endpoints
    results = test_enhanced_endpoints(session)

    # Step 5: Print summary
    success = print_summary(results)

    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
