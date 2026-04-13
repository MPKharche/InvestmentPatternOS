"use client";
import { useEffect, useState } from "react";
import { signalsApi, type Signal } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ConfidenceBadge } from "@/components/confidence-badge";
import { ChartWidget } from "@/components/chart-widget";
import { toast } from "sonner";
import { RefreshCw } from "lucide-react";

const TABS = ["pending", "reviewed", "dismissed", "all"] as const;

function SignalCard({ signal, onAction }: { signal: Signal; onAction: () => void }) {
  const [open, setOpen] = useState(false);
  const [action, setAction] = useState<"executed" | "watching" | "skipped" | "dismissed">("executed");
  const [entry, setEntry] = useState(signal.key_levels?.entry?.toString() ?? "");
  const [sl, setSl] = useState(signal.key_levels?.stop_loss?.toString() ?? "");
  const [target, setTarget] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleReview = async () => {
    setSubmitting(true);
    try {
      await signalsApi.review(signal.id, {
        action,
        entry_price: entry ? +entry : undefined,
        sl_price: sl ? +sl : undefined,
        target_price: target ? +target : undefined,
        notes: notes || undefined,
      });
      toast.success(`Signal marked as ${action}`);
      setOpen(false);
      onAction();
    } catch {
      toast.error("Failed to submit review");
    } finally {
      setSubmitting(false);
    }
  };

  const ago = (dateStr: string) => {
    const ms = Date.now() - new Date(dateStr).getTime();
    const h = Math.floor(ms / 3600000);
    return h < 24 ? `${h}h ago` : `${Math.floor(h / 24)}d ago`;
  };

  return (
    <>
      <Card
        className="cursor-pointer hover:border-primary/50 transition-colors"
        onClick={() => setOpen(true)}
      >
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="font-bold text-base">{signal.symbol.replace(".NS", "")}</span>
              <Badge variant="outline" className="text-xs">{signal.exchange}</Badge>
              <Badge variant="outline" className="text-xs">{signal.timeframe}</Badge>
            </div>
            <ConfidenceBadge score={signal.confidence_score} />
          </div>
          <p className="text-xs text-muted-foreground">{signal.pattern_name} · {ago(signal.triggered_at)}</p>
        </CardHeader>
        <CardContent>
          {signal.llm_analysis && (
            <p className="text-sm text-muted-foreground line-clamp-2">{signal.llm_analysis}</p>
          )}
          {signal.key_levels && (
            <div className="flex gap-4 mt-2 text-xs">
              {signal.key_levels.entry && <span className="text-blue-400">Entry: {signal.key_levels.entry}</span>}
              {signal.key_levels.stop_loss && <span className="text-red-400">SL: {signal.key_levels.stop_loss}</span>}
              {signal.key_levels.resistance && <span className="text-yellow-400">R: {signal.key_levels.resistance}</span>}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-3">
              {signal.symbol.replace(".NS", "")}
              <ConfidenceBadge score={signal.confidence_score} />
              <span className="text-sm font-normal text-muted-foreground">{signal.pattern_name}</span>
            </DialogTitle>
          </DialogHeader>

          <ChartWidget symbol={signal.symbol} keyLevels={signal.key_levels} height={280} />

          {signal.llm_analysis && (
            <div className="bg-muted/30 rounded p-3 text-sm">{signal.llm_analysis}</div>
          )}

          <div className="space-y-3">
            <div className="flex gap-2">
              {(["executed", "watching", "skipped", "dismissed"] as const).map((a) => (
                <Button
                  key={a}
                  size="sm"
                  variant={action === a ? "default" : "outline"}
                  onClick={() => setAction(a)}
                >
                  {a.charAt(0).toUpperCase() + a.slice(1)}
                </Button>
              ))}
            </div>

            {action === "executed" && (
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <Label className="text-xs">Entry Price</Label>
                  <Input value={entry} onChange={(e) => setEntry(e.target.value)} placeholder="0.00" />
                </div>
                <div>
                  <Label className="text-xs">Stop Loss</Label>
                  <Input value={sl} onChange={(e) => setSl(e.target.value)} placeholder="0.00" />
                </div>
                <div>
                  <Label className="text-xs">Target</Label>
                  <Input value={target} onChange={(e) => setTarget(e.target.value)} placeholder="0.00" />
                </div>
              </div>
            )}

            <div>
              <Label className="text-xs">Notes</Label>
              <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} placeholder="Optional notes..." />
            </div>

            <Button className="w-full" onClick={handleReview} disabled={submitting}>
              {submitting ? "Submitting..." : "Submit Review"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

export default function SignalsPage() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [tab, setTab] = useState<typeof TABS[number]>("pending");
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const data = await signalsApi.list(tab, undefined, 100);
      setSignals(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [tab]);

  return (
    <div className="space-y-4 max-w-4xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Signal Inbox</h1>
          <p className="text-muted-foreground text-sm">High-confidence pattern signals awaiting review</p>
        </div>
        <Button variant="outline" size="sm" onClick={load}>
          <RefreshCw className="h-3 w-3 mr-1" /> Refresh
        </Button>
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v as typeof tab)}>
        <TabsList>
          {TABS.map((t) => <TabsTrigger key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</TabsTrigger>)}
        </TabsList>
      </Tabs>

      {loading ? (
        <div className="text-muted-foreground text-sm">Loading signals...</div>
      ) : signals.length === 0 ? (
        <div className="text-muted-foreground text-sm py-12 text-center">
          No {tab} signals. Run a scan from Pattern Studio to generate signals.
        </div>
      ) : (
        <div className="grid gap-3">
          {signals.map((s) => <SignalCard key={s.id} signal={s} onAction={load} />)}
        </div>
      )}
    </div>
  );
}
