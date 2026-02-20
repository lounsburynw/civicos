import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: 'tests/visual',
  testMatch: '*.spec.ts',
  snapshotPathTemplate: '{testDir}/__screenshots__/{testFilePath}/{arg}{ext}',
  use: {
    viewport: { width: 380, height: 900 },
    baseURL: 'http://localhost:5199',
  },
  expect: {
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.01,
    },
  },
  webServer: {
    command: 'npx vite --config vite.harness.config.ts',
    port: 5199,
    reuseExistingServer: !process.env.CI,
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
});
