"use client";
import { useEffect, useState } from "react";
import { outcomesApi, signalsApi, type Signal, type Outcome } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ConfidenceBadge } from "@/components/confidence-badge";
import { ChartWidget } from "@/components/chart-widget";
import { toast } from "sonner";

type TradeRow = {
  signal: Signal;
  outcome: Outcome | null;
};

const RESULT_COLORS: Record<string, string> = {
  hit_target: "text-green-400",
  stopped_out: "text-red-400",
  partial: "text-yellow-400",
  open: "text-blue-400",
  cancelled: "text-muted-foreground",
};

function OutcomeModal({
  signal,
  outcome,
  onClose,
  onSave,
}: {
  signal: Signal;
  outcome: Outcome | null;
  onClose: () => void;
  onSave: () => void;
}) {
  const [result, setResult] = useState(outcome?.result ?? "open");
  const [exitPrice, setExitPrice] = useState(outcome?.exit_price?.toString() ?? "");
  const [pnl, setPnl] = useState(outcome?.pnl_pct?.toString() ?? "");
  const [notes, setNotes] = useState(outcome?.notes ?? "");
  const [feedback, setFeedback] = useState(outcome?.feedback ?? "");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      await outcomesApi.create(signal.id, {
        result,
        exit_price: exitPrice ? +exitPrice : undefined,
        pnl_pct: pnl ? +pnl : undefined,
        notes: notes || undefined,
        feedback: feedback || undefined,
      });
      toast.success("Outcome saved");
      onSave();
      onClose();
    } catch {
      toast.error("Failed to save outcome");
    } finally {
      setSaving(false);
    }
  };

  return (
    <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2">
          {signal.symbol.replace(".NS", "")} — {signal.pattern_name}
          <ConfidenceBadge score={signal.confidence_score} />
        </DialogTitle>
      </DialogHeader>

      <ChartWidget symbol={signal.symbol} keyLevels={signal.key_levels} height={220} />

      <div className="space-y-3">
        <div>
          <Label className="text-xs">Result</Label>
          <Select value={result} onValueChange={(v) => { if (v) setResult(v); }}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {["hit_target", "stopped_out", "partial", "open", "cancelled"].map((r) => (
                <SelectItem key={r} value={r}>{r.replace("_", " ")}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label className="text-xs">Exit Price</Label>
            <Input value={exitPrice} onChange={(e) => setExitPrice(e.target.value)} placeholder="0.00" />
          </div>
          <div>
            <Label className="text-xs">P&L %</Label>
            <Input value={pnl} onChange={(e) => setPnl(e.target.value)} placeholder="+5.2 or -3.1" />
          </div>
        </div>

        <div>
          <Label className="text-xs">Notes</Label>
          <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} placeholder="What happened?" />
        </div>

        <div>
          <Label className="text-xs">Feedback for Pattern</Label>
          <Textarea
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            rows={2}
            placeholder="What should the LLM learn from this signal? (goes into learning log)"
          />
        </div>

        <Button className="w-full" onClick={save} disabled={saving}>
          {saving ? "Saving..." : "Save Outcome"}
        </Button>
      </div>
    </DialogContent>
  );
}

export default function JournalPage() {
  const [trades, setTrades] = useState<TradeRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<TradeRow | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const [signals, outcomes] = await Promise.all([
        signalsApi.list("reviewed", undefined, 200),
        outcomesApi.list(),
      ]);
      const outcomeMap = new Map(outcomes.map((o) => [o.signal_id, o]));
      setTrades(signals.map((s) => ({ signal: s, outcome: outcomeMap.get(s.id) ?? null })));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  if (loading) return <div className="text-muted-foreground text-sm">Loading journal...</div>;

  return (
    <div className="space-y-4 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold">Trade Journal</h1>
        <p className="text-muted-foreground text-sm">Track outcomes and feed learnings back into patterns</p>
      </div>

      {trades.length === 0 ? (
        <div className="text-muted-foreground text-sm py-12 text-center">
          No executed trades yet. Review signals from the Signal Inbox first.
        </div>
      ) : (
        <div className="rounded-md border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="text-left p-3 font-medium text-muted-foreground">Symbol</th>
                <th className="text-left p-3 font-medium text-muted-foreground">Pattern</th>
                <th className="text-left p-3 font-medium text-muted-foreground">Confidence</th>
                <th className="text-left p-3 font-medium text-muted-foreground">Result</th>
                <th className="text-left p-3 font-medium text-muted-foreground">P&L</th>
                <th className="text-right p-3 font-medium text-muted-foreground">Action</th>
              </tr>
            </thead>
            <tbody>
              {trades.map(({ signal, outcome }) => (
                <tr key={signal.id} className="border-b hover:bg-muted/20 transition-colors">
                  <td className="p-3 font-medium">{signal.symbol.replace(".NS", "")}</td>
                  <td className="p-3 text-muted-foreground">{signal.pattern_name}</td>
                  <td className="p-3"><ConfidenceBadge score={signal.confidence_score} /></td>
                  <td className="p-3">
                    {outcome?.result ? (
                      <span className={`font-medium ${RESULT_COLORS[outcome.result] ?? ""}`}>
                        {outcome.result.replace("_", " ")}
                      </span>
                    ) : (
                      <span className="text-muted-foreground text-xs">—</span>
                    )}
                  </td>
                  <td className="p-3">
                    {outcome?.pnl_pct != null ? (
                      <span className={outcome.pnl_pct >= 0 ? "text-green-400" : "text-red-400"}>
                        {outcome.pnl_pct > 0 ? "+" : ""}{outcome.pnl_pct.toFixed(2)}%
                      </span>
                    ) : (
                      <span className="text-muted-foreground text-xs">—</span>
                    )}
                  </td>
                  <td className="p-3 text-right">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setSelected({ signal, outcome })}
                    >
                      {outcome ? "Update" : "Add Outcome"}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Dialog open={!!selected} onOpenChange={(o) => { if (!o) setSelected(null); }}>
        {selected && (
          <OutcomeModal
            signal={selected.signal}
            outcome={selected.outcome}
            onClose={() => setSelected(null)}
            onSave={load}
          />
        )}
      </Dialog>
    </div>
  );
}
