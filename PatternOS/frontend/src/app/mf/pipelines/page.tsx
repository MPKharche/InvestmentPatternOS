"use client";

import { useEffect, useState } from "react";
import { mfApi, type MFIngestionStatus } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { RefreshCw } from "lucide-react";

export default function MFPipelinesPage() {
  const [status, setStatus] = useState<MFIngestionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [runningNav, setRunningNav] = useState(false);
  const [runningSyncWatchlist, setRunningSyncWatchlist] = useState(false);
  const [runningHoldings, setRunningHoldings] = useState(false);
  const [runningHoldingsBootstrap, setRunningHoldingsBootstrap] = useState(false);
  const [runningBackfill, setRunningBackfill] = useState(false);
  const [runningLinkCheck, setRunningLinkCheck] = useState(false);
  const [runningGapfill, setRunningGapfill] = useState(false);
  const [quality, setQuality] = useState<any>(null);
  const [loadingQuality, setLoadingQuality] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      setStatus(await mfApi.status());
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const runNav = async () => {
    setRunningNav(true);
    try {
      const res = await mfApi.runNav();
      toast.success(`NAV run ok (${res.stats?.rows_parsed ?? "?"} rows)`);
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "NAV run failed");
    } finally {
      setRunningNav(false);
    }
  };

  const syncPriorityAmcWatchlist = async () => {
    setRunningSyncWatchlist(true);
    try {
      const res = await mfApi.syncPriorityAmcWatchlist();
      const st = res.stats as { promoted?: number; demoted?: number } | undefined;
      toast.success(
        `Watchlist synced${st != null ? ` (+${st.promoted ?? 0} promoted, −${st.demoted ?? 0} demoted)` : ""}`
      );
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Watchlist sync failed");
    } finally {
      setRunningSyncWatchlist(false);
    }
  };

  const runHoldings = async () => {
    setRunningHoldings(true);
    try {
      const res = await mfApi.runHoldings();
      toast.success(`Holdings run ok (${res.stats?.families ?? "?"} families)`);
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Holdings run failed");
    } finally {
      setRunningHoldings(false);
    }
  };

  const runHoldingsBootstrap = async () => {
    setRunningHoldingsBootstrap(true);
    try {
      const res = await mfApi.runHoldingsBootstrap();
      toast.success(`Holdings bootstrap ok (${res.stats?.snapshots ?? "?"} snapshots)`);
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Holdings bootstrap failed");
    } finally {
      setRunningHoldingsBootstrap(false);
    }
  };

  const runBackfill = async () => {
    setRunningBackfill(true);
    try {
      const res = await mfApi.runBackfill();
      const msg = res.stats?.skipped ? `Backfill skipped (${res.stats?.reason ?? "disabled"})` : `Backfill ok (${res.stats?.rows_inserted ?? "?"} rows)`;
      toast.success(msg);
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Backfill failed");
    } finally {
      setRunningBackfill(false);
    }
  };

  const runGapfill = async () => {
    setRunningGapfill(true);
    try {
      const res = await mfApi.runNavGapfill();
      toast.success(`Gap-fill ok (${res.stats?.inserted ?? "?"} rows)`);
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Gap-fill failed");
    } finally {
      setRunningGapfill(false);
    }
  };

  const pause = async (provider: string, minutes = 60) => {
    try {
      await mfApi.pauseProvider(provider, { minutes, reason: "Manual pause from UI" });
      toast.success(`Paused ${provider} for ${minutes}m`);
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : `Failed to pause ${provider}`);
    }
  };

  const checkLinks = async () => {
    setRunningLinkCheck(true);
    try {
      const res = await mfApi.checkLinks();
      const msg = res.stats?.skipped ? `Link check skipped (${res.stats?.reason ?? "disabled"})` : `Link check ok (${res.stats?.checked ?? "?"} schemes)`;
      toast.success(msg);
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Link check failed");
    } finally {
      setRunningLinkCheck(false);
    }
  };

  const loadQuality = async () => {
    setLoadingQuality(true);
    try {
      const q = await mfApi.navQuality({ monitored_only: true, gap_days: 10, limit: 200 });
      setQuality(q);
      toast.success("Quality loaded");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to load quality");
    } finally {
      setLoadingQuality(false);
    }
  };

  const resume = async (provider: string) => {
    try {
      await mfApi.resumeProvider(provider);
      toast.success(`Resumed ${provider}`);
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : `Failed to resume ${provider}`);
    }
  };

  return (
    <div className="space-y-4 max-w-5xl">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">MF Pipeline Runs</h1>
          <p className="text-muted-foreground text-sm mt-1">Latest ingestion run metadata + manual triggers.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className="h-3 w-3 mr-1" /> Refresh
          </Button>
          <Button size="sm" variant="secondary" onClick={syncPriorityAmcWatchlist} disabled={runningSyncWatchlist}>
            Sync priority AMC watchlist
          </Button>
          <Button size="sm" onClick={runNav} disabled={runningNav}>
            Run NAV now
          </Button>
          <Button size="sm" variant="secondary" onClick={runHoldings} disabled={runningHoldings}>
            Run holdings now
          </Button>
          <Button size="sm" variant="outline" onClick={runHoldingsBootstrap} disabled={runningHoldingsBootstrap}>
            Bootstrap holdings (12M)
          </Button>
          <Button size="sm" variant="outline" onClick={runGapfill} disabled={runningGapfill}>
            Gap-fill NAV (mfdata)
          </Button>
          <Button size="sm" variant="outline" onClick={runBackfill} disabled={runningBackfill}>
            Backfill (MFAPI)
          </Button>
          <Button size="sm" variant="outline" onClick={checkLinks} disabled={runningLinkCheck}>
            Check links
          </Button>
          <Button size="sm" variant="outline" onClick={loadQuality} disabled={loadingQuality}>
            Load quality
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">After a full historical seed</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground space-y-2">
          <p>
            One-time parquet load: run <code className="text-xs bg-muted px-1 rounded">backend/scripts/mf_seed_historical.py</code>{" "}
            with <code className="text-xs bg-muted px-1 rounded">--kaggle-dir</code> or set{" "}
            <code className="text-xs bg-muted px-1 rounded">MF_KAGGLE_DATA_DIR</code> (see script docstring and <code className="text-xs bg-muted px-1 rounded">.env.example</code>).
            NAV rows are idempotent (<code className="text-xs bg-muted px-1 rounded">ON CONFLICT DO NOTHING</code>).
          </p>
          <p>
            Then use <strong>Sync priority AMC watchlist</strong> above, then <strong>Run NAV now</strong> (same order as{" "}
            <code className="text-xs bg-muted px-1 rounded">POST /api/v1/mf/pipeline/watchlist/sync-priority-amc</code> and{" "}
            <code className="text-xs bg-muted px-1 rounded">POST /api/v1/mf/pipeline/nav/run</code>).
          </p>
          <p>
            <strong>Prod</strong>: aim <code className="text-xs bg-muted px-1 rounded">POSTGRES_*</code> at the live DB (or SSH tunnel), run the seed, then the two actions above. Scheme pages show{" "}
            <code className="text-xs bg-muted px-1 rounded">nav_days_in_db</code> — if it stays ~1 after seed, that AMFI code may be absent from your parquet or the seed did not run against this DB.
          </p>
          <p className="text-xs font-mono bg-muted/50 rounded p-2 overflow-x-auto">
            SELECT COUNT(*), MIN(nav_date), MAX(nav_date) FROM mf_nav_daily WHERE scheme_code = 147541;
          </p>
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs">Monitored</CardTitle>
          </CardHeader>
          <CardContent className="text-xl font-semibold">{status?.monitored_schemes ?? "—"}</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs">Schemes</CardTitle>
          </CardHeader>
          <CardContent className="text-xl font-semibold">{status?.schemes_total ?? "—"}</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs">NAV Rows</CardTitle>
          </CardHeader>
          <CardContent className="text-xl font-semibold">{status?.nav_rows_total ?? "—"}</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs">Pending Signals</CardTitle>
          </CardHeader>
          <CardContent className="text-xl font-semibold">{status?.signals_pending ?? "—"}</CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Latest NAV Run</CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground space-y-1">
            {status?.latest_nav_run ? (
              <>
                <div>Status: {status.latest_nav_run.status}</div>
                <div>Started: {status.latest_nav_run.started_at}</div>
                <div>Finished: {status.latest_nav_run.finished_at ?? "—"}</div>
              </>
            ) : (
              <>
                <div>Status: —</div>
                <div className="opacity-80">No NAV ingestion run recorded yet.</div>
              </>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Latest Holdings Run</CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground space-y-1">
            {status?.latest_holdings_run ? (
              <>
                <div>Status: {status.latest_holdings_run.status}</div>
                <div>Started: {status.latest_holdings_run.started_at}</div>
                <div>Finished: {status.latest_holdings_run.finished_at ?? "—"}</div>
              </>
            ) : (
              <>
                <div>Status: —</div>
                <div className="opacity-80">No holdings ingestion run recorded yet.</div>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Provider Safety (Circuit Breakers)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {!status?.providers?.length ? (
            <div className="text-sm text-muted-foreground">No provider state available yet.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-[760px] w-full text-sm">
                <thead>
                  <tr className="text-xs text-muted-foreground">
                    <th className="text-left py-2 pr-3">Provider</th>
                    <th className="text-left py-2 pr-3">Paused Until</th>
                    <th className="text-right py-2 pr-3">Failures</th>
                    <th className="text-left py-2 pr-3">Last Error</th>
                    <th className="text-right py-2">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {status.providers.map((p) => (
                    <tr key={p.provider} className="border-t border-border/60">
                      <td className="py-2 pr-3 font-medium">{p.provider}</td>
                      <td className="py-2 pr-3 text-xs text-muted-foreground">{p.paused_until ?? "—"}</td>
                      <td className="py-2 pr-3 text-right text-xs text-muted-foreground">{p.consecutive_failures ?? 0}</td>
                      <td className="py-2 pr-3 text-xs text-muted-foreground truncate max-w-[360px]">{p.last_error ?? "—"}</td>
                      <td className="py-2 text-right">
                        <div className="inline-flex gap-2">
                          <Button size="sm" variant="outline" onClick={() => pause(p.provider, 60)}>
                            Pause 60m
                          </Button>
                          <Button size="sm" variant="secondary" onClick={() => resume(p.provider)}>
                            Resume
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">NAV Coverage & Quality</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {!quality ? (
            <div className="text-sm text-muted-foreground">Load quality to see earliest/latest coverage and gap checks (monitored only).</div>
          ) : (
            <>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                <div className="rounded-lg border border-border p-3">
                  <div className="text-xs text-muted-foreground">Latest AMFI date</div>
                  <div className="text-sm font-semibold mt-1">{quality.latest_amfi_date ?? "—"}</div>
                </div>
                <div className="rounded-lg border border-border p-3">
                  <div className="text-xs text-muted-foreground">% updated on latest</div>
                  <div className="text-sm font-semibold mt-1">
                    {quality.pct_schemes_updated_on_latest_amfi != null ? `${Number(quality.pct_schemes_updated_on_latest_amfi).toFixed(1)}%` : "—"}
                  </div>
                </div>
                <div className="rounded-lg border border-border p-3">
                  <div className="text-xs text-muted-foreground">Zero-NAV schemes</div>
                  <div className="text-sm font-semibold mt-1">{quality.zero_nav_schemes ?? "—"}</div>
                </div>
                <div className="rounded-lg border border-border p-3">
                  <div className="text-xs text-muted-foreground">Gap threshold</div>
                  <div className="text-sm font-semibold mt-1">{quality.gap_days ?? 10}d</div>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="min-w-[980px] w-full text-sm">
                  <thead>
                    <tr className="text-xs text-muted-foreground">
                      <th className="text-left py-2 pr-3">Scheme</th>
                      <th className="text-left py-2 pr-3">AMC</th>
                      <th className="text-left py-2 pr-3">Earliest</th>
                      <th className="text-left py-2 pr-3">Latest</th>
                      <th className="text-right py-2 pr-3">Rows</th>
                      <th className="text-right py-2 pr-3">Max gap (d)</th>
                      <th className="text-right py-2">Gaps &gt; threshold</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(quality.rows ?? []).map((r: any) => (
                      <tr key={String(r.scheme_code)} className="border-t border-border/60">
                        <td className="py-2 pr-3">
                          <div className="font-medium">{r.scheme_name ?? `Scheme ${r.scheme_code}`}</div>
                          <div className="text-xs text-muted-foreground">AMFI {r.scheme_code}</div>
                        </td>
                        <td className="py-2 pr-3 text-xs text-muted-foreground">{r.amc_name ?? "—"}</td>
                        <td className="py-2 pr-3 text-xs text-muted-foreground">{r.min_date ?? "—"}</td>
                        <td className="py-2 pr-3 text-xs text-muted-foreground">{r.max_date ?? "—"}</td>
                        <td className="py-2 pr-3 text-right text-xs text-muted-foreground">{r.rows ?? "—"}</td>
                        <td className="py-2 pr-3 text-right text-xs text-muted-foreground">{r.max_gap_days ?? "—"}</td>
                        <td className="py-2 text-right text-xs text-muted-foreground">{r.gaps_gt ?? "—"}</td>
                      </tr>
                    ))}
                    {!(quality.rows ?? []).length && (
                      <tr><td colSpan={7} className="py-6 text-center text-sm text-muted-foreground">No data.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
