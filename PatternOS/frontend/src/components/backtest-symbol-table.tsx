"use client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { PatternDirection } from "@/lib/pattern-pnl";
import { fmtCompactPct, fmtPnlColor } from "@/lib/pattern-pnl";

export interface SymbolStatsRow {
  symbol: string;
  count: number;
  success: number;
  failure: number;
  neutral?: number;
  avgPnl1w?: number | null;
  avgPnl1m?: number | null;
  avgPnl3m?: number | null;
  avg_return_10d?: number;
}

interface BacktestSymbolTableProps {
  data: SymbolStatsRow[];
  direction?: PatternDirection;
  onSymbolClick?: (symbol: string) => void;
}

export function BacktestSymbolTable({
  data,
  direction = "unknown",
  onSymbolClick,
}: BacktestSymbolTableProps) {
  if (!data || data.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">By Symbol</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground text-center py-4">No events found in this backtest.</p>
        </CardContent>
      </Card>
    );
  }

  const hdr = "text-[10px] leading-tight py-1 px-1 font-medium text-muted-foreground whitespace-nowrap";
  const cell = "py-1 px-1 align-middle whitespace-nowrap border-b border-border/30 text-[11px]";

  return (
    <Card>
      <CardHeader className="pb-1 pt-3">
        <CardTitle className="text-sm">Top Symbols by Events</CardTitle>
      </CardHeader>
      <CardContent className="pt-0 overflow-x-auto">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-border/50">
              <th className={`${hdr} text-left`}>Sym</th>
              <th className={`${hdr} text-center`}>N</th>
              <th className={`${hdr} text-center`}>OK</th>
              <th className={`${hdr} text-center`}>X</th>
              {data.some((d) => d.neutral != null) && <th className={`${hdr} text-center`}>—</th>}
              <th className={`${hdr} text-center`}>WR</th>
              <th className={`${hdr} text-center`}>1w</th>
              <th className={`${hdr} text-center`}>1m</th>
              <th className={`${hdr} text-center`}>3m</th>
              {data.some((d) => d.avg_return_10d != null) && (
                <th className={`${hdr} text-center`}>10d raw</th>
              )}
            </tr>
          </thead>
          <tbody>
            {data.map((row) => {
              const totalDefined = row.success + row.failure;
              const winRate = totalDefined > 0 ? ((row.success / totalDefined) * 100).toFixed(0) : "—";
              const isHighWinRate = winRate !== "—" && Number(winRate) >= 50;

              return (
                <tr
                  key={row.symbol}
                  className={`hover:bg-muted/30 ${onSymbolClick ? "cursor-pointer" : ""}`}
                  onClick={() => onSymbolClick?.(row.symbol)}
                >
                  <td className={`${cell} font-mono font-medium`}>{row.symbol.replace(".NS", "")}</td>
                  <td className={`${cell} text-center text-muted-foreground tabular-nums`}>{row.count}</td>
                  <td className={`${cell} text-center`}>
                    <Badge
                      variant="outline"
                      className="h-5 min-w-[1.25rem] px-1 text-[10px] bg-green-500/10 text-green-400 border-green-500/30"
                    >
                      {row.success}
                    </Badge>
                  </td>
                  <td className={`${cell} text-center`}>
                    <Badge
                      variant="outline"
                      className="h-5 min-w-[1.25rem] px-1 text-[10px] bg-red-500/10 text-red-400 border-red-500/30"
                    >
                      {row.failure}
                    </Badge>
                  </td>
                  {data.some((d) => d.neutral != null) && (
                    <td className={`${cell} text-center text-muted-foreground tabular-nums`}>{row.neutral ?? 0}</td>
                  )}
                  <td
                    className={`${cell} text-center font-semibold tabular-nums ${
                      isHighWinRate
                        ? "text-green-400"
                        : winRate === "—"
                          ? "text-muted-foreground"
                          : "text-red-400"
                    }`}
                  >
                    {winRate !== "—" ? `${winRate}%` : winRate}
                  </td>
                  <td className={`${cell} text-center font-mono tabular-nums ${fmtPnlColor(direction, row.avgPnl1w)}`}>
                    {fmtCompactPct(row.avgPnl1w ?? null, 1)}
                  </td>
                  <td className={`${cell} text-center font-mono tabular-nums ${fmtPnlColor(direction, row.avgPnl1m)}`}>
                    {fmtCompactPct(row.avgPnl1m ?? null, 1)}
                  </td>
                  <td className={`${cell} text-center font-mono tabular-nums ${fmtPnlColor(direction, row.avgPnl3m)}`}>
                    {fmtCompactPct(row.avgPnl3m ?? null, 1)}
                  </td>
                  {data.some((d) => d.avg_return_10d != null) && (
                    <td
                      className={`${cell} text-center font-mono tabular-nums ${
                        (row.avg_return_10d ?? 0) > 0
                          ? "text-green-400"
                          : (row.avg_return_10d ?? 0) === 0
                            ? "text-muted-foreground"
                            : "text-red-400"
                      }`}
                    >
                      {row.avg_return_10d != null
                        ? `${row.avg_return_10d >= 0 ? "+" : ""}${row.avg_return_10d.toFixed(1)}%`
                        : "—"}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="text-[10px] text-muted-foreground mt-2">1w / 1m / 3m = avg strategy P&amp;L % (direction-aware).</p>
      </CardContent>
    </Card>
  );
}
