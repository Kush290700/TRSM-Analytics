import { test, expect } from '@playwright/test';

test.describe('Global filters', () => {
  test('render and populate without reload', async ({ page }) => {
    await page.goto('/');

    const filters = page.locator('#GlobalFilters');
    await expect(filters).toBeVisible();
    await expect(filters.locator('#filtersApply')).toBeVisible();

    await page.waitForSelector('#fRegions option', { timeout: 20000 });
    const regionOptions = await filters.locator('#fRegions option').count();
    expect(regionOptions).toBeGreaterThan(0);

    const methodOptions = await filters.locator('#fMethods option').count();
    expect(methodOptions).toBeGreaterThan(0);
  });
});
