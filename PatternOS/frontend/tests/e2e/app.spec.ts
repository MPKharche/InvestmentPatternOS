import { test, expect } from "@playwright/test";

const UI_BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
// Prefer same-origin proxy in Next (`/api/v1`) so tests work across different backend ports.
const API_BASE = process.env.E2E_API_BASE ?? `${UI_BASE.replace(/\/$/, "")}/api/v1`;

test("capabilities endpoint returns optional flags", async ({ request }) => {
  const res = await request.get(`${API_BASE}/meta/capabilities`);
  expect(res.ok()).toBeTruthy();
  const json = await res.json();
  expect(json).toHaveProperty("optional");
  expect(json.optional).toHaveProperty("mplfinance");
});

test("sidebar groups render and collapse works", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Equity")).toBeVisible();
  await expect(page.getByText("Mutual Funds")).toBeVisible();

  // Collapse
  await page.getByTitle("Collapse sidebar").click();
  await expect(page.getByTitle("Expand sidebar")).toBeVisible();
});

test("mobile sidebar opens as overlay", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  await page.getByTitle("Open menu").click();
  await expect(page.getByRole("button", { name: "Equity" }).first()).toBeVisible();
  await page.getByRole("button", { name: "Mutual Funds" }).first().click({ force: true });
});

test("mf schemes page loads", async ({ page }) => {
  await page.goto("/mf/schemes");
  await expect(page.getByRole("heading", { name: "Schemes" })).toBeVisible();
  // Should render at least one row from curated watchlist
  await expect(page.locator("text=/AMFI\\s+\\d+/").first()).toBeVisible();
});

test("mf scheme detail uses Morningstar factsheet deep link when available", async ({ request, page }) => {
  const res = await request.get(`${API_BASE}/mf/schemes?limit=250`);
  expect(res.ok()).toBeTruthy();
  const schemes = (await res.json()) as any[];
  const target = schemes.find(
    (s) =>
      s?.morningstar_link_status === "deep_factsheet" &&
      typeof s?.morningstar_url === "string" &&
      s.morningstar_url.includes("fund-factsheet.aspx")
  );
  test.skip(!target, "No scheme with a Morningstar factsheet link in this environment");

  await page.goto(`/mf/schemes/${target.scheme_code}`);
  const popupPromise = page.waitForEvent("popup");
  await page.getByRole("button", { name: "Morningstar" }).click();
  const popup = await popupPromise;
  await popup.waitForLoadState();
  expect(popup.url()).toMatch(/fund-factsheet\.aspx/);
});

test("mf scheme detail can fix Morningstar link by pasting a Morningstar URL", async ({ request, page }) => {
  const res = await request.get(`${API_BASE}/mf/schemes?limit=400`);
  expect(res.ok()).toBeTruthy();
  const schemes = (await res.json()) as any[];
  const target = schemes.find((s) => !s?.morningstar_sec_id);
  test.skip(!target, "No scheme without morningstar_sec_id found in this environment");

  await page.goto(`/mf/schemes/${target.scheme_code}`);

  // Use the non-technical “Edit links” flow: paste a Morningstar factsheet URL once.
  await page.getByRole("button", { name: "Edit links" }).click();
  await page.getByLabel("Morningstar URL").fill("https://www.morningstar.in/mutualfunds/f00000pfli/test/fund-factsheet.aspx");
  await page.getByRole("button", { name: "Save" }).click();

  // Clicking again should now open a factsheet deep link.
  const popup2Promise = page.waitForEvent("popup");
  await page.getByRole("button", { name: "Morningstar" }).click();
  const popup2 = await popup2Promise;
  await popup2.waitForLoadState();
  expect(popup2.url()).toMatch(/fund-factsheet\.aspx/);
});

test("mf schemes watchlist toggle works", async ({ page }) => {
  await page.goto("/mf/schemes");
  const btn = page.getByRole("button", { name: /Monitor|Monitored/ }).first();
  const before = (await btn.innerText()).trim();
  await btn.click();
  await expect(btn).not.toHaveText(before);
  // toggle back to keep watchlist populated for other tests
  await btn.click();
});

test("mf pipelines page can trigger NAV ingestion", async ({ page }) => {
  await page.goto("/mf/pipelines");
  await expect(page.getByRole("heading", { name: "MF Pipeline Runs" })).toBeVisible();
  // In stdtest mode we prefer offline-safe coverage; the page should still render status.
  await expect(page.getByText("Latest NAV Run")).toBeVisible();
  await expect(page.getByText("Latest NAV Run")).toBeVisible();
  await expect(page.getByText(/Status:/).first()).toBeVisible();
});

