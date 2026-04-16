/**
 * Direction-aware display: for bearish setups, price decline = favorable "profit".
 */

export type PatternDirection = "bearish" | "bullish" | "unknown";

export function inferDirectionFromRulebook(rb: Record<string, unknown> | null | undefined): PatternDirection {
  if (!rb || typeof rb !== "object") return "unknown";
  const d = String(rb.direction ?? "").toLowerCase();
  if (d === "bearish" || d === "bullish") return d;
  const pt = String(rb.pattern_type ?? "").toLowerCase();
  if (pt.includes("bearish") || (pt.includes("divergence") && d !== "bullish")) return "bearish";
  if (pt.includes("bullish")) return "bullish";
  const crit = rb.criteria;
  if (Array.isArray(crit)) {
    const s = crit.join(" ").toLowerCase();
    if (s.includes("bearish")) return "bearish";
    if (s.includes("bullish")) return "bullish";
  }
  return "unknown";
}

/** Raw return % from entry (positive = price up). */
export function strategyPnlPct(direction: PatternDirection, rawReturnPct: number | null | undefined): number | null {
  if (rawReturnPct == null || Number.isNaN(rawReturnPct)) return null;
  if (direction === "bearish") return -rawReturnPct;
  if (direction === "bullish") return rawReturnPct;
  return rawReturnPct;
}

export function forwardPrice(entry: number | null | undefined, rawReturnPct: number | null | undefined): number | null {
  if (entry == null || rawReturnPct == null) return null;
  return Math.round(entry * (1 + rawReturnPct / 100) * 100) / 100;
}

export function fmtCompactPct(v: number | null | undefined, digits = 1): string {
  if (v == null || Number.isNaN(v)) return "—";
  const s = v >= 0 ? "+" : "";
  return `${s}${v.toFixed(digits)}%`;
}

export function fmtPnlColor(direction: PatternDirection, strategyPnl: number | null | undefined): string {
  if (strategyPnl == null || Number.isNaN(strategyPnl)) return "text-muted-foreground";
  if (direction === "unknown") return strategyPnl >= 0 ? "text-green-400" : "text-red-400";
  return strategyPnl > 0 ? "text-green-400" : strategyPnl < 0 ? "text-red-400" : "text-muted-foreground";
}

export function avg(nums: (number | null | undefined)[]): number | null {
  const ok = nums.filter((n): n is number => n != null && !Number.isNaN(n));
  if (!ok.length) return null;
  return ok.reduce((a, b) => a + b, 0) / ok.length;
}
