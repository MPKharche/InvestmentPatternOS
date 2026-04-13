"use client";
import { useEffect, useState, useCallback } from "react";
import { PatternEvent, BacktestRun, studioApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Loader2, Search } from "lucide-react";
import { BacktestEventCard } from "./backtest-event-card";
import { BacktestSymbolTable } from "./backtest-symbol-table";

interface BacktestSymbolStats {
  symbol: string;
  count: number;
  success: number;
  failure: number;
  neutral?: number;
}

interface BacktestResultsProps {
  patternId: string;
  run: BacktestRun;
  onEventFeedback?: (id: string, feedback: string, notes: string) => void;
}

export function BacktestResults({
  patternId,
  run,
  onEventFeedback,
}: BacktestResultsProps) {
  const [events, setEvents] = useState<PatternEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [offset, setOffset] = useState(0);
  const [symbolFilter, setSymbolFilter] = useState("");
  const [symbolStats, setSymbolStats] = useState<BacktestSymbolStats[]>([]);
  const [viewMode, setViewMode] = useState<"list" | "symbols">("symbols");

  const LIMIT = 50;

  // Load symbol statistics on mount
  useEffect(() => {
    const loadSymbolStats = async () => {
      try {
        const res = await studioApi.getEvents(patternId, { limit: 200 });
        const map: Record<string, BacktestSymbolStats> = {};
        for (const e of res.events) {
          if (!map[e.symbol]) {
            map[e.symbol] = { symbol: e.symbol, count: 0, success: 0, failure: 0, neutral: 0 };
          }
          map[e.symbol].count++;
          if (e.outcome === "success") map[e.symbol].success++;
          else if (e.outcome === "failure") map[e.symbol].failure++;
          else if (e.outcome === "neutral") map[e.symbol].neutral = (map[e.symbol].neutral || 0) + 1;
        }
        const sorted = Object.values(map)
          .sort((a, b) => b.count - a.count);
        setSymbolStats(sorted);
      } catch (e) {
        console.error("Failed to load symbol stats", e);
      }
    };

    if (patternId) {
      loadSymbolStats();
    }
  }, [patternId]);

  // Load events
  const loadEvents = useCallback(
    async (reset = false) => {
      if (!patternId) return;
      setLoading(true);
      const newOffset = reset ? 0 : offset;
      try {
        const params: { symbol?: string; limit: number; offset: number } = {
          limit: LIMIT,
          offset: newOffset,
        };
        if (symbolFilter.trim()) {
          params.symbol = symbolFilter.trim().toUpperCase();
        }
        const res = await studioApi.getEvents(patternId, params);
        if (reset) {
          setEvents(res.events);
          setOffset(LIMIT);
        } else {
          setEvents((prev) => [...prev, ...res.events]);
          setOffset(newOffset + LIMIT);
        }
        setTotal(res.total);
      } catch (e) {
        console.error("Failed to load events", e);
      } finally {
        setLoading(false);
      }
    },
    [patternId, symbolFilter, offset]
  );

  // Load events on filter change
  useEffect(() => {
    loadEvents(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patternId, symbolFilter]);

  // Handle feedback update
  const handleFeedback = async (id: string, feedback: string, notes: string) => {
    try {
      await studioApi.updateEventFeedback(id, feedback, notes);
      setEvents((prev) =>
        prev.map((e) =>
          e.id === id ? { ...e, user_feedback: feedback, user_notes: notes } : e
        )
      );
      onEventFeedback?.(id, feedback, notes);
    } catch (e) {
      console.error("Failed to update event feedback", e);
    }
  };

  // Handle symbol click from table
  const handleSymbolClick = (symbol: string) => {
    setSymbolFilter(symbol);
    setViewMode("list");
  };

  return (
    <div className="space-y-4 border-t border-border/40 pt-4">
      {/* View Mode Toggle */}
      <div className="flex gap-2 items-center">
        <span className="text-xs font-semibold text-muted-foreground">View:</span>
        <Button
          size="sm"
          variant={viewMode === "symbols" ? "default" : "outline"}
          onClick={() => setViewMode("symbols")}
          className="text-xs h-7"
        >
          By Symbol
        </Button>
        <Button
          size="sm"
          variant={viewMode === "list" ? "default" : "outline"}
          onClick={() => setViewMode("list")}
          className="text-xs h-7"
        >
          Detailed Events
        </Button>
        {symbolFilter && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setSymbolFilter("")}
            className="text-xs h-7 ml-auto"
          >
            Clear filter ({symbolFilter})
          </Button>
        )}
      </div>

      {/* Symbol Breakdown View */}
      {viewMode === "symbols" && (
        <BacktestSymbolTable data={symbolStats} onSymbolClick={handleSymbolClick} />
      )}

      {/* Detailed Events View */}
      {viewMode === "list" && (
        <>
          {/* Search/Filter */}
          <div className="flex gap-2">
            <div className="flex-1 relative">
              <Search className="absolute left-2 top-2 h-4 w-4 text-muted-foreground" />
              <input
                type="text"
                placeholder="Filter by symbol..."
                value={symbolFilter}
                onChange={(e) => setSymbolFilter(e.target.value.toUpperCase())}
                className="w-full h-9 rounded-md border border-border bg-muted pl-8 pr-3 text-xs placeholder-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
            <span className="text-xs text-muted-foreground flex items-center px-2">
              {events.length} / {total}
            </span>
          </div>

          {/* Events List */}
          <div className="space-y-2 max-h-[600px] overflow-y-auto pr-2">
            {loading && events.length === 0 && (
              <div className="flex justify-center py-8">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            )}

            {!loading && events.length === 0 && (
              <Card>
                <CardContent className="py-8 text-center text-muted-foreground text-sm">
                  No events found {symbolFilter && `for ${symbolFilter}`}
                </CardContent>
              </Card>
            )}

            {events.map((event) => (
              <BacktestEventCard
                key={event.id}
                event={event}
                onFeedback={handleFeedback}
              />
            ))}

            {/* Load More Button */}
            {events.length < total && (
              <Button
                variant="outline"
                className="w-full text-xs h-8"
                onClick={() => loadEvents(false)}
                disabled={loading}
              >
                {loading ? (
                  <>
                    <Loader2 className="h-3 w-3 animate-spin mr-1" />
                    Loading...
                  </>
                ) : (
                  `Load more (${total - events.length} remaining)`
                )}
              </Button>
            )}
          </div>
        </>
      )}

      {/* Summary Stats */}
      <Card className="bg-muted/30 border-border/30">
        <CardContent className="pt-4">
          <p className="text-xs text-muted-foreground mb-2">
            <strong>Summary:</strong> {total} total events found. Success rate:{" "}
            <span className={run.success_rate && run.success_rate >= 50 ? "text-green-400" : "text-red-400"}>
              {run.success_rate?.toFixed(1) ?? "—"}%
            </span>
            . Avg 10d return:{" "}
            <span className={run.avg_ret_10d && run.avg_ret_10d > 0 ? "text-green-400" : "text-red-400"}>
              {run.avg_ret_10d ? `${run.avg_ret_10d >= 0 ? "+" : ""}${run.avg_ret_10d.toFixed(2)}%` : "—"}
            </span>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
