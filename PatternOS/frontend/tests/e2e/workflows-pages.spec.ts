import { test, expect } from "@playwright/test";

/**
 * Smoke: every primary route renders without crash (requires backend + Next).
 */
test.describe("Workflow — static pages render", () => {
  test("home dashboard or backend-off message", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }).or(page.getByText(/Failed to load/i)),
    ).toBeVisible({ timeout: 30_000 });
  });

  test("equity: Signal Inbox", async ({ page }) => {
    await page.goto("/signals");
    await expect(page.getByRole("heading", { name: "Signal Inbox" })).toBeVisible();
  });

  test("equity: Universe", async ({ page }) => {
    await page.goto("/universe");
    await expect(page.getByRole("heading", { name: "Universe" })).toBeVisible();
  });

  test("equity: Chart Tool (toolbar)", async ({ page }) => {
    await page.goto("/chart");
    await expect(page.getByRole("button", { name: /Symbol/i })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTitle("Clear drawings")).toBeVisible();
  });

  test("equity: Pattern Studio", async ({ page }) => {
    await page.goto("/studio");
    await expect(page.getByRole("heading", { name: "Pattern Studio" })).toBeVisible({ timeout: 30_000 });
  });

  test("equity: Trade Journal", async ({ page }) => {
    await page.goto("/journal");
    await expect(page.getByRole("heading", { name: "Trade Journal" })).toBeVisible();
  });

  test("equity: Stock Comparison", async ({ page }) => {
    await page.goto("/compare");
    await expect(page.getByRole("heading", { name: "Stock Comparison" })).toBeVisible();
  });

  test("equity: F&O Analysis", async ({ page }) => {
    await page.goto("/fno");
    await expect(page.getByRole("heading", { name: "F&O Analysis" })).toBeVisible();
  });

  test("equity: Analytics", async ({ page }) => {
    await page.goto("/analytics");
    await expect(page.getByRole("heading", { name: "Analytics" })).toBeVisible();
  });

  test("equity: Sector Heatmap", async ({ page }) => {
    await page.goto("/analytics/sectors");
    await expect(page.getByRole("heading", { name: "Sector Heatmap" })).toBeVisible();
  });

  test("equity: Indicator Playground", async ({ page }) => {
    await page.goto("/indicators");
    await expect(page.getByRole("heading", { name: "Indicator Playground" })).toBeVisible();
  });

  test("equity: Custom Screener list", async ({ page }) => {
    await page.goto("/screener");
    await expect(page.getByRole("heading", { name: "Custom Screener" })).toBeVisible({ timeout: 30_000 });
  });

  test("equity: Screener builder", async ({ page }) => {
    await page.goto("/screener/builder");
    await expect(page.getByRole("heading", { name: /Create Screener|Edit Screener/ })).toBeVisible();
  });

  test("equity: Stress test portfolios", async ({ page }) => {
    await page.goto("/stress-test");
    await expect(page.getByRole("heading", { name: "Portfolios" })).toBeVisible({ timeout: 30_000 });
  });

  test("system: Status page", async ({ page }) => {
    await page.goto("/status");
    await expect(page.getByRole("heading", { name: "System Status" })).toBeVisible({ timeout: 30_000 });
  });

  test("MF: hub", async ({ page }) => {
    await page.goto("/mf");
    await expect(page.getByRole("heading", { name: "Mutual Funds" })).toBeVisible();
  });

  test("MF: Chart Tool", async ({ page }) => {
    await page.goto("/mf/chart");
    await expect(page.getByText(/Select Scheme/i).first()).toBeVisible({ timeout: 45_000 });
  });

  test("MF: Schemes directory", async ({ page }) => {
    await page.goto("/mf/schemes");
    await expect(page.getByRole("heading", { name: "Schemes" })).toBeVisible({ timeout: 45_000 });
  });

  test("MF: Signals", async ({ page }) => {
    await page.goto("/mf/signals");
    await expect(page.getByRole("heading", { name: "MF Signals" })).toBeVisible({ timeout: 30_000 });
  });

  test("MF: Rulebooks", async ({ page }) => {
    await page.goto("/mf/rulebooks");
    await expect(page.getByRole("heading", { name: "MF Rulebooks" })).toBeVisible({ timeout: 30_000 });
  });

  test("MF: Pipelines", async ({ page }) => {
    await page.goto("/mf/pipelines");
    await expect(page.getByRole("heading", { name: "MF Pipeline Runs" })).toBeVisible({ timeout: 30_000 });
  });
});
