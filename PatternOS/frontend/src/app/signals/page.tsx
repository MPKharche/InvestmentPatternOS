"use client";
import { useEffect, useState, useMemo } from "react";
import { signalsApi, patternsApi, type Signal, type Pattern } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ConfidenceBadge } from "@/components/confidence-badge";
import { ChartWidget } from "@/components/chart-widget";
import { toast } from "sonner";
import { RefreshCw, Sparkles } from "lucide-react";

const TABS = ["pending", "reviewed", "dismissed", "all"] as const;

type EquityNote = {
  stance?: string;
  headline?: string;
  body?: string;
  tags?: string[];
  sources?: { title?: string; url?: string }[];
  searx_used?: boolean;
  ddg_used?: boolean;
  crawl_used?: boolean;
};

function parseEquity(raw: unknown): EquityNote | null {
  if (!raw || typeof raw !== "object") return null;
  return raw as EquityNote;
}

function stanceColor(stance: string | undefined) {
  const s = (stance || "").toLowerCase();
  if (s.includes("construct")) return "text-emerald-400 border-emerald-500/40";
  if (s.includes("skept")) return "text-amber-400 border-amber-500/40";
  return "text-slate-300 border-border";
}

function fmtPct(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
}

function SignalCard({ signal, onAction }: { signal: Signal; onAction: () => void }) {
  const [open, setOpen] = useState(false);
  const [action, setAction] = useState<"executed" | "watching" | "skipped" | "dismissed">("executed");
  const [entry, setEntry] = useState(signal.key_levels?.entry?.toString() ?? "");
  const [sl, setSl] = useState(signal.key_levels?.stop_loss?.toString() ?? "");
  const [target, setTarget] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const eq = parseEquity(signal.equity_research_note);

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
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-bold text-base">{signal.symbol.replace(".NS", "")}</span>
              <Badge variant="outline" className="text-xs">{signal.exchange}</Badge>
              <Badge variant="outline" className="text-xs">{signal.timeframe}</Badge>
            </div>
            <ConfidenceBadge score={signal.confidence_score} />
          </div>
          <p className="text-xs text-muted-foreground">{signal.pattern_name} · {ago(signal.triggered_at)}</p>
        </CardHeader>
        <CardContent className="space-y-2">
          {eq?.headline && (
            <div className="flex items-start gap-2 rounded-md border border-violet-500/30 bg-violet-500/5 px-2 py-1.5">
              <Sparkles className="h-4 w-4 text-violet-400 shrink-0 mt-0.5" />
              <div className="min-w-0">
                <p className="text-[10px] font-semibold text-violet-300/90 uppercase tracking-wide">What AI thinks</p>
                <p className={`text-xs font-medium ${stanceColor(eq.stance)}`}>{eq.headline}</p>
              </div>
            </div>
          )}
          {signal.llm_analysis && (
            <p className="text-sm text-muted-foreground line-clamp-2">{signal.llm_analysis}</p>
          )}
          {signal.key_levels && (
            <div className="flex gap-4 text-xs flex-wrap">
              {signal.key_levels.entry && <span className="text-blue-400">Entry: {signal.key_levels.entry}</span>}
              {signal.key_levels.stop_loss && <span className="text-red-400">SL: {signal.key_levels.stop_loss}</span>}
              {signal.key_levels.resistance && <span className="text-yellow-400">R: {signal.key_levels.resistance}</span>}
            </div>
          )}
          {signal.forward_horizon_returns?.pct && (
            <div className="text-xs text-muted-foreground flex flex-wrap gap-3">
              <span>1w: {fmtPct(signal.forward_horizon_returns.pct["1w_5d"] as number)}</span>
              <span>1m: {fmtPct(signal.forward_horizon_returns.pct["1m_21d"] as number)}</span>
              <span>3m: {fmtPct(signal.forward_horizon_returns.pct["3m_63d"] as number)}</span>
              <span>6m: {fmtPct(signal.forward_horizon_returns.pct["6m_126d"] as number)}</span>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-3 flex-wrap">
              {signal.symbol.replace(".NS", "")}
              <ConfidenceBadge score={signal.confidence_score} />
              <span className="text-sm font-normal text-muted-foreground">{signal.pattern_name}</span>
            </DialogTitle>
          </DialogHeader>

          <ChartWidget symbol={signal.symbol} keyLevels={signal.key_levels} height={280} />

          {eq && (eq.headline || eq.body) && (
            <div className="rounded-lg border border-violet-500/35 bg-violet-950/20 p-3 space-y-2">
              <div className="flex items-center gap-2 text-violet-300">
                <Sparkles className="h-4 w-4" />
                <span className="text-sm font-semibold">What AI thinks</span>
                {eq.stance && (
                  <Badge variant="outline" className={`text-[10px] capitalize ${stanceColor(eq.stance)}`}>
                    {eq.stance}
                  </Badge>
                )}
                <span className="text-[10px] text-muted-foreground ml-auto">
                  {eq.searx_used ? "SearxNG " : ""}
                  {eq.ddg_used ? "DDG " : ""}
                  {eq.crawl_used ? "· Crawl4AI " : ""}
                </span>
              </div>
              {eq.headline && <p className="text-sm font-medium text-foreground">{eq.headline}</p>}
              {eq.body && <p className="text-sm text-muted-foreground whitespace-pre-wrap leading-relaxed">{eq.body}</p>}
              {eq.tags && eq.tags.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {eq.tags.map((t) => (
                    <Badge key={t} variant="secondary" className="text-[10px]">{t}</Badge>
                  ))}
                </div>
              )}
              {eq.sources && eq.sources.length > 0 && (
                <div className="text-[11px] space-y-1 border-t border-border/40 pt-2">
                  <p className="font-medium text-muted-foreground">Sources</p>
                  <ul className="list-disc pl-4 space-y-0.5 max-h-28 overflow-y-auto">
                    {eq.sources.map((s, i) => (
                      <li key={i}>
                        {s.url ? (
                          <a href={s.url} className="text-sky-400 hover:underline break-all" target="_blank" rel="noreferrer">
                            {s.title || s.url}
                          </a>
                        ) : (
                          <span>{s.title}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {signal.llm_analysis && (
            <div className="bg-muted/30 rounded p-3 text-sm">
              <p className="text-[10px] uppercase text-muted-foreground mb-1">Screener</p>
              {signal.llm_analysis}
            </div>
          )}

          <div className="space-y-3">
            <div className="flex gap-2 flex-wrap">
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
  const [patterns, setPatterns] = useState<Pattern[]>([]);
  const [tab, setTab] = useState<typeof TABS[number]>("pending");
  const [patternId, setPatternId] = useState<string>("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    patternsApi.list().then(setPatterns).catch(() => {});
  }, []);

  const load = async () => {
    setLoading(true);
    try {
      const pid = patternId === "all" ? undefined : patternId;
      const data = await signalsApi.list(tab, pid, 100);
      setSignals(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [tab, patternId]);

  const sorted = useMemo(
    () => [...signals].sort((a, b) => new Date(b.triggered_at).getTime() - new Date(a.triggered_at).getTime()),
    [signals]
  );

  return (
    <div className="space-y-4 max-w-4xl">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Signal Inbox</h1>
          <p className="text-muted-foreground text-sm max-w-xl">
            Cockpit for actionable setups across all active patterns. Each card shows screener context; open for chart,
            <span className="text-violet-300"> What AI thinks</span> (equity desk pass with optional news crawl), and review actions.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} className="shrink-0">
          <RefreshCw className="h-3 w-3 mr-1" /> Refresh
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Tabs value={tab} onValueChange={(v) => setTab(v as typeof tab)}>
          <TabsList>
            {TABS.map((t) => (
              <TabsTrigger key={t} value={t}>
                {t.charAt(0).toUpperCase() + t.slice(1)}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <Select value={patternId} onValueChange={(v) => { if (v) setPatternId(v); }}>
          <SelectTrigger className="w-[220px] h-9 text-xs">
            <SelectValue placeholder="Pattern" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all" className="text-xs">All patterns</SelectItem>
            {patterns.map((p) => (
              <SelectItem key={p.id} value={p.id} className="text-xs">
                {p.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {loading ? (
        <div className="text-muted-foreground text-sm">Loading signals...</div>
      ) : sorted.length === 0 ? (
        <div className="text-muted-foreground text-sm py-12 text-center">
          No {tab} signals for this filter. Run a scan from Pattern Studio (or wait for the scheduled scan).
        </div>
      ) : (
        <div className="grid gap-3">
          {sorted.map((s) => (
            <SignalCard key={s.id} signal={s} onAction={load} />
          ))}
        </div>
      )}
    </div>
  );
}
