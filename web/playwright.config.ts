import { defineConfig } from '@playwright/test'

// Runs against the real FastAPI server and the real runs in ../runs (build the UI first: npm run build).
export default defineConfig({
  testDir: './e2e',
  timeout: 45_000,
  use: { baseURL: 'http://127.0.0.1:8765', channel: 'chrome', viewport: { width: 1366, height: 768 } },
  webServer: {
    command: '.venv\\Scripts\\python -m forgeai serve --port 8765',  // cwd is the repo root
    cwd: '..',
    url: 'http://127.0.0.1:8765/api/runs',
    reuseExistingServer: true,
    timeout: 60_000,
  },
})
