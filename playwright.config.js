// @ts-check
const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './e2e',
  timeout: 120000,
  expect: { timeout: 15000 },
  fullyParallel: false,
  retries: 0,
  use: {
    baseURL: process.env.JARVIS_E2E_URL || 'http://127.0.0.1:8000',
    headless: true,
    locale: 'fr-FR',
  },
  webServer: process.env.JARVIS_E2E_NO_SERVER
    ? undefined
    : {
        command: process.env.JARVIS_PYTHON || 'venv\\Scripts\\python.exe main_fast_WINDOWS_ULTRA.py',
        url: 'http://127.0.0.1:8000/api',
        reuseExistingServer: true,
        timeout: 120000,
      },
});
