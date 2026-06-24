import { defineConfig, devices } from "@playwright/test";

// Route-smoke tests for the refactored console/workspace/client-status routes.
//
// SAFETY: the app's real API base is the PRODUCTION API (auth + PAID Apollo credits). These tests
// must NEVER reach it. Two guards, both required:
//   1. The dev server is started with NEXT_PUBLIC_API_BASE_URL pointed at a DEAD local port
//      (127.0.0.1:9876), so any request the tests forget to mock fails locally instead of hitting
//      prod.
//   2. Every test page.route()-intercepts that base (http://127.0.0.1:9876/**) and fulfills with
//      mock JSON — see e2e/_mock.ts. No request is ever allowed to reach a real host.
const API_BASE = "http://127.0.0.1:9876";
const PORT = 3100;
// Serve the dev app from `localhost` (not 127.0.0.1): Next 16's dev server blocks cross-origin
// requests to its own /_next dev resources unless the host is allow-listed, and accessing via a
// bare IP trips that guard — which silently breaks client hydration (effects like the index
// redirect never run). `localhost` is same-origin-allowed by default, so no next.config change is
// needed. The PAID-API safety guard is unaffected: the API base stays a dead 127.0.0.1 port and
// every API call is still page.route()-intercepted.
const HOST = "localhost";

export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  // The client-side redirects/hydration these smokes exercise have a small timing window; one retry
  // locally (two on CI) absorbs transient flakes without masking a real regression.
  retries: process.env.CI ? 2 : 1,
  reporter: [["list"]],
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: `http://${HOST}:${PORT}`,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `next dev -H ${HOST} -p ${PORT}`,
    url: `http://${HOST}:${PORT}/login`,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    env: { NEXT_PUBLIC_API_BASE_URL: API_BASE },
  },
});
