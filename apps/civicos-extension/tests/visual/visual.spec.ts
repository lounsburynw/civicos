import { test, expect } from '@playwright/test';

test.describe('CivicOS Extension Visual Tests', () => {
  test('city-pulse', async ({ page }) => {
    await page.goto('/?level=city');
    await page.waitForSelector('.panel');
    await expect(page).toHaveScreenshot('city-pulse.png', { fullPage: true });
  });

  test('state-pulse', async ({ page }) => {
    await page.goto('/?level=state');
    await page.waitForSelector('.panel');
    await expect(page).toHaveScreenshot('state-pulse.png', { fullPage: true });
  });

  test('federal-pulse', async ({ page }) => {
    await page.goto('/?level=federal');
    await page.waitForSelector('.panel');
    await expect(page).toHaveScreenshot('federal-pulse.png', { fullPage: true });
  });

  test('state-take-action', async ({ page }) => {
    await page.goto('/?level=state');
    await page.waitForSelector('.focal-points-group');
    const focalGroup = page.locator('.focal-points-group');
    await expect(focalGroup).toHaveScreenshot('state-take-action.png');
  });

  test('federal-urgency-badges', async ({ page }) => {
    await page.goto('/?level=federal');
    await page.waitForSelector('.deadline-tag');
    const deadlineTags = page.locator('.deadline-tag');
    // Screenshot the first comment period card which contains urgency badges
    const firstFocalCard = page.locator('.focal-card').first();
    await expect(firstFocalCard).toHaveScreenshot('federal-urgency-badges.png');
  });

  test('city-sections', async ({ page }) => {
    await page.goto('/?level=city');
    await page.waitForSelector('.feed-section');
    const sections = page.locator('.feed-section');
    const count = await sections.count();
    expect(count).toBeGreaterThanOrEqual(3);
    await expect(page).toHaveScreenshot('city-sections.png', { fullPage: true });
  });
});
