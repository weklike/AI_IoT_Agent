import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './e2e', timeout: 45000, workers: 1, retries: 0,
  outputDir: process.env.E2E_OUTPUT || '../artifacts/acceptance/e2e',
  reporter: [['list'], ['junit', { outputFile: `${process.env.E2E_OUTPUT || '../artifacts/acceptance/e2e'}/results.xml` }]],
  use: { baseURL: process.env.E2E_BASE_URL, trace: 'retain-on-failure', screenshot: 'only-on-failure' }
})
