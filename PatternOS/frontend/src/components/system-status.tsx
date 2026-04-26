"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { fetchCapabilities, fetchHealth, type Capabilities } from "@/lib/system";
import { cn } from "@/lib/utils";

type Status = "checking" | "online" | "offline";

/** Health/capabilities polling: keep VPS + laptops calm (was 30s). */
const STATUS_PILL_POLL_MS = 120_000;
/** Offline banner probe (was 20s). */
const OFFLINE_BANNER_POLL_MS = 120_000;

export function SystemStatusPill() {
  const [status, setStatus] = useState<Status>("checking");
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [version, setVersion] = useState<string | null>(null);
  const [errorText, setErrorText] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const run = async () => {
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
      try {
        const [h, c] = await Promise.all([fetchHealth(), fetchCapabilities()]);
        if (!alive) return;
        setVersion(h.version ?? null);
        setCaps(c);
        setStatus("online");
        setErrorText(null);
      } catch (e) {
        if (!alive) return;
        setStatus("offline");
        setCaps(null);
        setErrorText(e instanceof Error ? e.message : String(e));
      }
    };
    run();
    const id = window.setInterval(run, STATUS_PILL_POLL_MS);
    const onVis = () => {
      if (document.visibilityState === "visible") void run();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      alive = false;
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  const badge = useMemo(() => {
    if (status === "checking") return <Badge variant="secondary">Checking…</Badge>;
    if (status === "online") return <Badge className="bg-emerald-600/20 text-emerald-200 border-emerald-600/30">Online</Badge>;
    return <Badge className="bg-red-600/20 text-red-200 border-red-600/30">Needs attention</Badge>;
  }, [status]);

  return (
    <Dialog>
      <DialogTrigger
        render={
          <Button variant="ghost" className="h-9 px-2 gap-2" title="System status">
            {badge}
          </Button>
        }
      />
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>System status</DialogTitle>
          <DialogDescription>
            This confirms PatternOS is connected and ready. No technical setup required on this screen.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 text-sm">
          <div className="flex items-center justify-between">
            <span>Connection</span>
            <span className="font-medium">{status === "online" ? "Online" : status === "offline" ? "Offline" : "Checking…"}</span>
          </div>
          <div className="flex items-center justify-between">
            <span>Version</span>
            <span className="font-medium">{version ?? "—"}</span>
          </div>
          <div className="flex items-center justify-between">
            <span>Charts (image)</span>
            <span className="font-medium">{caps?.optional?.mplfinance ? "Enabled" : "Enabled (core)"}</span>
          </div>
          <div className="flex items-center justify-between">
            <span>TA‑Lib (optional)</span>
            <span className="font-medium">{caps?.optional?.talib ? "Enabled" : "Not installed"}</span>
          </div>
          <div className="flex items-center justify-between">
            <span>vectorbt (optional)</span>
            <span className="font-medium">{caps?.optional?.vectorbt ? "Enabled" : "Not installed"}</span>
          </div>
          <div className="flex items-center justify-between">
            <span>Telegram alerts</span>
            <span className="font-medium">
              {caps ? (caps.telegram.alerts_enabled ? "On" : "Off") : "—"}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span>AI (LLM)</span>
            <span className="font-medium">
              {caps ? (caps.llm.disabled ? "Off" : "On") : "—"}
            </span>
          </div>

          {status === "offline" && (
            <div className="rounded-md border border-border bg-muted/40 p-3 space-y-2">
              <div className="font-medium">Fix</div>
              <div className="text-muted-foreground">
                PatternOS can’t reach its data service. If you’re running locally on Windows, start everything using:
              </div>
              <div className="font-mono text-xs bg-background/40 rounded p-2 border border-border">
                dev-up.bat (double-click)
              </div>
              <div className="text-muted-foreground text-xs break-words">
                {errorText ?? ""}
              </div>
            </div>
          )}

          <div className="flex gap-2 pt-2">
            <Link href="/status" className={cn(buttonVariants({ variant: "secondary" }), "flex-1 justify-center")}>
              Open full status
            </Link>
            <Button
              variant="outline"
              className="flex-1"
              onClick={() => window.location.reload()}
            >
              Refresh
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}


export function SystemOfflineBanner() {
  const [offline, setOffline] = useState(false);
  useEffect(() => {
    let alive = true;
    const run = async () => {
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
      try {
        await fetchCapabilities();
        if (!alive) return;
        setOffline(false);
      } catch {
        if (!alive) return;
        setOffline(true);
      }
    };
    run();
    const id = window.setInterval(run, OFFLINE_BANNER_POLL_MS);
    const onVis = () => {
      if (document.visibilityState === "visible") void run();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      alive = false;
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  if (!offline) return null;
  return (
    <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm flex items-center justify-between gap-3">
      <div className="text-red-100">
        We can’t load your data right now. PatternOS services may not be running.
      </div>
      <Link href="/status" className={cn(buttonVariants({ variant: "secondary", size: "sm" }), "justify-center")}>
        Fix
      </Link>
    </div>
  );
}
