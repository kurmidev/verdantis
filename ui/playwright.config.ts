import { defineConfig, devices } from '@playwright/test'

// E2E runs against the Vite dev server with the MSW mock layer (backend P2/P3 not deployed yet).
// Against staging, set E2E_BASE_URL and VITE_USE_MOCKS=false instead (LLD 13 3.20).
const base = process.env.E2E_BASE_URL ?? 'http://localhost:5173'
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  reporter: 'list',
  use: { baseURL: base, trace: 'on-first-retry' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : { command: 'npm run dev:mock -- --port 5173 --strictPort', url: base, reuseExistingServer: true },
})
