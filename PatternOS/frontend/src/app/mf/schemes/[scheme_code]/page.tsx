"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import {
  createChart,
  CandlestickSeries,
  LineSeries,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
  LineStyle,
} from "lightweight-charts";
import {
  patternOsChartMfCardOptions,
  patternOsChartMfSubPaneOptions,
  patternOsCandlestickSeriesDefaults,
} from "@/lib/chart-theme";
import { mfApi, type MFIndicatorRecord, type MFOhlcBar, type MFPatternsResponse, type MFScheme, type MFSignal } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import Link from "next/link";
import { Download, RefreshCw } from "lucide-react";

type IndKey = "ema20" | "ema50" | "rsi" | "macd";
type ChartStyle = "candles" | "heikin" | "line";

function extractMorningstarSecId(url: string): string | null {
  const m = url.match(/\/mutualfunds\/([a-z0-9]{6,})\//i);
  return m?.[1] ? m[1].toUpperCase() : null;
}

// Time-scale sync guard (prevents recursive range updates)
let _syncing = false;
function syncRange(source: IChartApi, ...targets: (IChartApi | null)[]) {
  if (_syncing) return;
  const range = source.timeScale().getVisibleLogicalRange();
  if (!range) return;
  _syncing = true;
  for (const t of targets) {
    try {
      t?.timeScale().setVisibleLogicalRange(range);
    } catch {
      /**/
    }
  }
  _syncing = false;
}

export default function MFSchemeDetailPage() {
  const params = useParams<{ scheme_code: string }>();
  const schemeCode = Number(params.scheme_code);

  const [scheme, setScheme] = useState<MFScheme | null>(null);
  const [bars, setBars] = useState<MFOhlcBar[]>([]);
  const [indicators, setIndicators] = useState<MFIndicatorRecord[]>([]);
  const [patterns, setPatterns] = useState<MFPatternsResponse | null>(null);
  const [metrics, setMetrics] = useState<any>(null);
  const [holdings, setHoldings] = useState<any>(null);
  const [signals, setSignals] = useState<MFSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [latestAmfiDate, setLatestAmfiDate] = useState<string | null>(null);
  const [variantSuggestion, setVariantSuggestion] = useState<MFScheme | null>(null);
  const [switchingVariant, setSwitchingVariant] = useState(false);

  const chartRef = useRef<HTMLDivElement>(null);
  const chartApi = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const lineSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const candleMarkersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const lineMarkersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const ema20Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ema50Ref = useRef<ISeriesApi<"Line"> | null>(null);

  const rsiRef = useRef<HTMLDivElement>(null);
  const rsiChartApi = useRef<IChartApi | null>(null);
  const rsiSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  const macdRef = useRef<HTMLDivElement>(null);
  const macdChartApi = useRef<IChartApi | null>(null);
  const macdSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const macdSignalRef = useRef<ISeriesApi<"Line"> | null>(null);

  const [barTf, setBarTf] = useState<"1d" | "1w" | "1M">("1d");
  const [timeframe, setTimeframe] = useState<"1M" | "3M" | "6M" | "1Y" | "3Y" | "5Y" | "10Y" | "MAX">("MAX");
  const [activeInds, setActiveInds] = useState<Set<IndKey>>(new Set(["ema20", "ema50", "rsi"]));
  const [chartStyle, setChartStyle] = useState<ChartStyle>("candles");
  const showRsi = activeInds.has("rsi");
  const showMacd = activeInds.has("macd");

  useEffect(() => {
    if (barTf === "1d" && chartStyle === "heikin") setChartStyle("candles");
    if (barTf !== "1d" && chartStyle === "candles") setChartStyle("heikin");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [barTf]);

  useEffect(() => {
    void mfApi
      .status()
      .then((st) => {
        const d = (st as any)?.latest_nav_run?.stats_json?.latest_date;
        if (typeof d === "string" && d.length >= 10) setLatestAmfiDate(d.slice(0, 10));
      })
      .catch(() => {});
  }, []);

  const load = async () => {
    setLoading(true);
    try {
      const lim = barTf === "1d" ? 2500 : 5000;
      const ha = chartStyle === "heikin";
      const [s, n, inds, pats, m, sigs] = await Promise.all([
        mfApi.scheme(schemeCode),
        mfApi.ohlc(schemeCode, lim, barTf, ha),
        mfApi.indicators(schemeCode, lim, barTf),
        mfApi.patterns(schemeCode, 220, barTf),
        mfApi.metrics(schemeCode),
        mfApi.signals("all", 400),
      ]);
      setScheme(s);
      setBars(n);
      setIndicators(inds);
      setPatterns(pats);
      setMetrics(m);
      setSignals(sigs.filter((x) => x.scheme_code === schemeCode));
      if (s.family_id) {
        try {
          const h = await mfApi.holdings(s.family_id);
          setHoldings(h);
        } catch {
          setHoldings(null);
        }
      } else {
        setHoldings(null);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to load scheme");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schemeCode, barTf]);

  useEffect(() => {
    const s = scheme;
    if (!s?.scheme_name || !s?.latest_nav_date || !latestAmfiDate) {
      setVariantSuggestion(null);
      return;
    }
    const cur = new Date(s.latest_nav_date);
    const latest = new Date(latestAmfiDate);
    const days = Math.floor((latest.getTime() - cur.getTime()) / (24 * 3600 * 1000));
    if (!Number.isFinite(days) || days <= 30) {
      setVariantSuggestion(null);
      return;
    }
    let cancelled = false;
    void mfApi
      .schemes(false, s.scheme_name)
      .then((list) => {
        if (cancelled) return;
        const candidates = (list || []).filter((x) => x.scheme_name === s.scheme_name && x.latest_nav_date);
        candidates.sort((a, b) => String(b.latest_nav_date).localeCompare(String(a.latest_nav_date)));
        const best = candidates[0];
        if (best && best.scheme_code !== s.scheme_code && String(best.latest_nav_date) > String(s.latest_nav_date)) setVariantSuggestion(best);
        else setVariantSuggestion(null);
      })
      .catch(() => setVariantSuggestion(null));
    return () => {
      cancelled = true;
    };
  }, [scheme?.scheme_code, scheme?.scheme_name, scheme?.latest_nav_date, latestAmfiDate]);

  const switchToSuggestedVariant = async () => {
    if (!scheme || !variantSuggestion) return;
    setSwitchingVariant(true);
    try {
      if (scheme.monitored) {
        await Promise.all([
          mfApi.updateScheme(scheme.scheme_code, { monitored: false }),
          mfApi.updateScheme(variantSuggestion.scheme_code, { monitored: true }),
        ]);
      }
      window.location.href = `/mf/schemes/${variantSuggestion.scheme_code}`;
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to switch scheme variant");
    } finally {
      setSwitchingVariant(false);
    }
  };

  const filteredBars = useMemo(() => {
    if (timeframe === "MAX") return bars;
    if (!bars.length) return bars;
    const end = new Date(bars[bars.length - 1].time);
    const start = new Date(end);
    if (timeframe === "1M") start.setMonth(start.getMonth() - 1);
    if (timeframe === "3M") start.setMonth(start.getMonth() - 3);
    if (timeframe === "6M") start.setMonth(start.getMonth() - 6);
    if (timeframe === "1Y") start.setFullYear(start.getFullYear() - 1);
    if (timeframe === "3Y") start.setFullYear(start.getFullYear() - 3);
    if (timeframe === "5Y") start.setFullYear(start.getFullYear() - 5);
    if (timeframe === "10Y") start.setFullYear(start.getFullYear() - 10);
    return bars.filter((p) => new Date(p.time) >= start);
  }, [bars, timeframe]);

  const filteredIndicators = useMemo(() => {
    if (!indicators.length || !filteredBars.length) return [];
    const allowed = new Set(filteredBars.map((p) => p.time));
    return indicators.filter((r) => allowed.has(r.time));
  }, [indicators, filteredBars]);

  const navByTime = useMemo(() => {
    return new Map(filteredBars.map((p) => [p.time, p.close]));
  }, [filteredBars]);

  const indByTime = useMemo(() => {
    return new Map(filteredIndicators.map((r) => [r.time, r]));
  }, [filteredIndicators]);

  // Init chart
  useEffect(() => {
    if (!chartRef.current) return;
    const c = createChart(chartRef.current, {
      width: chartRef.current.clientWidth,
      ...patternOsChartMfCardOptions({ height: 260, timeScaleVisible: false }),
    });
    const candles = c.addSeries(CandlestickSeries, {
      ...patternOsCandlestickSeriesDefaults,
    });
    const line = c.addSeries(LineSeries, { color: "#38bdf8", lineWidth: 2, priceLineVisible: false, lastValueVisible: true });
    const e20 = c.addSeries(LineSeries, { color: "#22c55e", lineWidth: 1, priceLineVisible: false, lastValueVisible: false, lineStyle: LineStyle.Dotted });
    const e50 = c.addSeries(LineSeries, { color: "#3b82f6", lineWidth: 1, priceLineVisible: false, lastValueVisible: false, lineStyle: LineStyle.Dotted });
    const candleMarkers = createSeriesMarkers(candles);
    const lineMarkers = createSeriesMarkers(line);
    chartApi.current = c;
    candleSeriesRef.current = candles;
    lineSeriesRef.current = line;
    ema20Ref.current = e20;
    ema50Ref.current = e50;
    candleMarkersRef.current = candleMarkers;
    lineMarkersRef.current = lineMarkers;
    const ro = new ResizeObserver(() => {
      if (!chartRef.current) return;
      c.applyOptions({ width: chartRef.current.clientWidth });
    });
    ro.observe(chartRef.current);
    return () => {
      ro.disconnect();
      c.remove();
      chartApi.current = null;
      candleSeriesRef.current = null;
      lineSeriesRef.current = null;
      ema20Ref.current = null;
      ema50Ref.current = null;
      candleMarkersRef.current = null;
      lineMarkersRef.current = null;
    };
  }, []);

  // Set chart data
  useEffect(() => {
    if (!filteredBars.length) return;
    const candleData = filteredBars.map((b) => ({ time: b.time as Time, open: b.open, high: b.high, low: b.low, close: b.close }));
    const lineData = filteredBars.map((b) => ({ time: b.time as Time, value: b.close }));
    if (chartStyle === "line") {
      candleSeriesRef.current?.setData([] as any);
      lineSeriesRef.current?.setData(lineData as any);
    } else {
      lineSeriesRef.current?.setData([] as any);
      candleSeriesRef.current?.setData(candleData as any);
    }
    chartApi.current?.timeScale().fitContent();
    if (chartApi.current) syncRange(chartApi.current, rsiChartApi.current, macdChartApi.current);
  }, [filteredBars, chartStyle]);

  useEffect(() => {
    if (!filteredBars.length) return;
    const times = filteredBars.map((p) => p.time as Time);
    const byTime = new Map(filteredIndicators.map((r) => [r.time, r]));

    if (ema20Ref.current) {
      if (activeInds.has("ema20")) {
        const data = times
          .map((t) => {
            const r = byTime.get(String(t));
            return r?.ema_20 != null ? { time: t, value: r.ema_20 } : null;
          })
          .filter(Boolean) as any;
        ema20Ref.current.setData(data);
      } else {
        ema20Ref.current.setData([] as any);
      }
    }

    if (ema50Ref.current) {
      if (activeInds.has("ema50")) {
        const data = times
          .map((t) => {
            const r = byTime.get(String(t));
            return r?.ema_50 != null ? { time: t, value: r.ema_50 } : null;
          })
          .filter(Boolean) as any;
        ema50Ref.current.setData(data);
      } else {
        ema50Ref.current.setData([] as any);
      }
    }
  }, [filteredBars, filteredIndicators, activeInds]);

  useEffect(() => {
    const markersApi = chartStyle === "line" ? lineMarkersRef.current : candleMarkersRef.current;
    if (!markersApi) return;
    const markers: SeriesMarker<Time>[] = [];

    const min = filteredBars.length ? filteredBars[0].time : null;
    const max = filteredBars.length ? filteredBars[filteredBars.length - 1].time : null;

    // Signals: collapse to 1 marker per day (prevents label overlap).
    const sigByDate = new Map<string, MFSignal[]>();
    for (const s of signals) {
      if (!s.nav_date) continue;
      if (min && max && (s.nav_date < min || s.nav_date > max)) continue;
      const list = sigByDate.get(s.nav_date) ?? [];
      list.push(s);
      sigByDate.set(s.nav_date, list);
    }
    sigByDate.forEach((list, date) => {
      const best = [...list].sort((a, b) => (b.confidence_score ?? 0) - (a.confidence_score ?? 0))[0];
      const col = best.confidence_score >= 80 ? "#22c55e" : best.confidence_score >= 70 ? "#f59e0b" : "#ef4444";
      const m: SeriesMarker<Time> = {
        time: date as Time,
        position: "aboveBar",
        color: col,
        shape: list.length > 1 ? "square" : "circle",
        size: list.length > 1 ? 2 : 1,
      };
      // Show only a count label when multiple signals collide on the same day.
      if (list.length > 1) m.text = String(list.length);
      markers.push(m);
    });

    const talib = (patterns?.talib_candlestick_patterns || []) as any[];
    const native = (patterns?.candlestick_patterns || []) as any[];
    const allPats = [
      ...talib.map((p) => ({ time: p?.time, label: p?.name, direction: p?.direction })),
      ...native.map((p) => ({ time: p?.date, label: p?.pattern, direction: p?.direction })),
    ].filter((p) => p.time && p.label);

    const patInWindow = allPats.filter((p) => !min || !max || (String(p.time) >= min && String(p.time) <= max));
    // Patterns: collapse per day + direction (prevents overlapping text clutter).
    const patsByDate = new Map<string, { bull: any[]; bear: any[]; other: any[] }>();
    for (const p of patInWindow) {
      const key = String(p.time);
      const entry = patsByDate.get(key) ?? { bull: [], bear: [], other: [] };
      if (p.direction === "bullish") entry.bull.push(p);
      else if (p.direction === "bearish") entry.bear.push(p);
      else entry.other.push(p);
      patsByDate.set(key, entry);
    }
    const patDates = Array.from(patsByDate.keys()).sort((a, b) => a.localeCompare(b));
    const recentDates = patDates.slice(Math.max(0, patDates.length - 12));
    for (const d of recentDates) {
      const entry = patsByDate.get(d)!;
      if (entry.bear.length) {
        const m: SeriesMarker<Time> = { time: d as Time, position: "aboveBar", color: "#ef4444", shape: "arrowDown", size: 1 };
        if (entry.bear.length > 1) m.text = String(entry.bear.length);
        markers.push(m);
      }
      if (entry.bull.length) {
        const m: SeriesMarker<Time> = { time: d as Time, position: "belowBar", color: "#22c55e", shape: "arrowUp", size: 1 };
        if (entry.bull.length > 1) m.text = String(entry.bull.length);
        markers.push(m);
      }
      if (!entry.bull.length && !entry.bear.length && entry.other.length) {
        const m: SeriesMarker<Time> = { time: d as Time, position: "aboveBar", color: "#9ca3af", shape: "circle", size: 1 };
        if (entry.other.length > 1) m.text = String(entry.other.length);
        markers.push(m);
      }
    }
    markersApi.setMarkers(markers);
  }, [signals, patterns, filteredBars, chartStyle]);

  useEffect(() => {
    if (!showRsi) {
      rsiChartApi.current?.remove();
      rsiChartApi.current = null;
      rsiSeriesRef.current = null;
      return;
    }
    if (!rsiRef.current) return;
    if (rsiChartApi.current) return;

    const c = createChart(rsiRef.current, {
      width: rsiRef.current.clientWidth,
      ...patternOsChartMfSubPaneOptions({ height: 140, timeScaleVisible: !showMacd }),
    });
    const s = c.addSeries(LineSeries, { color: "#a78bfa", lineWidth: 2, priceLineVisible: false, lastValueVisible: true });
    rsiChartApi.current = c;
    rsiSeriesRef.current = s;
    const ro = new ResizeObserver(() => c.applyOptions({ width: rsiRef.current?.clientWidth ?? 0 }));
    ro.observe(rsiRef.current);
    return () => {
      ro.disconnect();
      c.remove();
      rsiChartApi.current = null;
      rsiSeriesRef.current = null;
    };
  }, [showRsi]);

  useEffect(() => {
    if (!rsiSeriesRef.current) return;
    if (!showRsi) return;
    if (!filteredBars.length) return;
    const byTime = new Map(filteredIndicators.map((r) => [r.time, r]));
    const data = filteredBars
      .map((p) => {
        const r = byTime.get(p.time);
        return r?.rsi != null ? { time: p.time as Time, value: r.rsi } : null;
      })
      .filter(Boolean) as any;
    rsiSeriesRef.current.setData(data);
  }, [filteredBars, filteredIndicators, showRsi]);

  useEffect(() => {
    if (!showMacd) {
      macdChartApi.current?.remove();
      macdChartApi.current = null;
      macdSeriesRef.current = null;
      macdSignalRef.current = null;
      return;
    }
    if (!macdRef.current) return;
    if (macdChartApi.current) return;

    const c = createChart(macdRef.current, {
      width: macdRef.current.clientWidth,
      ...patternOsChartMfSubPaneOptions({ height: 160, timeScaleVisible: true }),
    });
    const m = c.addSeries(LineSeries, { color: "#38bdf8", lineWidth: 2, priceLineVisible: false, lastValueVisible: true });
    const sig = c.addSeries(LineSeries, { color: "#f59e0b", lineWidth: 2, priceLineVisible: false, lastValueVisible: true, lineStyle: LineStyle.Dotted });
    macdChartApi.current = c;
    macdSeriesRef.current = m;
    macdSignalRef.current = sig;
    const ro = new ResizeObserver(() => c.applyOptions({ width: macdRef.current?.clientWidth ?? 0 }));
    ro.observe(macdRef.current);
    return () => {
      ro.disconnect();
      c.remove();
      macdChartApi.current = null;
      macdSeriesRef.current = null;
      macdSignalRef.current = null;
    };
  }, [showMacd]);

  // Keep indicator panes in sync with the NAV timeline (single driver = main chart).
  useEffect(() => {
    const main = chartApi.current;
    if (!main) return;
    const ts = main.timeScale();
    const onRange = (range: { from: number; to: number } | null) => {
      // lightweight-charts can emit null/partial ranges during init/teardown; ignore those.
      if (!range || range.from == null || range.to == null) return;
      try {
        if (showRsi && rsiChartApi.current) rsiChartApi.current.timeScale().setVisibleLogicalRange(range);
      } catch {}
      try {
        if (showMacd && macdChartApi.current) macdChartApi.current.timeScale().setVisibleLogicalRange(range);
      } catch {}
    };
    ts.subscribeVisibleLogicalRangeChange(onRange);
    // Best-effort initial sync.
    try {
      const cur = ts.getVisibleLogicalRange();
      if (cur && (cur as any).from != null && (cur as any).to != null) onRange(cur as any);
    } catch {}
    return () => ts.unsubscribeVisibleLogicalRangeChange(onRange);
  }, [showRsi, showMacd]);

  // Sync crosshair across panes so the vertical marker aligns (main chart drives).
  const syncingCrosshair = useRef(false);
  useEffect(() => {
    const main = chartApi.current;
    const mainSeries = chartStyle === "line" ? lineSeriesRef.current : candleSeriesRef.current;
    if (!main || !mainSeries) return;

    const rsiChart = rsiChartApi.current;
    const rsiSeries = rsiSeriesRef.current;
    const macdChart = macdChartApi.current;
    const macdSeries = macdSeriesRef.current;
    const macdSigSeries = macdSignalRef.current;

    const timeKey = (t: any): string | null => {
      if (!t) return null;
      if (typeof t === "string") return t;
      if (typeof t === "object" && "year" in t && "month" in t && "day" in t) {
        const y = String((t as any).year);
        const m = String((t as any).month).padStart(2, "0");
        const d = String((t as any).day).padStart(2, "0");
        return `${y}-${m}-${d}`;
      }
      return String(t);
    };

    const clearOthers = () => {
      try {
        if (showRsi && rsiChart) rsiChart.clearCrosshairPosition();
      } catch {}
      try {
        if (showMacd && macdChart) macdChart.clearCrosshairPosition();
      } catch {}
    };

    const onMainMove = (param: any) => {
      if (syncingCrosshair.current) return;
      syncingCrosshair.current = true;
      try {
        const t = timeKey(param?.time);
        if (!t) {
          clearOthers();
          return;
        }
        const rec = indByTime.get(t);

        if (showRsi && rsiChart && rsiSeries && rec?.rsi != null) {
          rsiChart.setCrosshairPosition(rec.rsi, t as any, rsiSeries as any);
        } else if (showRsi && rsiChart) {
          rsiChart.clearCrosshairPosition();
        }

        if (showMacd && macdChart) {
          const v = rec?.macd ?? rec?.macd_signal ?? null;
          const targetSeries = rec?.macd != null ? macdSeries : macdSigSeries;
          if (v != null && targetSeries) macdChart.setCrosshairPosition(v, t as any, targetSeries as any);
          else macdChart.clearCrosshairPosition();
        }
      } finally {
        syncingCrosshair.current = false;
      }
    };

    main.subscribeCrosshairMove(onMainMove);

    // Allow moving the crosshair from the indicator panes too (keeps it feeling unified).
    const onRsiMove = (param: any) => {
      if (!showRsi || !rsiChart) return;
      if (syncingCrosshair.current) return;
      syncingCrosshair.current = true;
      try {
        const t = timeKey(param?.time);
        if (!t) {
          main.clearCrosshairPosition();
          return;
        }
        const navVal = navByTime.get(t);
        if (navVal != null) main.setCrosshairPosition(navVal, t as any, mainSeries as any);
      } finally {
        syncingCrosshair.current = false;
      }
    };

    const onMacdMove = (param: any) => {
      if (!showMacd || !macdChart) return;
      if (syncingCrosshair.current) return;
      syncingCrosshair.current = true;
      try {
        const t = timeKey(param?.time);
        if (!t) {
          main.clearCrosshairPosition();
          return;
        }
        const navVal = navByTime.get(t);
        if (navVal != null) main.setCrosshairPosition(navVal, t as any, mainSeries as any);
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
  }, [indByTime, navByTime, showRsi, showMacd, chartStyle]);

  useEffect(() => {
    if (!macdSeriesRef.current || !macdSignalRef.current) return;
    if (!showMacd) return;
    if (!filteredBars.length) return;
    const byTime = new Map(filteredIndicators.map((r) => [r.time, r]));
    const macdData = filteredBars
      .map((p) => {
        const r = byTime.get(p.time);
        return r?.macd != null ? { time: p.time as Time, value: r.macd } : null;
      })
      .filter(Boolean) as any;
    const sigData = filteredBars
      .map((p) => {
        const r = byTime.get(p.time);
        return r?.macd_signal != null ? { time: p.time as Time, value: r.macd_signal } : null;
      })
      .filter(Boolean) as any;
    macdSeriesRef.current.setData(macdData);
    macdSignalRef.current.setData(sigData);
  }, [filteredBars, filteredIndicators, showMacd]);

  const topHoldings = useMemo(() => {
    const hs = holdings?.holdings || [];
    return hs
      // Some MF families (FoF) primarily hold other funds; show those too.
      // Also drop malformed numeric "holdings" that occasionally appear in free sources.
      .filter((h: any) => {
        const nm = String(h?.name ?? "").trim();
        if (!nm) return false;
        if (/^-?\d+(\.\d+)?$/.test(nm)) return false;
        return true;
      })
      .sort((a: any, b: any) => (Number(b.weight_pct ?? 0) - Number(a.weight_pct ?? 0)))
      .slice(0, 10);
  }, [holdings]);

  const patternItems = useMemo(() => {
    const talib = (patterns?.talib_candlestick_patterns || []) as any[];
    const native = (patterns?.candlestick_patterns || []) as any[];
    const chartP = (patterns?.chart_patterns || []) as any[];
    const out: { time: string; label: string; direction?: string; kind: string }[] = [];

    for (const p of talib) {
      const t = String(p?.time ?? "").slice(0, 10);
      const label = String(p?.name ?? "").trim();
      if (!t || !label) continue;
      out.push({ time: t, label, direction: p?.direction, kind: "candlestick" });
    }
    for (const p of native) {
      const t = String(p?.date ?? "").slice(0, 10);
      const label = String(p?.pattern ?? "").trim();
      if (!t || !label) continue;
      out.push({ time: t, label, direction: p?.direction, kind: "candlestick" });
    }
    for (const p of chartP) {
      const t = String(p?.end_date ?? p?.date ?? p?.time ?? "").slice(0, 10);
      const label = String(p?.type ?? p?.pattern ?? p?.name ?? "Chart pattern").trim();
      if (!t || !label) continue;
      out.push({ time: t, label, direction: p?.direction, kind: "chart" });
    }

    return out.sort((a, b) => b.time.localeCompare(a.time)).slice(0, 150);
  }, [patterns]);

  const focusOnTime = (t: string) => {
    if (!t) return;
    setTimeframe("MAX");
    setTimeout(() => {
      const idx = bars.findIndex((b) => b.time === t);
      if (idx < 0) return;
      const from = Math.max(0, idx - 30);
      const to = Math.min(bars.length - 1, idx + 30);
      try {
        chartApi.current?.timeScale().setVisibleLogicalRange({ from, to } as any);
      } catch {
        /**/
      }
    }, 0);
  };

  const pdfHref = `/api/mf/report/${schemeCode}`;

  const [linksOpen, setLinksOpen] = useState(false);
  const [vrUrl, setVrUrl] = useState("");
  const [msUrl, setMsUrl] = useState("");
  const [msId, setMsId] = useState("");
  const [savingLinks, setSavingLinks] = useState(false);
  // Kept as a hidden/reserve flow: no button opens this by default.
  // Users can paste the URL directly in “Edit links” and we’ll extract the SECID server-side.
  const [fixMsOpen, setFixMsOpen] = useState(false);
  const [fixMsPasteUrl, setFixMsPasteUrl] = useState("");
  const [fixingMs, setFixingMs] = useState(false);

  useEffect(() => {
    setVrUrl(scheme?.valueresearch_url ?? "");
    setMsUrl(scheme?.morningstar_url ?? "");
    setMsId(scheme?.morningstar_sec_id ?? "");
  }, [scheme?.valueresearch_url, scheme?.morningstar_url, scheme?.morningstar_sec_id]);

  useEffect(() => {
    if (!fixMsOpen) setFixMsPasteUrl("");
  }, [fixMsOpen]);

  const saveLinks = async () => {
    setSavingLinks(true);
    try {
      const res = await mfApi.updateSchemeLinks(schemeCode, {
        valueresearch_url: vrUrl || null,
        morningstar_url: msUrl || null,
        morningstar_sec_id: msId || null,
      });
      setScheme(res);
      toast.success("Links saved");
      setLinksOpen(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to save links");
    } finally {
      setSavingLinks(false);
    }
  };

  const fixMorningstar = async () => {
    const u = fixMsPasteUrl.trim();
    if (!u) return;
    if (u.includes("google.com/search")) {
      toast.error("Paste the Morningstar page link (not the Google results link).");
      return;
    }
    const sec = extractMorningstarSecId(u);
    if (!sec) {
      toast.error("Paste the full Morningstar fund page URL (it must contain “/mutualfunds/F000.../”).");
      return;
    }
    setFixingMs(true);
    try {
      const res = await mfApi.updateSchemeLinks(schemeCode, { morningstar_url: u });
      setScheme(res);
      toast.success("Morningstar factsheet link updated");
      setFixMsOpen(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to update Morningstar link");
    } finally {
      setFixingMs(false);
    }
  };

  const openMorningstar = async () => {
    if (!scheme) return;
    let href = scheme.morningstar_url || "";
    if (scheme.morningstar_link_status === "deep_factsheet") {
      window.open(href, "_blank", "noopener,noreferrer");
      return;
    }
    // If we already have a Morningstar SECID, refresh once: backend should rewrite to factsheet.
    if (scheme.morningstar_sec_id) {
      try {
        const fresh = await mfApi.scheme(schemeCode);
        setScheme(fresh);
        href = fresh.morningstar_url || href;
        if (fresh.morningstar_link_status === "deep_factsheet" && href) {
          window.open(href, "_blank", "noopener,noreferrer");
          return;
        }
      } catch {
        // Fall back to whatever we have.
      }
    }
    if (href) window.open(href, "_blank", "noopener,noreferrer");
    toast.message("Morningstar factsheet link not available yet. Use “Edit links” to paste a Morningstar factsheet URL once and it will become direct next time.");
  };

  const [enabling, setEnabling] = useState(false);
  const enableAnalysis = async () => {
    setEnabling(true);
    try {
      await mfApi.enableScheme(schemeCode);
      toast.success("Analysis enabled");
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to enable analysis");
    } finally {
      setEnabling(false);
    }
  };

  const [refreshingHoldings, setRefreshingHoldings] = useState(false);
  const refreshHoldingsNow = async () => {
    if (!scheme?.family_id) return;
    setRefreshingHoldings(true);
    try {
      const res = await mfApi.refreshHoldings(scheme.family_id);
      if (res.skipped) {
        toast.message(res.reason ?? "Holdings refresh is disabled");
        return;
      }
      if (!res.fetched) {
        toast.message(res.error ? `Holdings not available: ${res.error}` : "Holdings not available for this fund yet");
        // Still try loading any existing snapshot from DB (if present).
        try {
          const h = await mfApi.holdings(scheme.family_id);
          setHoldings(h);
        } catch {
          setHoldings(null);
        }
        return;
      }
      const h = await mfApi.holdings(scheme.family_id);
      setHoldings(h);
      toast.success("Holdings updated");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to refresh holdings");
    } finally {
      setRefreshingHoldings(false);
    }
  };

  return (
    <div className="space-y-4 w-full">
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold truncate">{scheme?.scheme_name ?? `Scheme ${schemeCode}`}</h1>
          <div className="text-xs text-muted-foreground mt-1 flex flex-wrap gap-2 items-center">
            <span>AMFI {schemeCode}</span>
            {scheme?.category ? <Badge variant="outline">{scheme.category}</Badge> : null}
            {scheme?.risk_label ? <Badge variant="outline">{scheme.risk_label}</Badge> : null}
          </div>
          {variantSuggestion ? (
            <div className="mt-2">
              <Card className="border-yellow-500/30 bg-card/70">
                <CardContent className="p-2 flex items-center justify-between gap-2 text-xs">
                  <div className="min-w-0">
                    <div className="font-medium truncate">This scheme variant looks outdated.</div>
                    <div className="text-muted-foreground truncate">
                      Latest NAV here: {scheme?.latest_nav_date} Â· Better match: AMFI {variantSuggestion.scheme_code} ({variantSuggestion.latest_nav_date})
                    </div>
                  </div>
                  <Button size="sm" onClick={switchToSuggestedVariant} disabled={switchingVariant}>
                    {switchingVariant ? "Switchingâ€¦" : "Switch"}
                  </Button>
                </CardContent>
              </Card>
            </div>
          ) : null}
        </div>
        <div className="flex gap-2">
          {!scheme?.monitored ? (
            <Button size="sm" onClick={enableAnalysis} disabled={enabling || loading}>
              {enabling ? "Enabling…" : "Enable analysis"}
            </Button>
          ) : null}
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className="h-3 w-3 mr-1" /> Refresh
          </Button>
          <Dialog open={fixMsOpen} onOpenChange={setFixMsOpen}>
            <DialogContent className="max-w-xl">
              <DialogHeader>
                <DialogTitle>Lock Morningstar Factsheet link</DialogTitle>
              </DialogHeader>
              <div className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  Morningstar doesn’t always provide a stable ID via free data sources. If you paste the fund’s Morningstar URL once,
                  we’ll extract the Morningstar code and save a direct Factsheet link for next time.
                </p>
                <div className="space-y-1.5">
                  <Label>Morningstar page URL</Label>
                  <Input
                    value={fixMsPasteUrl}
                    onChange={(e) => setFixMsPasteUrl(e.target.value)}
                    placeholder="https://www.morningstar.in/mutualfunds/..."
                  />
                </div>
                <div className="flex justify-end gap-2 pt-2">
                  <Button variant="outline" onClick={() => setFixMsOpen(false)}>
                    Not now
                  </Button>
                  <Button onClick={fixMorningstar} disabled={fixingMs || !fixMsPasteUrl.trim()}>
                    {fixingMs ? "Saving…" : "Save"}
                  </Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
          <Dialog open={linksOpen} onOpenChange={setLinksOpen}>
            <DialogTrigger
              render={
                <Button variant="outline" size="sm">
                  Edit links
                </Button>
              }
            />
            <DialogContent className="max-w-xl">
              <DialogHeader>
                <DialogTitle>External links</DialogTitle>
              </DialogHeader>
                <div className="space-y-3">
                  <div className="space-y-1.5">
                  <Label htmlFor="vr-url">ValueResearch URL</Label>
                  <Input id="vr-url" value={vrUrl} onChange={(e) => setVrUrl(e.target.value)} placeholder="https://..." />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="ms-url">Morningstar URL</Label>
                  <Input id="ms-url" value={msUrl} onChange={(e) => setMsUrl(e.target.value)} placeholder="https://..." />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="ms-secid">Morningstar SECID (optional)</Label>
                  <Input id="ms-secid" value={msId} onChange={(e) => setMsId(e.target.value)} placeholder="F00000..." />
                </div>
                <div className="flex justify-end gap-2 pt-2">
                  <Button variant="outline" onClick={() => setLinksOpen(false)}>Cancel</Button>
                  <Button onClick={saveLinks} disabled={savingLinks}>Save</Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
          {scheme?.valueresearch_url ? (
            <Link href={scheme.valueresearch_url} target="_blank">
              <Button variant="outline" size="sm">ValueResearch</Button>
            </Link>
          ) : null}
          <Button variant="outline" size="sm" onClick={openMorningstar} disabled={!scheme?.morningstar_url}>
            Morningstar
          </Button>
          <Link href={pdfHref} target="_blank">
            <Button size="sm">
              <Download className="h-3 w-3 mr-1" /> 1-Pager PDF
            </Button>
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">NAV</CardTitle>
          </CardHeader>
          <CardContent>
              <div className="flex flex-col gap-2 mb-2">
                <div className="flex flex-wrap items-center gap-2">
                  {(
                    [
                      { v: "1d" as const, label: "D" },
                      { v: "1w" as const, label: "W" },
                      { v: "1M" as const, label: "M" },
                    ] as const
                  ).map((it) => (
                    <Button
                      key={it.v}
                      size="sm"
                      variant={barTf === it.v ? "default" : "outline"}
                      onClick={() => setBarTf(it.v)}
                      title="Bar timeframe"
                    >
                      {it.label}
                    </Button>
                  ))}
                  {barTf !== "1d" ? (
                    <Badge variant="outline" className="text-[10px]" title="Weekly/Monthly uses Heikin Ashi candles">
                      Heikin Ashi
                    </Badge>
                  ) : null}
                  <span className="text-[10px] text-muted-foreground">
                    {filteredBars.length ? `${filteredBars.length} bars` : ""}
                  </span>
                  <div className="w-px h-6 bg-border/60 mx-1" />
                  {[
                    { v: "line" as const, label: "Line" },
                    { v: "candles" as const, label: "Candles" },
                    { v: "heikin" as const, label: "Heikin" },
                  ].map((it) => (
                    <Button
                      key={it.v}
                      size="sm"
                      variant={chartStyle === it.v ? "secondary" : "outline"}
                      onClick={() => setChartStyle(it.v)}
                      disabled={it.v === "heikin" && barTf === "1d"}
                      title={it.v === "heikin" && barTf === "1d" ? "Heikin Ashi applies to W/M" : "Chart style"}
                    >
                      {it.label}
                    </Button>
                  ))}
                  <div className="w-px h-6 bg-border/60 mx-1" />
                  {(["1M", "3M", "6M", "1Y", "3Y", "5Y", "10Y", "MAX"] as const).map((tf) => (
                    <Button
                      key={tf}
                      size="sm"
                      variant={timeframe === tf ? "default" : "outline"}
                    onClick={() => setTimeframe(tf)}
                  >
                    {tf}
                  </Button>
                ))}
                <div className="w-px h-6 bg-border/60 mx-1" />
                {[
                  { k: "ema20" as const, label: "EMA20" },
                  { k: "ema50" as const, label: "EMA50" },
                  { k: "rsi" as const, label: "RSI" },
                  { k: "macd" as const, label: "MACD" },
                ].map((it) => (
                  <Button
                    key={it.k}
                    size="sm"
                    variant={activeInds.has(it.k) ? "secondary" : "outline"}
                    onClick={() => {
                      setActiveInds((prev) => {
                        const n = new Set(prev);
                        if (n.has(it.k)) n.delete(it.k);
                        else n.add(it.k);
                        return n;
                      });
                    }}
                  >
                    {it.label}
                  </Button>
                ))}
              </div>
            </div>
            <div ref={chartRef} className="w-full" />
            {showRsi ? <div ref={rsiRef} className="w-full mt-3" /> : null}
            {showMacd ? <div ref={macdRef} className="w-full mt-3" /> : null}
            <div className="mt-2 text-xs text-muted-foreground flex flex-wrap gap-3">
              <span>Latest: {scheme?.latest_nav != null ? scheme.latest_nav.toFixed(4) : "—"}</span>
              <span>Date: {scheme?.latest_nav_date ?? "—"}</span>
              <span>52W High: {metrics?.is_52w_high ? "Yes" : "No"}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Returns / Risk</CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground space-y-2">
            <div className="flex justify-between"><span>1W</span><span>{metrics?.ret_7d != null ? `${metrics.ret_7d.toFixed(1)}%` : "—"}</span></div>
            <div className="flex justify-between"><span>1M</span><span>{metrics?.ret_30d != null ? `${metrics.ret_30d.toFixed(1)}%` : "—"}</span></div>
            <div className="flex justify-between"><span>3M</span><span>{metrics?.ret_90d != null ? `${metrics.ret_90d.toFixed(1)}%` : "—"}</span></div>
            <div className="flex justify-between"><span>1Y</span><span>{metrics?.ret_365d != null ? `${metrics.ret_365d.toFixed(1)}%` : "—"}</span></div>
            {scheme?.returns_json ? (
              <>
                <div className="pt-2 border-t border-border/60" />
                <div className="flex justify-between"><span>3Y (mfdata)</span><span>{(scheme.returns_json as any)?.return_3y != null ? `${Number((scheme.returns_json as any).return_3y).toFixed(1)}%` : "â€”"}</span></div>
                <div className="flex justify-between"><span>5Y (mfdata)</span><span>{(scheme.returns_json as any)?.return_5y != null ? `${Number((scheme.returns_json as any).return_5y).toFixed(1)}%` : "â€”"}</span></div>
              </>
            ) : null}
            <div className="pt-2 border-t border-border/60">
              <div className="flex justify-between"><span>Expense</span><span>{scheme?.expense_ratio != null ? `${scheme.expense_ratio.toFixed(2)}%` : "—"}</span></div>
              <div className="flex justify-between"><span>Min SIP</span><span>{scheme?.min_sip != null ? `₹${scheme.min_sip.toFixed(0)}` : "—"}</span></div>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Holdings (Latest)</CardTitle>
          </CardHeader>
          <CardContent>
            {!scheme?.family_id ? (
              <div className="space-y-2">
                <div className="text-sm text-muted-foreground">Holdings need one-time scheme enrichment.</div>
                <Button size="sm" onClick={enableAnalysis} disabled={enabling || loading}>
                  {enabling ? "Enabling…" : "Enable holdings"}
                </Button>
              </div>
            ) : !holdings ? (
              <div className="space-y-2">
                <div className="text-sm text-muted-foreground">No holdings snapshot yet.</div>
                <Button size="sm" variant="outline" onClick={refreshHoldingsNow} disabled={refreshingHoldings || loading}>
                  {refreshingHoldings ? "Fetching…" : "Fetch holdings now"}
                </Button>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-[560px] w-full text-sm">
                  <thead>
                    <tr className="text-xs text-muted-foreground">
                      <th className="text-left py-2 pr-3">Name</th>
                      <th className="text-left py-2 pr-3">Type</th>
                      <th className="text-right py-2">Weight</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topHoldings.map((h: any) => (
                      <tr key={`${h.holding_type}:${h.name}`} className="border-t border-border/60">
                        <td className="py-2 pr-3">{h.name}</td>
                        <td className="py-2 pr-3 text-xs text-muted-foreground">
                          {h.holding_type}
                          {h.ticker ? <span className="opacity-70"> · {h.ticker}</span> : null}
                        </td>
                        <td className="py-2 text-right text-xs text-muted-foreground">
                          {h.weight_pct != null ? `${Number(h.weight_pct).toFixed(2)}%` : "—"}
                        </td>
                      </tr>
                    ))}
                    {!topHoldings.length && (
                      <tr><td colSpan={3} className="py-6 text-center text-sm text-muted-foreground">No holdings.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Signals</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {signals.slice(0, 8).map((s) => (
              <div key={s.id} className="rounded-lg border border-border p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-medium">{s.signal_type}</div>
                  <Badge variant="outline">{s.confidence_score.toFixed(0)}%</Badge>
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  {s.nav_date ? `NAV date: ${s.nav_date}` : "Portfolio signal"}
                </div>
                {s.llm_analysis ? <div className="text-xs text-muted-foreground mt-2">{s.llm_analysis}</div> : null}
              </div>
            ))}
            {!signals.length && (
              <div className="space-y-2">
                <div className="text-sm text-muted-foreground">No signals yet for this scheme.</div>
                {!scheme?.monitored ? (
                  <Button size="sm" onClick={enableAnalysis} disabled={enabling || loading}>
                    {enabling ? "Enabling…" : "Enable & compute signals"}
                  </Button>
                ) : null}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-start-3">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center justify-between">
              <span>Patterns</span>
              <Button variant="outline" size="sm" onClick={() => chartApi.current?.timeScale().fitContent()}>
                Reset
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {patternItems.length === 0 ? (
              <div className="p-4 text-sm text-muted-foreground">No patterns detected for this scheme yet.</div>
            ) : (
              <div className="max-h-[360px] overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-card border-b border-border/60">
                    <tr className="text-xs text-muted-foreground">
                      <th className="text-left py-2 px-3">Date</th>
                      <th className="text-left py-2 px-3">Pattern</th>
                    </tr>
                  </thead>
                  <tbody>
                    {patternItems.slice(0, 60).map((p, i) => (
                      <tr
                        key={`${p.kind}:${p.time}:${p.label}:${i}`}
                        className="border-b border-border/40 hover:bg-muted/20 cursor-pointer"
                        onClick={() => focusOnTime(p.time)}
                        title="Click to jump"
                      >
                        <td className="py-2 px-3 text-xs text-muted-foreground whitespace-nowrap">{p.time}</td>
                        <td className="py-2 px-3">
                          <div className="flex items-center gap-2">
                            <span className={p.direction === "bullish" ? "text-green-400" : p.direction === "bearish" ? "text-red-400" : ""}>
                              {p.label}
                            </span>
                            <span className="text-[10px] text-muted-foreground">{p.kind}</span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
