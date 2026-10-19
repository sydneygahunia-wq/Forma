import { defineConfig, devices } from "@playwright/test";

// The e2e run boots its own isolated stack on separate ports: a fresh SQLite
// database, a fast simulation tick, and a Next dev server pointed at it.
const API_PORT = 8100;
const WEB_PORT = 3100;
const backendDir = "../backend";
const python = process.env.E2E_PYTHON ?? `${backendDir}/.venv/bin/python`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `rm -f e2e.db e2e.db-wal e2e.db-shm && ${python.replace(backendDir, ".")} -m uvicorn app.main:app --port ${API_PORT}`,
      cwd: backendDir,
      url: `http://localhost:${API_PORT}/api/health`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        DATABASE_URL: "sqlite:///./e2e.db",
        TICK_INTERVAL_MS: "40",
        CORS_ORIGINS: `["http://localhost:${WEB_PORT}"]`,
        LOG_LEVEL: "WARNING",
      },
    },
    {
      // Test the production build: it is what ships, and it catches
      // prerendering errors that `next dev` doesn't.
      command: `npx next build && npx next start --port ${WEB_PORT}`,
      url: `http://localhost:${WEB_PORT}`,
      reuseExistingServer: false,
      timeout: 240_000,
      env: { NEXT_PUBLIC_API_URL: `http://localhost:${API_PORT}`, NEXT_TELEMETRY_DISABLED: "1" },
    },
  ],
});
