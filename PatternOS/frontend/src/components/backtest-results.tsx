"use client";
import { useEffect, useState, useCallback, useMemo } from "react";
import type { PatternEvent, BacktestRun, PatternVersion } from "@/lib/api";
import { studioApi, patternsApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Loader2, Search } from "lucide-react";
import { BacktestSymbolTable } from "./backtest-symbol-table";
import { BacktestEventsTable } from "./backtest-events-table";
import { EventChartDialog } from "./event-chart-dialog";
import {
  type PatternDirection,
  inferDirectionFromRulebook,
  strategyPnlPct,
  fmtCompactPct,
  fmtPnlColor,
  avg,
} from "@/lib/pattern-pnl";

export interface BacktestSymbolStats {
  symbol: string;
  count: number;
  success: number;
  failure: number;
  neutral?: number;
  avgPnl1w?: number | null;
  avgPnl1m?: number | null;
  avgPnl3m?: number | null;
}

interface BacktestResultsProps {
  patternId: string;
  run: BacktestRun;
  onEventFeedback?: (id: string, feedback: string, notes: string) => void;
}

/** Load every event for a backtest run (paginated on the server). */
async function fetchAllRunEvents(patternId: string, runId: string): Promise<PatternEvent[]> {
  const acc: PatternEvent[] = [];
  const page = 200;
  let offset = 0;
  for (;;) {
    const res = await studioApi.getEvents(patternId, {
      backtest_run_id: runId,
      limit: page,
      offset,
    });
    acc.push(...res.events);
    if (res.events.length < page || acc.length >= res.total) break;
    offset += res.events.length;
  }
  return acc;
}

