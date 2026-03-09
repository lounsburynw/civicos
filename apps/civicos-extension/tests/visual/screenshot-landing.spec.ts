/**
 * Generate a screenshot of the extension side panel for the docs landing page.
 *
 * Usage:
 *   cd apps/civicos-extension
 *   npx playwright test tests/visual/screenshot-landing.spec.ts
 *
 * Output: docs/public/assets/extension-screenshot.png
 */
import { test } from '@playwright/test';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUTPUT_PATH = resolve(__dirname, '../../../../docs/public/assets/extension-screenshot.png');

test('generate landing page screenshot', async ({ page }) => {
  await page.goto('/?level=city');
  await page.waitForSelector('.panel');

  // Let fonts and transitions settle
  await page.waitForTimeout(500);

  await page.screenshot({
    path: OUTPUT_PATH,
    clip: { x: 0, y: 0, width: 380, height: 680 },
  });
});
