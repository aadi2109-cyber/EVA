import { defineConfig } from '@playwright/test';
import { existsSync } from 'node:fs';

// Cloud sandboxes ship a pre-installed Chromium; use it instead of downloading one.
const preinstalled = '/opt/pw-browsers/chromium';
const executablePath =
  process.env.PLAYWRIGHT_CHROMIUM_PATH || (existsSync(preinstalled) ? preinstalled : undefined);
const PORT = 5199;

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: `http://localhost:${PORT}`,
    viewport: { width: 1400, height: 1000 },
    launchOptions: { executablePath, args: ['--no-sandbox'] },
  },
  // The API is stubbed per-test with page.route, so no backend is needed.
  webServer: {
    command: `npx vite --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
