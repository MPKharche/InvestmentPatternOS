import { chromium } from "playwright";

export const runtime = "nodejs";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

function esc(s: string) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c] as string));
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status} on ${path}`);
  return res.json() as Promise<T>;
}

function fmtPct(v: any) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  return `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;
}

function fmtNum(v: any, dp = 2) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toFixed(dp);
}

export async function GET(_: Request, ctx: { params: Promise<{ scheme_code: string }> }) {
  const { scheme_code } = await ctx.params;
  const cleaned = scheme_code.endsWith(".pdf") ? scheme_code.slice(0, -4) : scheme_code;
  const schemeCode = Number(cleaned);
  if (!Number.isFinite(schemeCode)) {
    return new Response("Invalid scheme_code", { status: 400 });
  }

  const scheme = await getJson<any>(`/mf/schemes/${schemeCode}`);
  const metrics = await getJson<any>(`/mf/schemes/${schemeCode}/metrics`);
  const signalsAll = await getJson<any[]>(`/mf/signals?status=all&limit=100`);
  const signals = (signalsAll || []).filter((s) => s.scheme_code === schemeCode).slice(0, 5);

  let holdings: any = null;
  if (scheme?.family_id) {
    try {
      holdings = await getJson<any>(`/mf/families/${scheme.family_id}/holdings`);
    } catch {
      holdings = null;
    }
  }

  const topHoldings = (holdings?.holdings || [])
    .filter((h: any) => (h.holding_type === "equity" || h.holding_type === "debt") && h?.name)
    .sort((a: any, b: any) => (Number(b.weight_pct) || 0) - (Number(a.weight_pct) || 0))
    .slice(0, 10);

  const title = scheme?.scheme_name ? String(scheme.scheme_name) : `Scheme ${schemeCode}`;
  const asOf = scheme?.latest_nav_date ? String(scheme.latest_nav_date) : (metrics?.nav_date ? String(metrics.nav_date) : new Date().toISOString().slice(0, 10));

  const html = `<!doctype html>
  <html>
  <head>
    <meta charset="utf-8" />
    <style>
      @page { size: A4; margin: 18mm 14mm; }
      html, body { padding: 0; margin: 0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial; }
      .muted { color: #475569; }
      .small { font-size: 10px; }
      .h1 { font-size: 18px; font-weight: 800; letter-spacing: -0.02em; margin: 0; }
      .row { display: flex; gap: 12px; }
      .col { flex: 1; }
      .card { border: 1px solid #e2e8f0; border-radius: 10px; padding: 10px 12px; }
      .kpi { font-size: 14px; font-weight: 800; }
      .kpiLabel { font-size: 10px; color: #64748b; margin-top: 2px; }
      table { width: 100%; border-collapse: collapse; font-size: 10px; }
      th, td { border-top: 1px solid #e2e8f0; padding: 6px 0; text-align: left; vertical-align: top; }
      th { color: #64748b; font-weight: 700; border-top: none; padding-top: 0; }
      .pill { display: inline-block; padding: 2px 8px; border: 1px solid #cbd5e1; border-radius: 999px; font-size: 10px; color: #334155; }
      .hr { height: 1px; background: #e2e8f0; margin: 10px 0; }
      .sectionTitle { font-size: 11px; font-weight: 800; margin: 0 0 6px; }
      .sig { border: 1px solid #e2e8f0; border-radius: 10px; padding: 8px 10px; margin-top: 6px; }
      .sigHead { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
    </style>
  </head>
  <body>
    <div class="row" style="align-items:flex-start;">
      <div class="col">
        <h1 class="h1">${esc(title)}</h1>
        <div class="small muted" style="margin-top:4px;">
          AMFI ${schemeCode} · ${scheme?.category ? esc(String(scheme.category)) : "—"} · As of ${esc(asOf)}
        </div>
      </div>
      <div style="text-align:right;">
        <div class="pill">${esc(scheme?.risk_label ? String(scheme.risk_label) : "Risk N/A")}</div>
        <div class="small muted" style="margin-top:6px;">Generated: ${new Date().toISOString().replace("T"," ").slice(0,19)}Z</div>
      </div>
    </div>

    <div class="hr"></div>

    <div class="row">
      <div class="card col">
        <div class="kpi">${fmtNum(scheme?.latest_nav, 4)}</div>
        <div class="kpiLabel">Latest NAV (${scheme?.latest_nav_date ? esc(String(scheme.latest_nav_date)) : "—"})</div>
      </div>
      <div class="card col">
        <div class="kpi">${fmtPct(metrics?.day_change_pct)}</div>
        <div class="kpiLabel">Day change</div>
      </div>
      <div class="card col">
        <div class="kpi">${scheme?.expense_ratio != null ? fmtNum(scheme.expense_ratio, 2) + "%" : "—"}</div>
        <div class="kpiLabel">Expense ratio</div>
      </div>
      <div class="card col">
        <div class="kpi">${metrics?.is_52w_high ? "Yes" : "No"}</div>
        <div class="kpiLabel">52-week high</div>
      </div>
    </div>

    <div class="row" style="margin-top:12px;">
      <div class="card col">
        <div class="sectionTitle">Performance (Rolling)</div>
        <table>
          <thead><tr><th>Horizon</th><th>Return</th></tr></thead>
          <tbody>
            <tr><td>1W</td><td>${fmtPct(metrics?.ret_7d)}</td></tr>
            <tr><td>1M</td><td>${fmtPct(metrics?.ret_30d)}</td></tr>
            <tr><td>3M</td><td>${fmtPct(metrics?.ret_90d)}</td></tr>
            <tr><td>1Y</td><td>${fmtPct(metrics?.ret_365d)}</td></tr>
          </tbody>
        </table>
        <div class="small muted" style="margin-top:6px;">
          Note: returns require historical NAV; seed history for full coverage.
        </div>
      </div>

      <div class="card col">
        <div class="sectionTitle">Portfolio Snapshot</div>
        ${
          holdings
            ? `<div class="small muted">Family ${esc(String(scheme.family_id))} · Month ${esc(String(holdings.month))}</div>`
            : `<div class="small muted">No holdings snapshot yet. Run monthly holdings ingest.</div>`
        }
        <div style="margin-top:8px;">
          <table>
            <thead><tr><th>Holding</th><th style="text-align:right;">Weight</th></tr></thead>
            <tbody>
              ${
                topHoldings.length
                  ? topHoldings
                      .map(
                        (h: any) =>
                          `<tr><td>${esc(String(h.name))}</td><td style="text-align:right;">${h.weight_pct != null ? fmtNum(h.weight_pct, 2) + "%" : "—"}</td></tr>`
                      )
                      .join("")
                  : `<tr><td colspan="2" class="muted">No holdings available.</td></tr>`
              }
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="row" style="margin-top:12px;">
      <div class="card col">
        <div class="sectionTitle">Signals & Insights</div>
        ${
          signals.length
            ? signals
                .map(
                  (s: any) => `
                  <div class="sig">
                    <div class="sigHead">
                      <div style="font-weight:800; font-size:11px;">${esc(String(s.signal_type))}</div>
                      <div class="pill">${fmtNum(s.confidence_score, 0)}%</div>
                    </div>
                    <div class="small muted" style="margin-top:4px;">${s.nav_date ? "NAV date " + esc(String(s.nav_date)) : "Portfolio signal"}</div>
                    ${s.llm_analysis ? `<div class="small" style="margin-top:6px;">${esc(String(s.llm_analysis)).slice(0, 420)}</div>` : ""}
                  </div>
                `
                )
                .join("")
            : `<div class="small muted">No signals yet.</div>`
        }
      </div>
    </div>

    <div class="small muted" style="margin-top:10px;">
      Disclaimer: informational only. Not investment advice. Data sources: AMFI NAVAll.txt and mfdata.in (holdings/ratios, best-effort).
    </div>
  </body>
  </html>`;

  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1240, height: 1754 } });
    await page.setContent(html, { waitUntil: "load" });
    const pdf = await page.pdf({ format: "A4", printBackground: true });
    const filename = `MF_${schemeCode}_${asOf}.pdf`.replace(/[^a-zA-Z0-9_.-]/g, "_");
    const body = new Uint8Array(pdf);
    return new Response(body, {
      headers: {
        "Content-Type": "application/pdf",
        "Content-Disposition": `attachment; filename="${filename}"`,
        "Cache-Control": "no-store",
      },
    });
  } finally {
    await browser.close();
  }
}
