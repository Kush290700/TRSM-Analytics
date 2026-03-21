#!/usr/bin/env python3
"""Quick diagnostic check of the Overview page"""
import time
from playwright.sync_api import sync_playwright

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        # Navigate and login
        print("Logging in...")
        page.goto("http://localhost:5000/auth/login")
        page.fill('input[name="username"]', "admin")
        page.fill('input[name="password"]', "admin")
        page.click('button[type="submit"]')
        page.wait_for_load_state("domcontentloaded")
        time.sleep(2)

        # Navigate to overview
        print("Navigating to overview...")
        page.goto("http://localhost:5000/overview")
        page.wait_for_load_state("domcontentloaded")
        time.sleep(5)  # Wait for JS to execute

        # Check page content
        print("\n=== Page Diagnostics ===")

        # Check if overview page container exists
        overview_page = page.locator('#overviewPage')
        print(f"overviewPage exists: {overview_page.count() > 0}")

        # Check for metric cards
        metric_cards = page.locator('[data-metric-card]')
        print(f"Metric cards found: {metric_cards.count()}")

        # Check for KPI elements
        kpi_customers = page.locator('#kpi-customers')
        print(f"kpi-customers exists: {kpi_customers.count() > 0}")
        if kpi_customers.count() > 0:
            print(f"kpi-customers text: {kpi_customers.inner_text()}")

        # Check for charts
        charts = page.locator('.chart-container')
        print(f"Chart containers found: {charts.count()}")

        # Check if overview.js loaded
        js_loaded = page.evaluate("typeof window.__OVERVIEW_ENDPOINTS__ !== 'undefined'")
        print(f"overview.js bridge loaded: {js_loaded}")

        # Check for errors in console
        errors = []
        def handle_console(msg):
            if msg.type == "error":
                errors.append(msg.text)
        page.on("console", handle_console)

        time.sleep(2)
        if errors:
            print(f"\nConsole errors:")
            for err in errors[:5]:
                print(f"  - {err}")

        # Take screenshot
        page.screenshot(path=".artifacts/overview/quick_check.png", full_page=True)
        print("\nScreenshot saved to .artifacts/overview/quick_check.png")

        input("\nPress Enter to close browser...")
        browser.close()

if __name__ == "__main__":
    main()
