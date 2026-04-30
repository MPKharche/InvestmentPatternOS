"use client";
/**
 * Lightweight chart — OHLCV from backend; optional key levels and event markers.
 */
import { useEffect, useRef } from "react";
import {
  createChart,
  CandlestickSeries,
  createSeriesMarkers,
  LineSeries,
  type IChartApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import {
  patternOsChartToolBase,
  patternOsCandlestickSeriesDefaults,
} from "@/lib/chart-theme";

export interface KeyLevels {
  entry?: number;
  support?: number;
  resistance?: number;
  stop_loss?: number;
}

export interface EventChartFocus {
  triggerDate: string;
  entryPrice?: number | null;
  /** Bar offsets from trigger (daily): 1w≈5, 1m≈21, 3m≈63 */
  horizons: { label: string; bars: number }[];
}

interface OHLCBar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export function ChartWidget({
  symbol,
  keyLevels,
  height = 300,
  eventFocus,
}: {
  symbol: string;
  keyLevels?: KeyLevels | null;
  height?: number;
  eventFocus?: EventChartFocus | null;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: patternOsChartToolBase.layout,
      grid: patternOsChartToolBase.grid,
      crosshair: patternOsChartToolBase.crosshair,
      timeScale: patternOsChartToolBase.timeScale,
    });
    chartRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      ...patternOsCandlestickSeriesDefaults,
    });
    markersRef.current = createSeriesMarkers(candleSeries, []);

    let cancelled = false;

    (async () => {
      let bars: OHLCBar[] = [];
      try {
        const r = await fetch(`${BASE}/scanner/ohlcv?symbol=${encodeURIComponent(symbol)}&timeframe=1d`);
        const data = r.ok ? ((await r.json()) as OHLCBar[]) : null;
        if (data && data.length > 0) bars = data;
      } catch {
        /* ignore */
      }

      if (cancelled) return;

      if (!bars.length) {
        const generated: OHLCBar[] = [];
        let price = 100;
        for (let i = 120; i >= 0; i--) {
          const d = new Date();
          d.setDate(d.getDate() - i);
          const change = (Math.random() - 0.48) * 2;
          const open = price;
          const close = price + change;
          const high = Math.max(open, close) + Math.random();
          const low = Math.min(open, close) - Math.random();
          generated.push({
            time: d.toISOString().split("T")[0],
            open: +open.toFixed(2),
            high: +high.toFixed(2),
            low: +low.toFixed(2),
            close: +close.toFixed(2),
          });
          price = close;
        }
        bars = generated;
      }

      bars.sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime());
      if (!bars.length) return;

      candleSeries.setData(bars);

      const t0 = bars[0].time as Time;
      const t1 = bars[bars.length - 1].time as Time;

      if (keyLevels) {
        const lineColors: Record<string, string> = {
          entry: "#3b82f6",
          stop_loss: "#ef4444",
          resistance: "#f59e0b",
          support: "#22c55e",
        };
        Object.entries(keyLevels).forEach(([key, value]) => {
          if (value == null) return;
          const series = chart.addSeries(LineSeries, {
            color: lineColors[key] ?? "#9ca3af",
            lineWidth: 1,
            lineStyle: 2,
            title: key,
          });
          series.setData([
            { time: t0, value },
            { time: t1, value },
          ]);
        });
      }

      if (eventFocus?.triggerDate && markersRef.current) {
        const trig = eventFocus.triggerDate.slice(0, 10);
        let idx = bars.findIndex((b) => b.time >= trig);
        if (idx < 0) idx = bars.length - 1;
        const mk: SeriesMarker<Time>[] = [];
        const entryP = eventFocus.entryPrice ?? bars[idx]?.close;
        mk.push({
          time: bars[idx].time as Time,
          position: "aboveBar",
          color: "#60a5fa",
          shape: "circle",
          text: `E ${entryP != null ? entryP.toFixed(0) : ""}`,
        });
        const palette = ["#a78bfa", "#f472b6", "#fbbf24"];
        (eventFocus.horizons ?? [
          { label: "1w", bars: 5 },
          { label: "1m", bars: 21 },
          { label: "3m", bars: 63 },
        ]).forEach((h, i) => {
          const j = idx + h.bars;
          if (j < bars.length) {
            mk.push({
              time: bars[j].time as Time,
              position: "belowBar",
              color: palette[i % palette.length],
              shape: "square",
              text: h.label,
            });
          }
        });
        markersRef.current.setMarkers(mk);
        chart.timeScale().setVisibleRange({
          from: (bars[Math.max(0, idx - 40)].time as Time) as Time,
          to: (bars[Math.min(bars.length - 1, idx + 80)].time as Time) as Time,
        });
      } else {
        chart.timeScale().fitContent();
      }
    })();

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      cancelled = true;
      window.removeEventListener("resize", handleResize);
      markersRef.current = null;
      chart.remove();
    };
  }, [symbol, keyLevels, height, eventFocus]);

  return <div ref={containerRef} className="w-full rounded-md overflow-hidden" />;
}
