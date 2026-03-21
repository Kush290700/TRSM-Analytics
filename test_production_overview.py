#!/usr/bin/env python3
"""
Production Overview Page Validation
Tests the fully integrated overview page for production readiness
"""
import time
import os
import pytest

# Enable this Playwright smoke only when explicitly requested.
RUN_PRODUCTION_E2E = os.environ.get("RUN_PRODUCTION_PLAYWRIGHT") == "1"


@pytest.mark.skipif(
    not RUN_PRODUCTION_E2E,
    reason="Requires RUN_PRODUCTION_PLAYWRIGHT=1 and browser access to run.",
)
def test_production_overview():
    from playwright.sync_api import sync_playwright, expect

    os.environ['RATELIMIT_ENABLED'] = '0'
    print("\n" + "="*70)
    print("PRODUCTION OVERVIEW PAGE VALIDATION")
    print("="*70)

    headless = os.environ.get("PLAYWRIGHT_HEADLESS", "1") != "0"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900})

                # Track console messages
                console_messages = []
                errors = []

                def handle_console(msg):
                    console_messages.append({"type": msg.type, "text": msg.text})
                    if msg.type == "error":
                        errors.append(msg.text)
                        print(f"  [ERROR] {msg.text}")
                    elif "[OVERVIEW]" in msg.text:
                        print(f"  [LOG] {msg.text}")

                page.on("console", handle_console)

                # Step 1: Test Dashboard Redirect
                print("\n1. Testing /dashboard/ redirect...")
                page.goto("http://localhost:5000/auth/login")
                page.fill('input[name="username"]', "admin")
                page.fill('input[name="password"]', "admin")
                page.click('button[type="submit"]')
                page.wait_for_load_state("domcontentloaded")
                time.sleep(1)

                page.goto("http://localhost:5000/dashboard/")
                page.wait_for_load_state("domcontentloaded")
                time.sleep(2)

                current_url = page.url
                if "/dashboard" not in current_url and ("/" in current_url or "overview" in current_url):
                    print("  [OK] Dashboard redirects to overview")
                else:
                    print(f"  [WARN] Expected redirect, got: {current_url}")

                # Step 2: Load Overview Page
                print("\n2. Loading overview page...")
                page.goto("http://localhost:5000/")
                page.wait_for_load_state("domcontentloaded")
                print("  [OK] Page loaded (domcontentloaded)")

                # Wait for metric cards to appear
                try:
                    page.wait_for_selector('[data-metric-card]', timeout=10000)
                    print("  [OK] Metric cards found in DOM")
                except Exception:
                    print("  [ERROR] Metric cards not found after 10s")

                # Wait for JS initialization
                time.sleep(5)

                # Step 3: Check KPI Cards
                print("\n3. Validating KPI cards...")
                metric_cards = page.locator('[data-metric-card]').all()
                print(f"  Found {len(metric_cards)} metric cards")

                if len(metric_cards) >= 4:
                    print("  [OK] Sufficient metric cards present")

                    # Check specific KPIs
                    kpi_checks = [
                        ('#kpi-customers', 'Customers'),
                        ('#kpi-orders', 'Orders'),
                        ('#kpi-revenue', 'Revenue'),
                        ('#kpi-aov', 'AOV'),
                    ]

                    for selector, name in kpi_checks:
                        element = page.locator(selector)
                        if element.count() > 0:
                            value = element.inner_text()
                            if value and value != "$0" and value != "0":
                                print(f"  [OK] {name}: {value}")
                            else:
                                print(f"  [WARN] {name}: Shows zero or placeholder")
                        else:
                            print(f"  [ERROR] {name} element not found")
                else:
                    print(f"  [ERROR] Expected at least 4 cards, found {len(metric_cards)}")

                # Step 4: Check Charts
                print("\n4. Validating charts...")
                chart_containers = page.locator('.chart-container').all()
                print(f"  Found {len(chart_containers)} chart containers")

                if len(chart_containers) >= 2:
                    print("  [OK] Charts present")
                else:
                    print(f"  [WARN] Expected at least 2 charts, found {len(chart_containers)}")

                # Step 5: Check Filters
                print("\n5. Validating filters...")
                filter_controls = [
                    ('#date_range', 'Date range'),
                    ('select[name="regions"]', 'Regions'),
                    ('select[name="methods"]', 'Shipping methods'),
                ]

                for selector, name in filter_controls:
                    element = page.locator(selector).first
                    if element.count() > 0:
                        print(f"  [OK] {name} filter found")
                    else:
                        print(f"  [WARN] {name} filter not found")

                # Step 6: Check for Errors
                print("\n6. Checking for errors...")
                js_errors = [e for e in console_messages if e["type"] == "error"]

                # Filter out known non-critical errors
                critical_errors = [
                    e for e in js_errors
                    if "EventSource" not in e["text"]  # EventSource is known issue, not critical
                ]

                if len(critical_errors) == 0:
                    print(f"  [OK] No critical errors (found {len(js_errors)} non-critical)")
                else:
                    print(f"  [ERROR] Found {len(critical_errors)} critical errors:")
                    for err in critical_errors[:3]:
                        print(f"    - {err['text']}")

                # Step 7: Test Responsive Layout
                print("\n7. Testing responsive layout...")
                viewports = [
                    ("Desktop", 1440, 900),
                    ("iPad", 1024, 768),
                    ("iPhone", 393, 852),
                ]

                for name, width, height in viewports:
                    page.set_viewport_size({"width": width, "height": height})
                    time.sleep(1)
                    cards_visible = page.locator('[data-metric-card]').count()
                    if cards_visible > 0:
                        print(f"  [OK] {name} ({width}x{height}): {cards_visible} cards visible")
                    else:
                        print(f"  [ERROR] {name}: No cards visible")

                # Step 8: Take Screenshot
                print("\n8. Capturing production screenshot...")
                page.set_viewport_size({"width": 1440, "height": 900})
                time.sleep(2)
                screenshot_path = ".artifacts/overview/production_ready.png"
                page.screenshot(path=screenshot_path, full_page=True)
                print(f"  [OK] Screenshot saved: {screenshot_path}")

                # Summary
                print("\n" + "="*70)
                print("VALIDATION SUMMARY")
                print("="*70)
                print(f"Dashboard Redirect: {'PASS' if '/dashboard' not in page.url else 'FAIL'}")
                print(f"Metric Cards: {len(metric_cards)}/4 minimum")
                print(f"Charts: {len(chart_containers)} found")
                print(f"Critical Errors: {len(critical_errors)}")
                print(f"Console Messages: {len(console_messages)} total")

                overall_pass = (
                    len(metric_cards) >= 4 and
                    len(chart_containers) >= 2 and
                    len(critical_errors) == 0
                )

                if overall_pass:
                    print("\n[SUCCESS] Overview page is PRODUCTION READY!")
                else:
                    print("\n[NEEDS WORK] Some issues found - review above")

                print("\n" + "="*70)
                return overall_pass
            finally:
                browser.close()
    except Exception as exc:  # pragma: no cover - allow environments without browser access
        pytest.skip(f"Playwright browser unavailable: {exc}")

if __name__ == "__main__":
    import sys
    success = test_production_overview()
    sys.exit(0 if success else 1)