export function BacktestResults({ patternId, run, onEventFeedback }: BacktestResultsProps) {
  const [runEvents, setRunEvents] = useState<PatternEvent[]>([]);
  const [runEventsLoading, setRunEventsLoading] = useState(false);
  const [symbolFilter, setSymbolFilter] = useState("");
  const [symbolStats, setSymbolStats] = useState<BacktestSymbolStats[]>([]);
  const [viewMode, setViewMode] = useState<"symbols" | "list">("symbols");
  const [direction, setDirection] = useState<PatternDirection>("unknown");
  const [chartEvent, setChartEvent] = useState<PatternEvent | null>(null);
  const [chartOpen, setChartOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const vers = await patternsApi.versions(patternId);
        const top = [...vers].sort((a, b) => b.version - a.version)[0] as PatternVersion | undefined;
        if (!cancelled && top?.rulebook_json) {
          setDirection(inferDirectionFromRulebook(top.rulebook_json as Record<string, unknown>));
        }
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [patternId]);

  const loadRunEvents = useCallback(async () => {
    if (!patternId || !run.id) return;
    setRunEventsLoading(true);
    try {
      const all = await fetchAllRunEvents(patternId, run.id);
      setRunEvents(all);
    } catch (e) {
      console.error("Failed to load run events", e);
      setRunEvents([]);
    } finally {
      setRunEventsLoading(false);
    }
  }, [patternId, run.id]);

  useEffect(() => {
    void loadRunEvents();
  }, [loadRunEvents]);

  const rollup = useMemo(() => {
    const ev = runEvents;
    const p1w = avg(ev.map((e) => strategyPnlPct(direction, e.ret_5d)));
    const p1m = avg(ev.map((e) => strategyPnlPct(direction, e.ret_21d)));
    const p3m = avg(ev.map((e) => strategyPnlPct(direction, e.ret_63d)));
    return { p1w, p1m, p3m, n: ev.length };
  }, [runEvents, direction]);

  useEffect(() => {
    const dir = direction;
    const map: Record<
      string,
      BacktestSymbolStats & { _s5: number[]; _s21: number[]; _s63: number[] }
    > = {};
    for (const e of runEvents) {
      if (!map[e.symbol]) {
        map[e.symbol] = {
          symbol: e.symbol,
          count: 0,
          success: 0,
          failure: 0,
          neutral: 0,
          _s5: [],
          _s21: [],
          _s63: [],
        };
      }
      const m = map[e.symbol];
      m.count++;
      if (e.outcome === "success") m.success++;
      else if (e.outcome === "failure") m.failure++;
      else if (e.outcome === "neutral") m.neutral = (m.neutral ?? 0) + 1;
      const a = strategyPnlPct(dir, e.ret_5d);
      const b = strategyPnlPct(dir, e.ret_21d);
      const c = strategyPnlPct(dir, e.ret_63d);
      if (a != null) m._s5.push(a);
      if (b != null) m._s21.push(b);
      if (c != null) m._s63.push(c);
    }
    const sorted = Object.values(map)
      .map(({ _s5, _s21, _s63, ...rest }) => ({
        ...rest,
        avgPnl1w: _s5.length ? _s5.reduce((x, y) => x + y, 0) / _s5.length : null,
        avgPnl1m: _s21.length ? _s21.reduce((x, y) => x + y, 0) / _s21.length : null,
        avgPnl3m: _s63.length ? _s63.reduce((x, y) => x + y, 0) / _s63.length : null,
      }))
      .sort((a, b) => b.count - a.count);
    setSymbolStats(sorted);
  }, [runEvents, direction]);

  const listForTable = useMemo(() => {
    const q = symbolFilter.trim().toUpperCase();
    let ev = runEvents;
    if (q) ev = ev.filter((e) => e.symbol.toUpperCase().includes(q));
    return [...ev].sort(
      (a, b) => new Date(b.detected_at).getTime() - new Date(a.detected_at).getTime()
    );
  }, [runEvents, symbolFilter]);

  const handleFeedback = async (id: string, feedback: string, notes: string) => {
    try {
      await studioApi.updateEventFeedback(id, feedback, notes);
      setRunEvents((prev) =>
        prev.map((e) => (e.id === id ? { ...e, user_feedback: feedback, user_notes: notes } : e))
      );
      onEventFeedback?.(id, feedback, notes);
    } catch (e) {
      console.error("Failed to update event feedback", e);
    }
  };

  const handleSymbolClick = (symbol: string) => {
    setSymbolFilter(symbol);
    setViewMode("list");
  };

  return (
    <div className="space-y-3 border-t border-border/40 pt-3">
      <Card className="border-primary/20 bg-muted/20">
        <CardHeader className="py-2 pb-1">
          <CardTitle className="text-xs font-semibold">Run totals (strategy P&amp;L %, this run)</CardTitle>
        </CardHeader>
        <CardContent className="pt-0 pb-2">
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] font-mono tabular-nums">
            <span>
              Events: <strong>{run.events_found ?? rollup.n}</strong>
              {rollup.n !== (run.events_found ?? rollup.n) && (
                <span className="text-muted-foreground"> (loaded {rollup.n})</span>
              )}
            </span>
            <span>
              Success rate:{" "}
              <strong
                className={
                  run.success_rate != null && run.success_rate >= 50 ? "text-green-400" : "text-red-400"
                }
              >
                {run.success_rate?.toFixed(1) ?? "—"}%
              </strong>
            </span>
            <span className={fmtPnlColor(direction, rollup.p1w)}>
              Avg 1w P&amp;L: {fmtCompactPct(rollup.p1w, 2)}
            </span>
            <span className={fmtPnlColor(direction, rollup.p1m)}>
              Avg ~1m P&amp;L: {fmtCompactPct(rollup.p1m, 2)}
            </span>
            <span className={fmtPnlColor(direction, rollup.p3m)}>
              Avg ~3m P&amp;L: {fmtCompactPct(rollup.p3m, 2)}
            </span>
            <span className="text-muted-foreground text-[10px]">
              Bearish: down move = profit (green). Bullish: up = profit.
            </span>
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-2 items-center">
        <span className="text-[10px] font-semibold text-muted-foreground">View:</span>
        <Button
          size="sm"
          variant={viewMode === "symbols" ? "default" : "outline"}
          onClick={() => setViewMode("symbols")}
          className="text-[10px] h-7 px-2"
        >
          By Symbol
        </Button>
        <Button
          size="sm"
          variant={viewMode === "list" ? "default" : "outline"}
          onClick={() => setViewMode("list")}
          className="text-[10px] h-7 px-2"
        >
          Detailed Events
        </Button>
        {symbolFilter && (
          <Button size="sm" variant="ghost" onClick={() => setSymbolFilter("")} className="text-[10px] h-7 ml-auto">
            Clear ({symbolFilter})
          </Button>
        )}
      </div>

      {viewMode === "symbols" && (
        <BacktestSymbolTable data={symbolStats} direction={direction} onSymbolClick={handleSymbolClick} />
      )}

      {viewMode === "list" && (
        <>
          <div className="flex gap-2">
            <div className="flex-1 relative">
              <Search className="absolute left-2 top-1.5 h-3.5 w-3.5 text-muted-foreground" />
              <input
                type="text"
                placeholder="Filter symbol…"
                value={symbolFilter}
                onChange={(e) => setSymbolFilter(e.target.value.toUpperCase())}
                className="w-full h-8 rounded border border-border bg-muted pl-7 pr-2 text-[11px] focus:outline-none"
              />
            </div>
            <span className="text-[10px] text-muted-foreground flex items-center tabular-nums">
              {listForTable.length}
            </span>
          </div>
          {runEventsLoading && listForTable.length === 0 && (
            <div className="flex justify-center py-6">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            </div>
          )}
          {!runEventsLoading && listForTable.length === 0 && (
            <p className="text-xs text-muted-foreground text-center py-6">No events for this run.</p>
          )}
          {listForTable.length > 0 && (
            <BacktestEventsTable
              events={listForTable}
              direction={direction}
              onOpenChart={(e) => {
                setChartEvent(e);
                setChartOpen(true);
              }}
              onFeedback={onEventFeedback ? handleFeedback : undefined}
            />
          )}
        </>
      )}

      <EventChartDialog open={chartOpen} onOpenChange={setChartOpen} event={chartEvent} direction={direction} />
    </div>
  );
}
