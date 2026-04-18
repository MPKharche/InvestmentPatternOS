"use client";

import { useEffect, useMemo, useState } from "react";
import { mfApi, type MFSignal } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";
import Link from "next/link";
import { RefreshCw } from "lucide-react";

const TABS = ["pending", "reviewed", "dismissed", "all"] as const;

export default function MFSignalsPage() {
  const [tab, setTab] = useState<typeof TABS[number]>("pending");
  const [signals, setSignals] = useState<MFSignal[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const rows = await mfApi.signals(tab, 300);
      setSignals(rows);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to load MF signals");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const sorted = useMemo(() => {
    return [...signals].sort((a, b) => new Date(b.triggered_at).getTime() - new Date(a.triggered_at).getTime());
  }, [signals]);

  const review = async (id: string, action: string) => {
    try {
      await mfApi.reviewSignal(id, { action });
      toast.success("Updated");
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Update failed");
    }
  };

  return (
    <div className="space-y-4 max-w-5xl">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">MF Signals</h1>
          <p className="text-muted-foreground text-sm mt-1">Inbox for monitored scheme + portfolio alerts.</p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className="h-3 w-3 mr-1" /> Refresh
        </Button>
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v as typeof tab)}>
        <TabsList>
          {TABS.map((t) => (
            <TabsTrigger key={t} value={t}>
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      <div className="grid grid-cols-1 gap-3">
        {sorted.map((s) => (
          <Card key={s.id}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center justify-between gap-2">
                <Link href={`/mf/schemes/${s.scheme_code}`} className="hover:underline truncate">
                  {s.scheme_name ?? `Scheme ${s.scheme_code}`}
                </Link>
                <Badge variant="outline">{s.confidence_score.toFixed(0)}%</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="text-xs text-muted-foreground">
                <span className="font-medium text-foreground/80">{s.signal_type}</span>
                {" · "}
                {s.nav_date ? `NAV date ${s.nav_date}` : "Portfolio signal"}
              </div>
              {s.llm_analysis ? (
                <div className="text-xs text-muted-foreground">{s.llm_analysis}</div>
              ) : null}
              <div className="flex flex-wrap gap-2 pt-1">
                <Button size="xs" variant="outline" onClick={() => review(s.id, "reviewed")}>Mark reviewed</Button>
                <Button size="xs" variant="outline" onClick={() => review(s.id, "dismissed")}>Dismiss</Button>
                <Button size="xs" variant="secondary" onClick={() => review(s.id, "acted")}>Acted</Button>
              </div>
            </CardContent>
          </Card>
        ))}
        {!sorted.length && (
          <div className="text-sm text-muted-foreground text-center py-10">
            {loading ? "Loading…" : "No signals."}
          </div>
        )}
      </div>
    </div>
  );
}

