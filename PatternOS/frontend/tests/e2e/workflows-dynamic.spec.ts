import { test, expect } from "@playwright/test";
import { API_BASE } from "./_helpers";

/**
 * Deep-link workflows — IDs from live API (skipped when empty DB).
 */
test.describe("Workflow — dynamic routes", () => {
  test("studio backtest runs page for first pattern", async ({ page, request }) => {
    const res = await request.get(`${API_BASE}/patterns/`);
    expect(res.ok()).toBeTruthy();
    const patterns = (await res.json()) as { id: string }[];
    test.skip(!patterns?.length, "No patterns in DB");

    await page.goto(`/studio/${patterns[0].id}/runs`);
    await expect(page.getByRole("heading", { name: "Backtest Runs" })).toBeVisible({ timeout: 30_000 });
  });

  test("screener results page for first screener", async ({ page, request }) => {
    const res = await request.get(`${API_BASE}/screener/`);
    expect(res.ok()).toBeTruthy();
    const rows = (await res.json()) as { id: string }[];
    test.skip(!rows?.length, "No screeners in DB");

    await page.goto(`/screener/${rows[0].id}/results`);
    await expect(page.getByRole("heading", { name: "Screener Results" })).toBeVisible({ timeout: 45_000 });
  });

  test("stress test portfolio detail + run results when data exists", async ({
    page,
    request,
  }) => {
    const pres = await request.get(`${API_BASE}/stress-test/portfolio`);
    expect(pres.ok()).toBeTruthy();
    const portfolios = (await pres.json()) as { id: string; name?: string }[];
    test.skip(!portfolios?.length, "No stress-test portfolios");

    const pid = portfolios[0].id;
    const pname = portfolios[0].name?.trim() || "Portfolio";
    await page.goto(`/stress-test/${pid}`);
    await expect(page.getByRole("heading", { name: pname })).toBeVisible({
      timeout: 30_000,
    });

    const runsRes = await request.get(`${API_BASE}/stress-test/portfolio/${pid}/runs`);
    expect(runsRes.ok()).toBeTruthy();
    const runs = (await runsRes.json()) as { id: string }[];
    test.skip(!runs?.length, "No stress-test runs for portfolio");

    await page.goto(`/stress-test/run/${runs[0].id}`);
    await expect(page.getByRole("heading", { name: "Stress Test Results" })).toBeVisible({
      timeout: 30_000,
    });
  });

  test("MF scheme detail from first scheme in API", async ({ page, request }) => {
    const res = await request.get(`${API_BASE}/mf/schemes?limit=5`);
    expect(res.ok()).toBeTruthy();
    const schemes = (await res.json()) as { scheme_code: number }[];
    test.skip(!schemes?.length, "No MF schemes");

    const code = schemes[0].scheme_code;
    await page.goto(`/mf/schemes/${code}`);
    await expect(page.getByText(`AMFI ${code}`)).toBeVisible({ timeout: 45_000 });
  });
});
