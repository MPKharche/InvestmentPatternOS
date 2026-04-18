"use client";

import { useEffect, useState } from "react";
import { mfApi, type MFIngestionStatus } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import Link from "next/link";
import { RefreshCw } from "lucide-react";

export default function MFDashboardPage() {
  const [status, setStatus] = useState<MFIngestionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [runningNav, setRunningNav] = useState(false);
  const [runningHoldings, setRunningHoldings] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const s = await mfApi.status();
      setStatus(s);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to load MF status");
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
      const r = await mfApi.runNav();
      toast.success(`NAV ingest OK (${r.stats?.rows_parsed ?? "?"} rows)`);
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "NAV ingest failed");
    } finally {
      setRunningNav(false);
    }
  };

  const runHoldings = async () => {
    setRunningHoldings(true);
    try {
      const r = await mfApi.runHoldings();
      toast.success(`Holdings ingest OK (${r.stats?.families ?? "?"} families)`);
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Holdings ingest failed");
    } finally {
      setRunningHoldings(false);
    }
  };

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Mutual Funds</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Daily NAV pipeline (AMFI) + monthly portfolio enrichment (mfdata.in) + rulebook signals.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className="h-3 w-3 mr-1" /> Refresh
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">Monitored</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-bold">
            {status?.monitored_schemes ?? (loading ? "…" : 0)}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">Schemes</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-bold">
            {status?.schemes_total ?? (loading ? "…" : 0)}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">NAV Rows</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-bold">
            {status?.nav_rows_total ?? (loading ? "…" : 0)}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">Pending Signals</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-bold">
            {status?.signals_pending ?? (loading ? "…" : 0)}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Pipelines</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col md:flex-row md:items-center gap-3">
          <Button onClick={runNav} disabled={runningNav}>
            {runningNav ? "Running…" : "Run Daily NAV Ingest"}
          </Button>
          <Button variant="secondary" onClick={runHoldings} disabled={runningHoldings}>
            {runningHoldings ? "Running…" : "Run Monthly Holdings Ingest"}
          </Button>
          <div className="text-xs text-muted-foreground md:ml-auto">
            Default schedules: NAV 18:30 IST daily · Holdings 7th/10th 19:00 IST.
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center gap-2">
        <Link href="/mf/schemes">
          <Button variant="outline" size="sm">Schemes</Button>
        </Link>
        <Link href="/mf/signals">
          <Button variant="outline" size="sm">
            Signals {status?.signals_pending ? <Badge className="ml-2">{status.signals_pending}</Badge> : null}
          </Button>
        </Link>
        <Link href="/mf/rulebooks">
          <Button variant="outline" size="sm">Rulebooks</Button>
        </Link>
        <Link href="/mf/pipelines">
          <Button variant="outline" size="sm">Runs</Button>
        </Link>
      </div>
    </div>
  );
}

