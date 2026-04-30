import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000",
    trace: "retain-on-failure",
  },
  reporter: [["list"]],
  /**
   * Starts Next.js when port 3000 is free; set PLAYWRIGHT_NO_WEBSERVER=1 if you already run `npm run dev`.
   * PatternOS E2E still requires the FastAPI backend (proxied via /api/v1) for most tests.
   */
  webServer:
    process.env.PLAYWRIGHT_NO_WEBSERVER === "1"
      ? undefined
      : {
          command: "npm run dev",
          url: "http://localhost:3000",
          reuseExistingServer: true,
          timeout: 180_000,
        },
});
