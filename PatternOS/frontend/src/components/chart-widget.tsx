"use client";
/**
 * Lightweight chart widget using TradingView Lightweight Charts.
 * Fetches OHLCV from yfinance via backend (or static demo data if unavailable).
 */
import { useEffect, useRef } from "react";
import {
  createChart,
  CandlestickSeries,
  type IChartApi,
  ColorType,
  LineSeries,
} from "lightweight-charts";

interface KeyLevels {
  entry?: number;
  support?: number;
  resistance?: number;
  stop_loss?: number;
}

interface OHLCBar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

export function ChartWidget({
  symbol,
  keyLevels,
  height = 300,
}: {
  symbol: string;
  keyLevels?: KeyLevels | null;
  height?: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: "#0f0f11" },
        textColor: "#9ca3af",
      },
      grid: {
        vertLines: { color: "#1f2937" },
        horzLines: { color: "#1f2937" },
      },
      timeScale: { borderColor: "#374151" },
    });
    chartRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });

    // Fetch OHLCV from backend proxy
    fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/scanner/ohlcv?symbol=${encodeURIComponent(symbol)}&timeframe=1d`)
      .then((r) => r.ok ? r.json() : null)
      .then((data: OHLCBar[] | null) => {
        let bars = data && data.length > 0 ? data : (() => {
          // Demo fallback — generate synthetic bars
          const generated: OHLCBar[] = [];
          let price = 100;
          for (let i = 60; i >= 0; i--) {
            const d = new Date();
            d.setDate(d.getDate() - i);
            const change = (Math.random() - 0.48) * 3;
            const open = price;
            const close = price + change;
            const high = Math.max(open, close) + Math.random() * 1.5;
            const low  = Math.min(open, close) - Math.random() * 1.5;
            generated.push({
              time: d.toISOString().split("T")[0],
              open: +open.toFixed(2),
              high: +high.toFixed(2),
              low: +low.toFixed(2),
              close: +close.toFixed(2),
            });
            price = close;
          }
          return generated;
        })();

        // Sort by time in ascending order (required by lightweight-charts)
        bars.sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime());

        if (bars.length > 0) {
          candleSeries.setData(bars);
          chart.timeScale().fitContent();
        }
      })
      .catch(() => {});

    // Draw key level lines
    if (keyLevels) {
      const lineColors: Record<string, string> = {
        entry: "#3b82f6",
        stop_loss: "#ef4444",
        resistance: "#f59e0b",
        support: "#22c55e",
      };
      Object.entries(keyLevels).forEach(([key, value]) => {
        if (!value) return;
        const series = chart.addSeries(LineSeries, {
          color: lineColors[key] ?? "#9ca3af",
          lineWidth: 1,
          lineStyle: 2, // dashed
          title: key,
        });
        // Use a simple dummy data point to render horizontal line
        series.setData([
          { time: "2020-01-01", value },
          { time: new Date().toISOString().split("T")[0], value },
        ]);
      });
    }

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [symbol, keyLevels, height]);

  return <div ref={containerRef} className="w-full rounded-md overflow-hidden" />;
}
