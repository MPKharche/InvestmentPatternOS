"use client";
import { useEffect, useRef } from "react";
import {
  createChart,
  CandlestickSeries,
  LineSeries,
  HistogramSeries,
  LineStyle,
  type IChartApi,
  type Time,
} from "lightweight-charts";
import type { StockPrice } from "@/lib/api";
import {
  patternOsChartToolBase,
  patternOsCandlestickSeriesDefaults,
} from "@/lib/chart-theme";

interface IndicatorChartsProps {
  prices: StockPrice[];
  indicators: Record<string, (number | null)[]>;
  showSMA?: boolean;
  showEMA?: boolean;
  showBB?: boolean;
  showRSI?: boolean;
  showMACD?: boolean;
  showATR?: boolean;
}

/* Color palette for lines */
const COLORS = {
  sma: ["#f59e0b", "#a855f7", "#ec4899"],
  ema: ["#3b82f6", "#14b8a6", "#6366f1"],
  bb: ["#8b5cf6", "#6b7280", "#d1d5db"],
  rsi: "#f97316",
  macd: "#22c55e",
  macd_signal: "#ef4444",
  macd_hist_pos: "#22c55e",
  macd_hist_neg: "#ef4444",
};

export function IndicatorCharts({
  prices,
  indicators,
  showSMA = false,
  showEMA = false,
  showBB = false,
  showRSI = false,
  showMACD = false,
  showATR = false,
}: IndicatorChartsProps) {
  const priceRef = useRef<HTMLDivElement>(null);
  const rsiRef = useRef<HTMLDivElement>(null);
  const macdRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Price chart (candlesticks + overlays)
    const priceChart = priceRef.current
      ? createChart(priceRef.current, {
          ...patternOsChartToolBase,
          height: 350,
          width: priceRef.current.clientWidth,
        })
      : null;

    if (priceChart) {
      const candleSeries = priceChart.addSeries(CandlestickSeries, {
        ...patternOsCandlestickSeriesDefaults,
      });
      candleSeries.setData(
        prices.map((p) => ({
          time: p.date as Time,
          open: p.open,
          high: p.high,
          low: p.low,
          close: p.close,
        }))
      );

      // Overlays: SMA
      if (showSMA) {
        const smaPeriods = [20, 50, 200];
        smaPeriods.forEach((p, i) => {
          const data = indicators[`sma_${p}`];
          if (!data) return;
          const series = priceChart.addSeries(LineSeries, {
            color: COLORS.sma[i % COLORS.sma.length],
            lineWidth: 1,
            title: `SMA ${p}`,
          });
          series.setData(
            prices
              .map((p2, idx) => ({ time: p2.date as Time, value: data[idx] }))
              .filter((d) => d.value != null)
          );
        });
      }

      // EMA
      if (showEMA) {
        const emaPeriods = [20, 50, 200];
        emaPeriods.forEach((p, i) => {
          const data = indicators[`ema_${p}`];
          if (!data) return;
          const series = priceChart.addSeries(LineSeries, {
            color: COLORS.ema[i % COLORS.ema.length],
            lineWidth: 1,
            title: `EMA ${p}`,
          });
          series.setData(
            prices
              .map((p2, idx) => ({ time: p2.date as Time, value: data[idx] }))
              .filter((d) => d.value != null)
          );
        });
      }

      // Bollinger Bands
      if (showBB) {
        const upper = indicators["bb_upper"];
        const mid = indicators["bb_mid"];
        const lower = indicators["bb_lower"];
        if (upper) {
          const sUpper = priceChart.addSeries(LineSeries, { color: COLORS.bb[0], lineWidth: 1, title: "BB Upper" });
          sUpper.setData(prices.map((p2, i) => ({ time: p2.date as Time, value: upper[i] })).filter((d) => d.value != null));
        }
        if (mid) {
          const sMid = priceChart.addSeries(LineSeries, { color: COLORS.bb[1], lineWidth: 1, lineStyle: LineStyle.Dashed, title: "BB Mid" });
          sMid.setData(prices.map((p2, i) => ({ time: p2.date as Time, value: mid[i] })).filter((d) => d.value != null));
        }
        if (lower) {
          const sLower = priceChart.addSeries(LineSeries, { color: COLORS.bb[2], lineWidth: 1, title: "BB Lower" });
          sLower.setData(prices.map((p2, i) => ({ time: p2.date as Time, value: lower[i] })).filter((d) => d.value != null));
        }
      }

      priceChart.timeScale().fitContent();
    }

    // RSI chart
    let rsiChart: IChartApi | null = null;
    if (showRSI && rsiRef.current) {
      rsiChart = createChart(rsiRef.current, {
        ...patternOsChartToolBase,
        height: 150,
        width: rsiRef.current.clientWidth,
      });
      const rsiData = indicators["rsi"];
      if (rsiData) {
        const rsiSeries = rsiChart.addSeries(LineSeries, { color: COLORS.rsi, lineWidth: 2 });
        rsiSeries.setData(
          prices
            .map((p2, i) => ({ time: p2.date as Time, value: rsiData[i] }))
            .filter((d) => d.value != null)
        );
        // Overbought/oversold lines
        const start = prices[0].date as Time;
        const end = prices[prices.length - 1].date as Time;
        const overbought = rsiChart.addSeries(LineSeries, { lineWidth: 1, lineStyle: LineStyle.Dashed, color: "#ef4444" });
        overbought.setData([{ time: start, value: 70 }, { time: end, value: 70 }]);
        const oversold = rsiChart.addSeries(LineSeries, { lineWidth: 1, lineStyle: LineStyle.Dashed, color: "#22c55e" });
        oversold.setData([{ time: start, value: 30 }, { time: end, value: 30 }]);
      }
    }

    // MACD chart
    let macdChart: IChartApi | null = null;
    if (showMACD && macdRef.current) {
      macdChart = createChart(macdRef.current, {
        ...patternOsChartToolBase,
        height: 150,
        width: macdRef.current.clientWidth,
      });
      const macd = indicators["macd"];
      const signal = indicators["macd_signal"];
      const hist = indicators["macd_hist"];
      if (macd) {
        const macdLine = macdChart.addSeries(LineSeries, { color: COLORS.macd, lineWidth: 2, title: "MACD" });
        macdLine.setData(
          prices
            .map((p2, i) => ({ time: p2.date as Time, value: macd[i] }))
            .filter((d) => d.value != null)
        );
      }
      if (signal) {
        const signalLine = macdChart.addSeries(LineSeries, { color: COLORS.macd_signal, lineWidth: 1, title: "Signal" });
        signalLine.setData(
          prices
            .map((p2, i) => ({ time: p2.date as Time, value: signal[i] }))
            .filter((d) => d.value != null)
        );
      }
      if (hist) {
        const histSeries = macdChart.addSeries(HistogramSeries, {
          color: COLORS.macd_hist_pos,
          priceFormat: { type: "volume" },
        });
        const histData = prices
          .map((p2, i) => ({ time: p2.date as Time, value: hist[i] ?? 0 }))
          .filter((d) => d.value != null);
        // Color negative bars differently: we can supply color per value
        histSeries.setData(
          histData.map((d) => ({
            ...d,
            color: (d.value as number) >= 0 ? COLORS.macd_hist_pos : COLORS.macd_hist_neg,
          }))
        );
      }
    }

    // Resize handler
    const handleResize = () => {
      if (priceRef.current) priceChart?.applyOptions({ width: priceRef.current.clientWidth });
      if (rsiRef.current) rsiChart?.applyOptions({ width: rsiRef.current.clientWidth });
      if (macdRef.current) macdChart?.applyOptions({ width: macdRef.current.clientWidth });
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      priceChart?.remove();
      rsiChart?.remove();
      macdChart?.remove();
    };
  }, [prices, indicators, showSMA, showEMA, showBB, showRSI, showMACD]);

  return (
    <div className="space-y-4">
      <div ref={priceRef} className="w-full" />
      {showRSI && <div ref={rsiRef} className="w-full" />}
      {showMACD && <div ref={macdRef} className="w-full" />}
    </div>
  );
}
