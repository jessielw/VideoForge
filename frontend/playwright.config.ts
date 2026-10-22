import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/browser',
  outputDir: '../build/queue-browser-results',
  fullyParallel: true,
  use: {
    baseURL: 'http://127.0.0.1:5178',
    viewport: { width: 1600, height: 900 },
    colorScheme: 'light',
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE }
      : {},
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: process.env.PLAYWRIGHT_PREVIEW
      ? 'npm run preview -- --host 127.0.0.1 --port 5178 --strictPort'
      : 'npm run dev -- --host 127.0.0.1 --port 5178 --strictPort',
    url: 'http://127.0.0.1:5178',
    reuseExistingServer: false,
  },
})
