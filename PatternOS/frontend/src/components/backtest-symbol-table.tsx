"use client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface SymbolStats {
  symbol: string;
  count: number;
  success: number;
  failure: number;
  neutral?: number;
  avg_return_10d?: number;
}

interface BacktestSymbolTableProps {
  data: SymbolStats[];
  onSymbolClick?: (symbol: string) => void;
}

export function BacktestSymbolTable({
  data,
  onSymbolClick,
}: BacktestSymbolTableProps) {
  if (!data || data.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">By Symbol</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground text-center py-4">
            No events found in this backtest.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Top Symbols by Events</CardTitle>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border/50">
              <th className="text-left py-2 px-2 font-semibold text-muted-foreground">
                Symbol
              </th>
              <th className="text-center py-2 px-2 font-semibold text-muted-foreground">
                Events
              </th>
              <th className="text-center py-2 px-2 font-semibold text-muted-foreground">
                Success
              </th>
              <th className="text-center py-2 px-2 font-semibold text-muted-foreground">
                Failure
              </th>
              {data.some((d) => d.neutral != null) && (
                <th className="text-center py-2 px-2 font-semibold text-muted-foreground">
                  Neutral
                </th>
              )}
              <th className="text-center py-2 px-2 font-semibold text-muted-foreground">
                Win Rate
              </th>
              {data.some((d) => d.avg_return_10d != null) && (
                <th className="text-center py-2 px-2 font-semibold text-muted-foreground">
                  Avg 10d Return
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {data.map((row, i) => {
              const totalDefined = row.success + row.failure;
              const winRate =
                totalDefined > 0
                  ? ((row.success / totalDefined) * 100).toFixed(0)
                  : "—";
              const isHighWinRate = winRate !== "—" && Number(winRate) >= 50;

              return (
                <tr
                  key={row.symbol}
                  className={`border-b border-border/30 last:border-0 hover:bg-muted/30 transition-colors ${
                    onSymbolClick ? "cursor-pointer" : ""
                  }`}
                  onClick={() => onSymbolClick?.(row.symbol)}
                >
                  <td className="py-2 px-2">
                    <span className="font-mono font-medium text-foreground">
                      {row.symbol}
                    </span>
                  </td>
                  <td className="text-center py-2 px-2 text-muted-foreground">
                    {row.count}
                  </td>
                  <td className="text-center py-2 px-2">
                    <Badge
                      variant="outline"
                      className="bg-green-500/10 text-green-400 border-green-500/30 text-xs"
                    >
                      {row.success}
                    </Badge>
                  </td>
                  <td className="text-center py-2 px-2">
                    <Badge
                      variant="outline"
                      className="bg-red-500/10 text-red-400 border-red-500/30 text-xs"
                    >
                      {row.failure}
                    </Badge>
                  </td>
                  {data.some((d) => d.neutral != null) && (
                    <td className="text-center py-2 px-2 text-muted-foreground">
                      {row.neutral ?? 0}
                    </td>
                  )}
                  <td
                    className={`text-center py-2 px-2 font-semibold ${
                      isHighWinRate
                        ? "text-green-400"
                        : winRate === "—"
                        ? "text-muted-foreground"
                        : "text-red-400"
                    }`}
                  >
                    {winRate !== "—" ? `${winRate}%` : winRate}
                  </td>
                  {data.some((d) => d.avg_return_10d != null) && (
                    <td
                      className={`text-center py-2 px-2 font-mono ${
                        (row.avg_return_10d ?? 0) > 0
                          ? "text-green-400"
                          : (row.avg_return_10d ?? 0) === 0
                          ? "text-muted-foreground"
                          : "text-red-400"
                      }`}
                    >
                      {row.avg_return_10d != null
                        ? `${row.avg_return_10d >= 0 ? "+" : ""}${row.avg_return_10d.toFixed(2)}%`
                        : "—"}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
