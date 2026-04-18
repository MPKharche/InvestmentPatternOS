"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { fetchCapabilities, fetchHealth, type Capabilities } from "@/lib/system";
import { mfApi } from "@/lib/api";

type Block = { title: string; ok: boolean | null; detail: string; action?: React.ReactNode };

function StatusBadge({ ok }: { ok: boolean | null }) {
  if (ok === null) return <Badge variant="secondary">Checking…</Badge>;
  if (ok) return <Badge className="bg-emerald-600/20 text-emerald-200 border-emerald-600/30">Ready</Badge>;
  return <Badge className="bg-red-600/20 text-red-200 border-red-600/30">Needs attention</Badge>;
}

export default function StatusPage() {
  const [healthOk, setHealthOk] = useState<boolean | null>(null);
  const [healthVersion, setHealthVersion] = useState<string | null>(null);
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [mfOk, setMfOk] = useState<boolean | null>(null);
  const [mfStats, setMfStats] = useState<{ monitored?: number; schemes?: number; nav_rows?: number } | null>(null);
  const [errors, setErrors] = useState<string[]>([]);

  useEffect(() => {
    let alive = true;
    const run = async () => {
      setErrors([]);
      try {
        const h = await fetchHealth();
        if (!alive) return;
        setHealthOk(h.status === "ok");
        setHealthVersion(h.version ?? null);
      } catch (e) {
        if (!alive) return;
        setHealthOk(false);
        setHealthVersion(null);
        setErrors((xs) => [...xs, e instanceof Error ? e.message : String(e)]);
      }
      try {
        const c = await fetchCapabilities();
        if (!alive) return;
        setCaps(c);
      } catch (e) {
        if (!alive) return;
        setCaps(null);
        setErrors((xs) => [...xs, e instanceof Error ? e.message : String(e)]);
      }
      try {
        const st = await mfApi.status();
        if (!alive) return;
        setMfOk(true);
        setMfStats({
          monitored: st.monitored_schemes,
          schemes: st.schemes_total,
          nav_rows: st.nav_rows_total,
        });
      } catch (e) {
        if (!alive) return;
        setMfOk(false);
        setErrors((xs) => [...xs, e instanceof Error ? e.message : String(e)]);
      }
    };
    run();
    return () => {
      alive = false;
    };
  }, []);

  const blocks: Block[] = [
    {
      title: "Connection",
      ok: healthOk,
      detail: healthOk ? `PatternOS is running. Version: ${healthVersion ?? "—"}` : "PatternOS is not reachable from this browser.",
      action: !healthOk ? (
        <div className="space-y-2">
          <div className="text-muted-foreground text-sm">
            If you’re running locally on Windows, start everything using:
          </div>
          <div className="font-mono text-xs bg-muted/40 border border-border rounded p-2">dev-up.bat (double-click)</div>
        </div>
      ) : null,
    },
    {
      title: "Mutual Funds data",
      ok: mfOk,
      detail: mfOk
        ? `Schemes: ${mfStats?.schemes ?? "—"} · Monitored: ${mfStats?.monitored ?? "—"} · NAV rows: ${mfStats?.nav_rows ?? "—"}`
        : "Mutual Funds module could not load status (database or service issue).",
    },
    {
      title: "AI (LLM)",
      ok: caps ? !caps.llm.disabled : null,
      detail: caps
        ? caps.llm.disabled
          ? "AI is turned off. You can still use scanning + pipelines; AI insights will be limited."
          : "AI is on. Pattern Studio and signal analysis will include AI insights."
        : "Checking…",
    },
    {
      title: "Telegram",
      ok: caps ? (caps.telegram.alerts_enabled && caps.telegram.bot_token_configured) : null,
      detail: caps
        ? caps.telegram.bot_token_configured
          ? `Alerts: ${caps.telegram.alerts_enabled ? "On" : "Off"} · Mode: ${caps.telegram.mode}`
          : "Telegram bot token is not configured yet."
        : "Checking…",
    },
    {
      title: "Optional quant engines",
      ok: caps ? true : null,
      detail: caps
        ? `TA‑Lib: ${caps.optional.talib ? "Enabled" : "Not installed"} · vectorbt: ${caps.optional.vectorbt ? "Enabled" : "Not installed"}`
        : "Checking…",
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">System Status</h1>
          <p className="text-sm text-muted-foreground">
            A simple readiness check. If something is off, you’ll see exactly how to fix it.
          </p>
        </div>
        <Button variant="outline" onClick={() => window.location.reload()}>
          Refresh
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {blocks.map((b) => (
          <Card key={b.title}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between gap-3">
                <CardTitle className="text-sm">{b.title}</CardTitle>
                <StatusBadge ok={b.ok} />
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="text-sm text-muted-foreground">{b.detail}</div>
              {b.action}
            </CardContent>
          </Card>
        ))}
      </div>

      {errors.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Details (for support)</CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground space-y-2">
            {errors.map((e, i) => (
              <div key={i} className="break-words">{e}</div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

