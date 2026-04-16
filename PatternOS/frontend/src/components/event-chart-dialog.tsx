"use client";
import type { PatternEvent } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ChartWidget } from "@/components/chart-widget";
import {
  type PatternDirection,
  strategyPnlPct,
  fmtCompactPct,
} from "@/lib/pattern-pnl";

export function EventChartDialog({
  open,
  onOpenChange,
  event,
  direction = "unknown",
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  event: PatternEvent | null;
  direction?: PatternDirection;
}) {
  if (!event) return null;
  const trig = event.detected_at?.slice(0, 10) ?? "";
  const p1w = strategyPnlPct(direction, event.ret_5d);
  const p1m = strategyPnlPct(direction, event.ret_21d);
  const p3m = strategyPnlPct(direction, event.ret_63d);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-[75vw] w-[75vw] max-h-[90vh] overflow-y-auto gap-2 p-3 sm:max-w-[75vw]"
        showCloseButton
      >
        <DialogHeader>
          <DialogTitle className="text-sm font-mono">
            {event.symbol} · {trig} · entry {event.entry_price?.toFixed(2) ?? "—"}
          </DialogTitle>
        </DialogHeader>
        <p className="text-[10px] font-mono text-muted-foreground -mt-1">
          Strategy P&amp;L (dir-aware): 1w {fmtCompactPct(p1w, 1)} · 1m {fmtCompactPct(p1m, 1)} · 3m{" "}
          {fmtCompactPct(p3m, 1)}
        </p>
        <p className="text-[10px] text-muted-foreground -mt-1">
          Markers: blue = trigger bar; violet / pink / amber = +1w / +1m / +3m (daily bars, approx).
        </p>
        <div className="min-h-[480px] w-full">
          <ChartWidget
            symbol={event.symbol}
            height={480}
            eventFocus={{
              triggerDate: trig,
              entryPrice: event.entry_price,
              horizons: [
                { label: "1w", bars: 5 },
                { label: "1m", bars: 21 },
                { label: "3m", bars: 63 },
              ],
            }}
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}
