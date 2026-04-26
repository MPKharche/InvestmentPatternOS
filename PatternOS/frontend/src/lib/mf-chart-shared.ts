"use client";

import { useEffect, useRef } from "react";
import type { IChartApi, ISeriesApi, SeriesMarker, Time } from "lightweight-charts";
import type { MFIndicatorRecord } from "@/lib/api";

/** Merge multiple markers on the same day into one label to reduce overlap. */
export function collapseDailyMarkers<T extends SeriesMarker<Time>>(markers: T[]): T[] {
  const byTime = new Map<string, T[]>();
  for (const m of markers) {
    const k = String(m.time);
    if (!byTime.has(k)) byTime.set(k, []);
    byTime.get(k)!.push(m);
  }
  const out: T[] = [];
  for (const group of byTime.values()) {
    if (group.length === 1) {
      out.push(group[0]);
      continue;
    }
    const first = group[0];
    const extra = group.length - 1;
    out.push({
      ...first,
      text: first.text ? `${String(first.text)} (+${extra})` : `(+${extra})`,
    } as T);
  }
  return out;
}

function timeKey(t: unknown): string | null {
  if (!t) return null;
  if (typeof t === "string") return t;
  if (typeof t === "object" && t !== null && "year" in t && "month" in t && "day" in t) {
    const o = t as { year: number; month: number; day: number };
    const y = String(o.year);
    const m = String(o.month).padStart(2, "0");
    const d = String(o.day).padStart(2, "0");
    return `${y}-${m}-${d}`;
  }
  return String(t);
}

/**
 * NAV (or OHLC close) pane drives visible range + crosshair for RSI/MACD panes.
 * Pass refs so late-mounted indicator charts still subscribe correctly.
 */
export function useMfNavIndicatorSync(opts: {
  indByTime: Map<string, MFIndicatorRecord>;
  priceByTime: Map<string, number>;
  showRsi: boolean;
  showMacd: boolean;
  /** Re-subscribe when bar TF / style / panes change (ref `.current` is not reactive). */
  layoutKey?: string | number;
  chartApiRef: React.RefObject<IChartApi | null>;
  mainSeriesRef: React.RefObject<ISeriesApi<"Line"> | ISeriesApi<"Candlestick"> | null>;
  rsiChartApiRef: React.RefObject<IChartApi | null>;
  rsiSeriesRef: React.RefObject<ISeriesApi<"Line"> | null>;
  macdChartApiRef: React.RefObject<IChartApi | null>;
  macdSeriesRef: React.RefObject<ISeriesApi<"Line"> | null>;
  macdSignalRef: React.RefObject<ISeriesApi<"Line"> | null>;
}): void {
  const syncingCrosshair = useRef(false);

  useEffect(() => {
    const main = opts.chartApiRef.current;
    const mainSeries = opts.mainSeriesRef.current;
    if (!main || !mainSeries) return;

    const rsiChart = opts.rsiChartApiRef.current;
    const rsiSeries = opts.rsiSeriesRef.current;
    const macdChart = opts.macdChartApiRef.current;

    const clearOthers = () => {
      try {
        if (opts.showRsi && rsiChart) rsiChart.clearCrosshairPosition();
      } catch {
        /* ignore */
      }
      try {
        if (opts.showMacd && macdChart) macdChart.clearCrosshairPosition();
      } catch {
        /* ignore */
      }
    };

    const onMainMove = (param: { time?: unknown } | null) => {
      if (syncingCrosshair.current) return;
      syncingCrosshair.current = true;
      try {
        const t = timeKey(param?.time);
        if (!t) {
          clearOthers();
          return;
        }
        const rec = opts.indByTime.get(t);

        if (opts.showRsi && rsiChart && rsiSeries && rec?.rsi != null) {
          rsiChart.setCrosshairPosition(rec.rsi, param?.time as Time, rsiSeries);
        } else if (opts.showRsi && rsiChart) {
          rsiChart.clearCrosshairPosition();
        }

        if (opts.showMacd && macdChart) {
          const v = rec?.macd ?? rec?.macd_signal ?? null;
          const targetSeries = rec?.macd != null ? opts.macdSeriesRef.current : opts.macdSignalRef.current;
          if (v != null && targetSeries) macdChart.setCrosshairPosition(v, param?.time as Time, targetSeries);
          else macdChart.clearCrosshairPosition();
        }
      } finally {
        syncingCrosshair.current = false;
      }
    };

    main.subscribeCrosshairMove(onMainMove);

    const onRsiMove = (param: { time?: unknown } | null) => {
      if (!opts.showRsi || !rsiChart) return;
      if (syncingCrosshair.current) return;
      syncingCrosshair.current = true;
      try {
        const t = timeKey(param?.time);
        if (!t) {
          main.clearCrosshairPosition();
          return;
        }
        const px = opts.priceByTime.get(t);
        if (px != null) main.setCrosshairPosition(px, param?.time as Time, mainSeries);
      } finally {
        syncingCrosshair.current = false;
      }
    };

    const onMacdMove = (param: { time?: unknown } | null) => {
      if (!opts.showMacd || !macdChart) return;
      if (syncingCrosshair.current) return;
      syncingCrosshair.current = true;
      try {
        const t = timeKey(param?.time);
        if (!t) {
          main.clearCrosshairPosition();
          return;
        }
        const px = opts.priceByTime.get(t);
        if (px != null) main.setCrosshairPosition(px, param?.time as Time, mainSeries);
      } finally {
        syncingCrosshair.current = false;
      }
    };

    if (rsiChart) rsiChart.subscribeCrosshairMove(onRsiMove);
    if (macdChart) macdChart.subscribeCrosshairMove(onMacdMove);

    return () => {
      main.unsubscribeCrosshairMove(onMainMove);
      if (rsiChart) rsiChart.unsubscribeCrosshairMove(onRsiMove);
      if (macdChart) macdChart.unsubscribeCrosshairMove(onMacdMove);
    };
    // Refs are stable; maps and booleans drive refresh (avoid `[opts]` — new object every render).
  }, [
    opts.indByTime,
    opts.priceByTime,
    opts.showRsi,
    opts.showMacd,
    opts.chartApiRef,
    opts.mainSeriesRef,
    opts.rsiChartApiRef,
    opts.rsiSeriesRef,
    opts.macdChartApiRef,
    opts.macdSeriesRef,
    opts.macdSignalRef,
    opts.layoutKey ?? 0,
  ]);
}