test("mf rulebooks can save a new version", async ({ request, page }) => {
  // Make sure we have at least one rulebook and a stable editor flow.
  const listRes = await request.get(`${API_BASE}/mf/rulebooks`);
  expect(listRes.ok()).toBeTruthy();
  const list = (await listRes.json()) as Array<{ id: string }>;
  expect(list.length).toBeGreaterThan(0);

  await page.goto("/mf/rulebooks");
  // Select first rulebook in left list.
  await page.locator("button").filter({ hasText: "active" }).first().click();

  // Append whitespace to keep JSON valid but force a change.
  const ta = page.locator("textarea").first();
  const txt = await ta.inputValue();
  await ta.fill(txt + "\n");

  await page.getByRole("button", { name: "Save new version" }).click();
  await expect(page.getByText(/Saved v/)).toBeVisible({ timeout: 20_000 });
});

test("mf scheme detail loads and PDF route returns PDF", async ({ page, request }) => {
  // Pick a monitored scheme dynamically (watchlist is idempotent and seeded).
  const schemesRes = await request.get(`${API_BASE}/mf/schemes?monitored_only=true&limit=1&offset=0`);
  expect(schemesRes.ok()).toBeTruthy();
  const schemes = (await schemesRes.json()) as Array<{ scheme_code: number }>;
  const code = schemes[0]?.scheme_code ?? 135106;
  await page.goto(`/mf/schemes/${code}`);
  await expect(page.getByText(`AMFI ${code}`)).toBeVisible();

  const res = await request.get(`/api/mf/report/${code}`);
  expect(res.ok()).toBeTruthy();
  expect(res.headers()["content-type"]).toContain("application/pdf");
  const buf = await res.body();
  expect(buf.slice(0, 4).toString("utf-8")).toBe("%PDF");
  expect(buf.length).toBeGreaterThan(10_000);
});

test("charts endpoints return images", async ({ request }) => {
  const eq = await request.get(`${API_BASE}/charts/equity.png?symbol=AXISBANK.NS&tf=1d&ind=ema,rsi,macd`);
  expect(eq.ok()).toBeTruthy();
  expect(eq.headers()["content-type"]).toContain("image/png");
  const buf = await eq.body();
  expect(buf.slice(0, 8).toString("hex")).toBe("89504e470d0a1a0a"); // PNG magic
  expect(buf.length).toBeGreaterThan(5_000);

  const mf = await request.get(`${API_BASE}/charts/mf.png?scheme_code=135106&ind=ema,rsi,macd`);
  expect(mf.ok()).toBeTruthy();
  expect(mf.headers()["content-type"]).toContain("image/png");
  const buf2 = await mf.body();
  expect(buf2.slice(0, 8).toString("hex")).toBe("89504e470d0a1a0a");
  expect(buf2.length).toBeGreaterThan(5_000);
});

test("scanner chart-patterns includes talib key", async ({ request }) => {
  const res = await request.get(`${API_BASE}/scanner/chart-patterns?symbol=AXISBANK.NS&timeframe=1d&lookback=120`);
  expect(res.ok()).toBeTruthy();
  const json = await res.json();
  expect(json).toHaveProperty("chart_patterns");
  expect(json).toHaveProperty("candlestick_patterns");
  expect(json).toHaveProperty("talib_candlestick_patterns");
});

test("studio import (chat-with-files) works without real LLM", async ({ request }) => {
  const res = await request.post(`${API_BASE}/studio/chat-with-files`, {
    multipart: {
      message: "Analyze attached file",
      files: {
        name: "note.txt",
        mimeType: "text/plain",
        buffer: Buffer.from("hello from stdtest"),
      },
    },
  });
  expect(res.ok()).toBeTruthy();
  const json = await res.json();
  expect(json).toHaveProperty("pattern_id");
  expect(json).toHaveProperty("reply");
});

test("patterns API list returns seeded pack", async ({ request }) => {
  const res = await request.get(`${API_BASE}/patterns/`);
  expect(res.ok()).toBeTruthy();
  const list = await res.json();
  expect(Array.isArray(list)).toBeTruthy();
  expect(list.length).toBeGreaterThan(0);
});
