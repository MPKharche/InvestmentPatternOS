"use client";
import type { PatternEvent } from "@/lib/api";
import {
  type PatternDirection,
  strategyPnlPct,
  forwardPrice,
  fmtCompactPct,
  fmtPnlColor,
} from "@/lib/pattern-pnl";
import { Button } from "@/components/ui/button";
import { LineChart } from "lucide-react";

function Cell({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <td className={`px-1.5 py-1 align-middle whitespace-nowrap border-b border-border/40 ${className}`}>
      {children}
    </td>
  );
}

export function BacktestEventsTable({
  events,
  direction,
  onOpenChart,
  onFeedback,
  compact = true,
}: {
  events: PatternEvent[];
  direction: PatternDirection;
  onOpenChart: (e: PatternEvent) => void;
  /** When set, shows compact valid / invalid / unsure toggles. */
  onFeedback?: (id: string, feedback: string, notes: string) => void;
  compact?: boolean;
}) {
  const rows = [...events].sort(
    (a, b) => new Date(b.detected_at).getTime() - new Date(a.detected_at).getTime()
  );

  const hdr = compact ? "text-[10px] leading-tight" : "text-xs";

  const col = (raw: number | null | undefined, entry: number | null | undefined) => {
    const pnl = strategyPnlPct(direction, raw);
    const px = forwardPrice(entry ?? null, raw);
    return (
      <span className="font-mono tabular-nums">
        <span className={fmtPnlColor(direction, pnl)}>{fmtCompactPct(pnl, 1)}</span>
        <span className="text-muted-foreground"> @</span>
        <span className="text-foreground/90">{px != null ? px.toFixed(1) : "—"}</span>
      </span>
    );
  };

  return (
    <div className="w-full overflow-x-auto rounded-md border border-border/50">
      <table className="w-full text-left border-collapse" style={{ fontSize: compact ? 11 : 12 }}>
        <thead>
          <tr className="bg-muted/40 text-muted-foreground">
            <th className={`${hdr} px-1.5 py-1 font-medium`}>Date</th>
            <th className={`${hdr} px-1.5 py-1 font-medium`}>Sym</th>
            <th className={`${hdr} px-1.5 py-1 font-medium`}>Spot</th>
            <th className={`${hdr} px-1.5 py-1 font-medium`}>Res</th>
            <th className={`${hdr} px-1.5 py-1 font-medium`}>1w</th>
            <th className={`${hdr} px-1.5 py-1 font-medium`}>1m</th>
            <th className={`${hdr} px-1.5 py-1 font-medium`}>3m</th>
            <th className={`${hdr} px-1 py-1 font-medium w-[44px]`}>Ch</th>
            {onFeedback && <th className={`${hdr} px-1 py-1 font-medium`}>Fb</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((e) => (
            <tr key={e.id} className="hover:bg-muted/25">
              <Cell>
                <span className="font-mono text-[10px]">{e.detected_at}</span>
              </Cell>
              <Cell>
                <span className="font-mono text-[10px]">{e.symbol.replace(".NS", "")}</span>
              </Cell>
              <Cell>
                <span className="font-mono">{e.entry_price != null ? e.entry_price.toFixed(2) : "—"}</span>
              </Cell>
              <Cell>
                <span
                  className={
                    e.outcome === "success"
                      ? "text-green-400"
                      : e.outcome === "failure"
                        ? "text-red-400"
                        : "text-muted-foreground"
                  }
                >
                  {(e.outcome ?? "—").slice(0, 4)}
                </span>
              </Cell>
              <Cell>{col(e.ret_5d, e.entry_price)}</Cell>
              <Cell>{col(e.ret_21d, e.entry_price)}</Cell>
              <Cell>{col(e.ret_63d, e.entry_price)}</Cell>
              <Cell>
                <Button
                  type="button"
                  variant="link"
                  size="sm"
                  className="h-6 px-0 py-0 text-[10px] text-sky-400 font-mono underline-offset-2"
                  title="Chart at this event"
                  onClick={() => onOpenChart(e)}
                >
                  <LineChart className="h-3 w-3 inline mr-0.5" />
                  view
                </Button>
              </Cell>
              {onFeedback && (
                <Cell className="px-0.5">
                  <div className="flex gap-0">
                    {(["valid", "invalid", "unsure"] as const).map((fb) => (
                      <button
                        key={fb}
                        type="button"
                        title={fb}
                        className={`text-[9px] px-1 py-0.5 rounded border leading-none ${
                          e.user_feedback === fb
                            ? fb === "valid"
                              ? "bg-green-500/25 border-green-500/50 text-green-300"
                              : fb === "invalid"
                                ? "bg-red-500/25 border-red-500/50 text-red-300"
                                : "bg-amber-500/20 border-amber-500/40 text-amber-200"
                            : "border-border/60 text-muted-foreground hover:border-foreground/30"
                        }`}
                        onClick={(ev) => {
                          ev.stopPropagation();
                          onFeedback(e.id, fb, e.user_notes ?? "");
                        }}
                      >
                        {fb === "valid" ? "✓" : fb === "invalid" ? "✗" : "?"}
                      </button>
                    ))}
                  </div>
                </Cell>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
