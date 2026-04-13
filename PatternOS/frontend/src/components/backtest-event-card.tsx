"use client";
import { useState } from "react";
import { PatternEvent } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ExternalLink, ChevronDown, ChevronUp } from "lucide-react";

interface BacktestEventCardProps {
  event: PatternEvent;
  onFeedback?: (id: string, feedback: string, notes: string) => void;
}

export function BacktestEventCard({ event, onFeedback }: BacktestEventCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [notes, setNotes] = useState(event.user_notes ?? "");

  const handleNotesBlur = () => {
    if (onFeedback && notes !== (event.user_notes ?? "")) {
      onFeedback(event.id, event.user_feedback ?? "", notes);
    }
  };

  // Determine outcome badge styling
  const outcomeStyles: Record<string, string> = {
    success: "bg-green-500/20 text-green-400 border-green-500/30",
    failure: "bg-red-500/20 text-red-400 border-red-500/30",
    neutral: "bg-gray-500/20 text-gray-400 border-gray-500/30",
    pending: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  };

  const outcomeStyle = outcomeStyles[event.outcome ?? "pending"] ?? outcomeStyles.pending;

  // Helper to format percentage with color
  const formatReturn = (value: number | null) => {
    if (value == null) return "—";
    const prefix = value >= 0 ? "+" : "";
    return `${prefix}${value.toFixed(2)}%`;
  };

  const returnColor = (value: number | null) => {
    if (value == null) return "text-muted-foreground";
    return value > 0 ? "text-green-400" : value === 0 ? "text-muted-foreground" : "text-red-400";
  };

  // TradingView chart link for the exact date
  const chartUrl = event.detected_at
    ? `https://tradingview.com/chart/?symbol=NSE:${event.symbol}&date=${event.detected_at}`
    : null;

  return (
    <Card className="border-border/40 hover:border-border/60 transition-colors">
      <CardContent className="p-4">
        {/* Header: Symbol, Date, Entry Price, Outcome */}
        <div className="flex items-start justify-between gap-3 mb-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="font-mono font-bold text-base">{event.symbol}</span>
              <Badge variant="outline" className="text-xs">
                {event.timeframe || "1d"}
              </Badge>
            </div>
            <div className="flex items-center gap-4 text-xs text-muted-foreground">
              <span>📅 {event.detected_at || "—"}</span>
              {event.entry_price != null && (
                <span className="font-mono">₹ {event.entry_price.toFixed(2)}</span>
              )}
            </div>
          </div>
          <Badge className={`text-xs capitalize border ${outcomeStyle}`}>
            {event.outcome || "pending"}
          </Badge>
        </div>

        {/* Returns Grid: 5d, 10d, 20d, Max Gain/Loss */}
        <div className="grid grid-cols-2 gap-2 mb-4 p-3 bg-muted/30 rounded-lg">
          <div>
            <p className="text-xs text-muted-foreground">5d Return</p>
            <p className={`text-sm font-semibold ${returnColor(event.ret_5d)}`}>
              {formatReturn(event.ret_5d)}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">10d Return</p>
            <p className={`text-sm font-semibold ${returnColor(event.ret_10d)}`}>
              {formatReturn(event.ret_10d)}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">20d Return</p>
            <p className={`text-sm font-semibold ${returnColor(event.ret_20d)}`}>
              {formatReturn(event.ret_20d)}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Max Gain/Loss</p>
            <p className="text-xs font-semibold">
              <span className="text-green-400">{formatReturn(event.max_gain_20d)}</span>
              {" / "}
              <span className="text-red-400">{formatReturn(event.max_loss_20d)}</span>
            </p>
          </div>
        </div>

        {/* Indicators Snapshot */}
        {event.indicator_snapshot && Object.keys(event.indicator_snapshot).length > 0 && (
          <div className="mb-3 p-2 bg-blue-500/5 rounded border border-blue-500/20">
            <p className="text-xs font-semibold text-muted-foreground mb-1.5">
              Indicators at Entry
            </p>
            <div className="grid grid-cols-4 gap-1">
              {Object.entries(event.indicator_snapshot).map(([key, val]) => (
                <div key={key} className="text-xs">
                  <span className="text-muted-foreground">{key}:</span>
                  <span className="font-mono ml-1 text-foreground">
                    {typeof val === "number" ? val.toFixed(2) : String(val)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Expandable Section */}
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors mb-2 w-full"
        >
          {expanded ? (
            <ChevronUp className="h-3 w-3" />
          ) : (
            <ChevronDown className="h-3 w-3" />
          )}
          {expanded ? "Hide Details" : "Show Details"}
        </button>

        {expanded && (
          <div className="border-t border-border/40 pt-3 space-y-3">
            {/* Notes */}
            <div>
              <label className="text-xs font-semibold text-muted-foreground block mb-1.5">
                Notes & Remarks
              </label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                onBlur={handleNotesBlur}
                placeholder="Add your analysis, observations, or context..."
                className="w-full text-xs bg-muted border border-border rounded p-2 text-foreground placeholder-muted-foreground resize-none h-20 focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>

            {/* User Feedback */}
            {event.user_feedback && (
              <div className="p-2 bg-muted/50 rounded border border-border/50">
                <p className="text-xs font-semibold text-muted-foreground mb-1">
                  Your Assessment
                </p>
                <Badge variant="outline" className="text-xs capitalize">
                  {event.user_feedback}
                </Badge>
              </div>
            )}

            {/* Chart Links */}
            <div className="flex gap-2 pt-2">
              {chartUrl && (
                <a href={chartUrl} target="_blank" rel="noopener noreferrer">
                  <Button
                    size="sm"
                    variant="outline"
                    className="gap-1.5 text-xs h-7"
                  >
                    <ExternalLink className="h-3 w-3" />
                    View Chart on TradingView
                  </Button>
                </a>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
