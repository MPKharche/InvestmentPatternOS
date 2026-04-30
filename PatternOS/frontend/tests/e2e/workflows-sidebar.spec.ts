import { test, expect } from "@playwright/test";

/**
 * Navigation shell — sidebar links reach the intended routes (desktop layout).
 */
test.describe("Workflow — sidebar navigation", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("Equity Chart Tool from sidebar", async ({ page }) => {
    await page.goto("/");
    await page.locator('a[href="/chart"]').first().click();
    await expect(page).toHaveURL(/\/chart$/);
    await expect(page.getByRole("button", { name: /Symbol/i })).toBeVisible({ timeout: 30_000 });
  });

  test("MF Schemes from sidebar", async ({ page }) => {
    await page.goto("/mf");
    await page.locator('a[href="/mf/schemes"]').first().click();
    await expect(page).toHaveURL(/\/mf\/schemes$/);
    await expect(page.getByRole("heading", { name: "Schemes" })).toBeVisible({ timeout: 45_000 });
  });

  test("System Status from sidebar", async ({ page }) => {
    await page.goto("/signals");
    await page.locator('a[href="/status"]').first().click();
    await expect(page).toHaveURL(/\/status$/);
    await expect(page.getByRole("heading", { name: "System Status" })).toBeVisible({ timeout: 30_000 });
  });
});
