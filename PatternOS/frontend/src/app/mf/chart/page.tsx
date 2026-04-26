"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  createChart,
  LineSeries,
  CandlestickSeries,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
  ColorType,
  LineStyle,
} from "lightweight-charts";
import {
  mfApi,
  type MFIndicatorRecord,
  type MFNavPoint,
  type MFOhlcBar,
  type MFPatternsResponse,
  type MFScheme,
  type MFSignal,
} from "@/lib/api";
import { collapseDailyMarkers, useMfNavIndicatorSync } from "@/lib/mf-chart-shared";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import Link from "next/link";
import {
  Download,
  RefreshCw,
  Search,
  ExternalLink,
  ChevronRight,
  TrendingUp,
  TrendingDown,
  Activity,
  PieChart,
  BarChart3,
  Globe,
  ListOrdered,
} from "lucide-react";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/v1";

type IndKey = "ema20" | "ema50" | "rsi" | "macd";

const TIMEFRAMES = [
  { value: "1M", label: "1M" },
  { value: "3M", label: "3M" },
  { value: "6M", label: "6M" },
  { value: "1Y", label: "1Y" },
  { value: "3Y", label: "3Y" },
  { value: "5Y", label: "5Y" },
  { value: "10Y", label: "10Y" },
  { value: "MAX", label: "MAX" },
] as const;

const BAR_TF = [
  { value: "1d" as const, label: "D" },
  { value: "1w" as const, label: "W" },
  { value: "1M" as const, label: "M" },
];

const CHART_STYLES = [
  { value: "candle" as const, label: "Candle" },
  { value: "heikin" as const, label: "Heikin" },
  { value: "line" as const, label: "Line" },
];

export default function MFChartToolPage() {
  // Scheme selection
  const [schemes, setSchemes] = useState<MFScheme[]>([]);
  const [selectedScheme, setSelectedScheme] = useState<MFScheme | null>(null);
  const [schemeSearch, setSchemeSearch] = useState("");
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Data states
  const [nav, setNav] = useState<MFNavPoint[]>([]);
  const [indicators, setIndicators] = useState<MFIndicatorRecord[]>([]);
  const [patterns, setPatterns] = useState<MFPatternsResponse | null>(null);
  const [metrics, setMetrics] = useState<any>(null);
  const [holdings, setHoldings] = useState<any>(null);
  const [signals, setSignals] = useState<MFSignal[]>([]);
  const [loading, setLoading] = useState(false);
  const [rawOhlc, setRawOhlc] = useState<MFOhlcBar[]>([]);

  // Chart refs
  const chartRef = useRef<HTMLDivElement>(null);
  const chartApi = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Line"> | ISeriesApi<"Candlestick"> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const ema20Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ema50Ref = useRef<ISeriesApi<"Line"> | null>(null);

  const rsiRef = useRef<HTMLDivElement>(null);
  const rsiChartApi = useRef<IChartApi | null>(null);
  const rsiSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  const macdRef = useRef<HTMLDivElement>(null);
  const macdChartApi = useRef<IChartApi | null>(null);
  const macdSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const macdSignalRef = useRef<ISeriesApi<"Line"> | null>(null);

  // UI states
  const [timeframe, setTimeframe] = useState<"1M" | "3M" | "6M" | "1Y" | "3Y" | "5Y" | "10Y" | "MAX">("MAX");
  const [barTf, setBarTf] = useState<"1d" | "1w" | "1M">("1d");
  const [chartStyle, setChartStyle] = useState<"candle" | "heikin" | "line">("line");
  const [activeInds, setActiveInds] = useState<Set<IndKey>>(new Set(["ema20", "ema50", "rsi"]));
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [activeTab, setActiveTab] = useState<"overview" | "holdings" | "signals" | "patterns" | "links">("overview");

  const showRsi = activeInds.has("rsi");
  const showMacd = activeInds.has("macd");

  // Load schemes list
  useEffect(() => {
    void mfApi.schemes(false, "").then((s) => {
      setSchemes(s);
      if (s.length > 0 && !selectedScheme) {
        setSelectedScheme(s[0]);
      }
    });
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    if (!dropdownOpen) return;
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [dropdownOpen]);

  // Filtered schemes
  const filteredSchemes = useMemo(() => {
    if (!schemeSearch) return schemes.slice(0, 50);
    const q = schemeSearch.toLowerCase();
    return schemes
      .filter(
        (s) =>
          (s.scheme_name?.toLowerCase().includes(q) ?? false) ||
          (s.amc_name?.toLowerCase().includes(q) ?? false) ||
          (s.category?.toLowerCase().includes(q) ?? false) ||
          String(s.scheme_code).includes(q)
      )
      .slice(0, 50);
  }, [schemes, schemeSearch]);

  // Load scheme data (NAV + resampled OHLC + tf-aligned indicators/patterns)
  const loadSchemeData = useCallback(async (schemeCode: number) => {
    setLoading(true);
    try {
      const navLimit = 2500;
      const indLimit = barTf === "1M" ? 8200 : barTf === "1w" ? 3800 : 2600;
      const emptyOhlc = { scheme_code: schemeCode, tf: barTf, style: chartStyle, series: [] as MFOhlcBar[] };
      const [s, n, ohlcRes, inds, pats, m, sigs] = await Promise.all([
        mfApi.scheme(schemeCode),
        mfApi.nav(schemeCode, navLimit),
        mfApi.ohlc(schemeCode, barTf, chartStyle, navLimit).catch(() => emptyOhlc),
        mfApi.indicators(schemeCode, indLimit, barTf),
        mfApi.patterns(schemeCode, 220, barTf),
        mfApi.metrics(schemeCode),
        mfApi.signals("all", 400),
      ]);
      setSelectedScheme(s);
      setNav(n);
      setRawOhlc(ohlcRes.series ?? []);
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
  }, [barTf, chartStyle]);

  useEffect(() => {
    if (selectedScheme?.scheme_code) {
      void loadSchemeData(selectedScheme.scheme_code);
    }
  }, [selectedScheme?.scheme_code, loadSchemeData]);

  // Filter data by timeframe
  const filteredNav = useMemo(() => {
    if (timeframe === "MAX") return nav;
    if (!nav.length) return nav;
    const end = new Date(nav[nav.length - 1].nav_date);
    const start = new Date(end);
    if (timeframe === "1M") start.setMonth(start.getMonth() - 1);
    if (timeframe === "3M") start.setMonth(start.getMonth() - 3);
    if (timeframe === "6M") start.setMonth(start.getMonth() - 6);
    if (timeframe === "1Y") start.setFullYear(start.getFullYear() - 1);
    if (timeframe === "3Y") start.setFullYear(start.getFullYear() - 3);
    if (timeframe === "5Y") start.setFullYear(start.getFullYear() - 5);
    if (timeframe === "10Y") start.setFullYear(start.getFullYear() - 10);
    return nav.filter((p) => new Date(p.nav_date) >= start);
  }, [nav, timeframe]);

  const filteredOhlc = useMemo(() => {
    if (timeframe === "MAX" || !rawOhlc.length) return rawOhlc;
    const end = new Date(rawOhlc[rawOhlc.length - 1].time);
    const start = new Date(end);
    if (timeframe === "1M") start.setMonth(start.getMonth() - 1);
    if (timeframe === "3M") start.setMonth(start.getMonth() - 3);
    if (timeframe === "6M") start.setMonth(start.getMonth() - 6);
    if (timeframe === "1Y") start.setFullYear(start.getFullYear() - 1);
    if (timeframe === "3Y") start.setFullYear(start.getFullYear() - 3);
    if (timeframe === "5Y") start.setFullYear(start.getFullYear() - 5);
    if (timeframe === "10Y") start.setFullYear(start.getFullYear() - 10);
    return rawOhlc.filter((p) => new Date(p.time) >= start);
  }, [rawOhlc, timeframe]);

  const chartWindow = useMemo(() => {
    if (filteredOhlc.length)
      return { start: filteredOhlc[0].time, end: filteredOhlc[filteredOhlc.length - 1].time };
    if (filteredNav.length)
      return { start: filteredNav[0].nav_date, end: filteredNav[filteredNav.length - 1].nav_date };
    return null;
  }, [filteredOhlc, filteredNav]);

  const filteredIndicators = useMemo(() => {
    if (!indicators.length || !chartWindow) return [];
    const start = new Date(chartWindow.start);
    const end = new Date(chartWindow.end);
    return indicators.filter((r) => {
      const d = new Date(r.time);
      return !Number.isNaN(d.getTime()) && d >= start && d <= end;
    });
  }, [indicators, chartWindow]);

  const chartTimes = useMemo(() => {
    if (filteredOhlc.length) return filteredOhlc.map((o) => o.time as Time);
    return filteredNav.map((p) => p.nav_date as Time);
  }, [filteredOhlc, filteredNav]);

  const priceByTime = useMemo(() => {
    const m = new Map<string, number>();
    if (filteredOhlc.length) for (const o of filteredOhlc) m.set(String(o.time), o.close);
    else for (const p of filteredNav) m.set(String(p.nav_date), p.nav);
    return m;
  }, [filteredOhlc, filteredNav]);

  const indByTime = useMemo(() => {
    return new Map(filteredIndicators.map((r) => [r.time, r]));
  }, [filteredIndicators]);

  const patternSidebarRows = useMemo(() => {
    if (!patterns) return [];
    const chart = (patterns.chart_patterns || []) as { end_date?: string; time?: string; name?: string; pattern?: string; direction?: string }[];
    const talib = (patterns.talib_candlestick_patterns || []) as { time?: string; name?: string; direction?: string }[];
    const native = (patterns.candlestick_patterns || []) as { date?: string; pattern?: string; direction?: string }[];
    const rows: { t: string; label: string; direction?: string; kind: string }[] = [];
    for (const p of chart) {
      const t = p.end_date ?? p.time;
      if (!t) continue;
      rows.push({ t: String(t), label: String(p.name ?? p.pattern ?? "chart"), direction: p.direction, kind: "chart" });
    }
    for (const p of talib) {
      if (!p?.time) continue;
      rows.push({ t: String(p.time), label: String(p.name), direction: p.direction, kind: "talib" });
    }
    for (const p of native) {
      if (!p?.date) continue;
      rows.push({ t: String(p.date), label: String(p.pattern), direction: p.direction, kind: "native" });
    }
    rows.sort((a, b) => a.t.localeCompare(b.t));
    return rows;
  }, [patterns]);

  const jumpToTime = useCallback(
    (t: string) => {
      const chart = chartApi.current;
      if (!chart || !chartTimes.length) return;
      const times = chartTimes.map((x) => String(x));
      const idx = times.indexOf(t);
      if (idx < 0) return;
      chart.timeScale().setVisibleLogicalRange({
        from: Math.max(0, idx - 30),
        to: Math.min(times.length - 1, idx + 30),
      });
    },
    [chartTimes]
  );

  // Init main chart (rebuild when line vs candles/heikin — series type differs)
  useEffect(() => {
    if (!chartRef.current) return;
    const c = createChart(chartRef.current, {
      layout: { textColor: "#e5e7eb", background: { type: ColorType.Solid, color: "transparent" } },
      grid: { vertLines: { color: "rgba(148,163,184,0.08)" }, horzLines: { color: "rgba(148,163,184,0.08)" } },
      rightPriceScale: { borderColor: "rgba(148,163,184,0.15)", minimumWidth: 72 },
      timeScale: { borderColor: "rgba(148,163,184,0.15)", visible: false },
      height: 320,
    });
    const s =
      chartStyle === "line"
        ? c.addSeries(LineSeries, { color: "#38bdf8", lineWidth: 2, priceLineVisible: false, lastValueVisible: true })
        : c.addSeries(CandlestickSeries, {
            upColor: "#22c55e",
            downColor: "#ef4444",
            borderVisible: false,
            wickUpColor: "#22c55e",
            wickDownColor: "#ef4444",
            priceLineVisible: false,
            lastValueVisible: true,
          });
    const e20 = c.addSeries(LineSeries, { color: "#22c55e", lineWidth: 1, priceLineVisible: false, lastValueVisible: false, lineStyle: LineStyle.Dotted });
    const e50 = c.addSeries(LineSeries, { color: "#3b82f6", lineWidth: 1, priceLineVisible: false, lastValueVisible: false, lineStyle: LineStyle.Dotted });
    const markers = createSeriesMarkers(s);
    chartApi.current = c;
    seriesRef.current = s;
    ema20Ref.current = e20;
    ema50Ref.current = e50;
    markersRef.current = markers;
    const ro = new ResizeObserver(() => {
      if (!chartRef.current) return;
      c.applyOptions({ width: chartRef.current.clientWidth });
    });
    ro.observe(chartRef.current);
    return () => {
      ro.disconnect();
      c.remove();
      chartApi.current = null;
      seriesRef.current = null;
      ema20Ref.current = null;
      ema50Ref.current = null;
      markersRef.current = null;
    };
  }, [chartStyle]);

  // Set main series data (OHLC when available; else NAV line)
  useEffect(() => {
    const ser = seriesRef.current;
    if (!ser || !chartApi.current) return;
    if (chartStyle === "line") {
      if (filteredOhlc.length) {
        (ser as ISeriesApi<"Line">).setData(filteredOhlc.map((o) => ({ time: o.time as Time, value: o.close })));
      } else if (filteredNav.length) {
        (ser as ISeriesApi<"Line">).setData(filteredNav.map((p) => ({ time: p.nav_date as Time, value: p.nav })));
      } else {
        (ser as ISeriesApi<"Line">).setData([]);
      }
    } else if (filteredOhlc.length) {
      (ser as ISeriesApi<"Candlestick">).setData(
        filteredOhlc.map((o) => ({
          time: o.time as Time,
          open: o.open,
          high: o.high,
          low: o.low,
          close: o.close,
        }))
      );
    } else {
      (ser as ISeriesApi<"Candlestick">).setData([]);
    }
    chartApi.current.timeScale().fitContent();
  }, [filteredOhlc, filteredNav, chartStyle]);

  useEffect(() => {
    if (!chartTimes.length) return;
    const times = chartTimes;
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
  }, [chartTimes, filteredIndicators, activeInds]);

  // Signal + pattern markers (collapsed per day to reduce overlap)
  useEffect(() => {
    if (!markersRef.current) return;
    const markers: SeriesMarker<Time>[] = [];

    const min = chartWindow?.start ?? (filteredNav.length ? filteredNav[0].nav_date : null);
    const max = chartWindow?.end ?? (filteredNav.length ? filteredNav[filteredNav.length - 1].nav_date : null);

    const signalsByDate = new Map<string, MFSignal[]>();
    for (const s of signals) {
      if (!s.nav_date) continue;
      if (min && max && (s.nav_date < min || s.nav_date > max)) continue;
      if (!signalsByDate.has(s.nav_date)) {
        signalsByDate.set(s.nav_date, []);
      }
      signalsByDate.get(s.nav_date)!.push(s);
    }

    signalsByDate.forEach((sigs, date) => {
      sigs.forEach((s, idx) => {
        const col = s.confidence_score >= 80 ? "#22c55e" : s.confidence_score >= 70 ? "#f59e0b" : "#ef4444";
        const isOverlap = sigs.length > 1;
        markers.push({
          time: date as Time,
          position: idx % 2 === 0 ? "aboveBar" : "belowBar",
          color: col,
          shape: isOverlap ? "square" : "circle",
          text: isOverlap ? `${s.signal_type.slice(0, 8)}(${sigs.length})` : s.signal_type.slice(0, 12),
          size: isOverlap ? 2 : 1,
        });
      });
    });

    const chartPats = (patterns?.chart_patterns || []) as { end_date?: string; time?: string; name?: string; pattern?: string; direction?: string }[];
    const talib = (patterns?.talib_candlestick_patterns || []) as any[];
    const native = (patterns?.candlestick_patterns || []) as any[];
    const allPats = [
      ...chartPats.map((p) => ({
        time: p?.end_date ?? p?.time,
        label: p?.name ?? p?.pattern,
        direction: p?.direction,
      })),
      ...talib.map((p) => ({ time: p?.time, label: p?.name, direction: p?.direction })),
      ...native.map((p) => ({ time: p?.date, label: p?.pattern, direction: p?.direction })),
    ].filter((p) => p.time && p.label);

    const patInWindow = allPats.filter((p) => !min || !max || (String(p.time) >= min && String(p.time) <= max));
    patInWindow.sort((a, b) => String(a.time).localeCompare(String(b.time)));
    for (const p of patInWindow) {
      const bullish = p.direction === "bullish";
      markers.push({
        time: p.time as Time,
        position: bullish ? "belowBar" : "aboveBar",
        color: bullish ? "#22c55e" : "#ef4444",
        shape: bullish ? "arrowUp" : "arrowDown",
        text: String(p.label || "").slice(0, 12),
      });
    }
    markersRef.current.setMarkers(collapseDailyMarkers(markers));
  }, [signals, patterns, filteredNav, chartWindow]);

  // RSI chart
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
      layout: { textColor: "#e5e7eb", background: { type: ColorType.Solid, color: "transparent" } },
      grid: { vertLines: { color: "rgba(148,163,184,0.06)" }, horzLines: { color: "rgba(148,163,184,0.06)" } },
      rightPriceScale: { borderColor: "rgba(148,163,184,0.15)", minimumWidth: 72 },
      timeScale: { borderColor: "rgba(148,163,184,0.15)", visible: !showMacd },
      handleScroll: false,
      handleScale: false,
      height: 140,
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
  }, [showRsi, showMacd]);

  useEffect(() => {
    if (!rsiSeriesRef.current) return;
    if (!showRsi) return;
    if (!chartTimes.length) return;
    const byTime = new Map(filteredIndicators.map((r) => [r.time, r]));
    const data = chartTimes
      .map((t) => {
        const r = byTime.get(String(t));
        return r?.rsi != null ? { time: t, value: r.rsi } : null;
      })
      .filter(Boolean) as any;
    rsiSeriesRef.current.setData(data);
  }, [chartTimes, filteredIndicators, showRsi]);

  // MACD chart
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
      layout: { textColor: "#e5e7eb", background: { type: ColorType.Solid, color: "transparent" } },
      grid: { vertLines: { color: "rgba(148,163,184,0.06)" }, horzLines: { color: "rgba(148,163,184,0.06)" } },
      rightPriceScale: { borderColor: "rgba(148,163,184,0.15)", minimumWidth: 72 },
      timeScale: { borderColor: "rgba(148,163,184,0.15)", visible: true },
      handleScroll: false,
      handleScale: false,
      height: 160,
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

  // Sync time scales
  useEffect(() => {
    const main = chartApi.current;
    if (!main) return;
    const ts = main.timeScale();
    const onRange = (range: { from: number; to: number } | null) => {
      if (!range || range.from == null || range.to == null) return;
      try {
        if (showRsi && rsiChartApi.current) rsiChartApi.current.timeScale().setVisibleLogicalRange(range);
      } catch {}
      try {
        if (showMacd && macdChartApi.current) macdChartApi.current.timeScale().setVisibleLogicalRange(range);
      } catch {}
    };
    ts.subscribeVisibleLogicalRangeChange(onRange);
    try {
      const cur = ts.getVisibleLogicalRange();
      if (cur && (cur as any).from != null && (cur as any).to != null) onRange(cur as any);
    } catch {}
    return () => ts.unsubscribeVisibleLogicalRangeChange(onRange);
  }, [showRsi, showMacd, chartTimes.length, barTf, chartStyle]);

  useEffect(() => {
    if (!macdSeriesRef.current || !macdSignalRef.current) return;
    if (!showMacd) return;
    if (!chartTimes.length) return;
    const byTime = new Map(filteredIndicators.map((r) => [r.time, r]));
    const macdData = chartTimes
      .map((t) => {
        const r = byTime.get(String(t));
        return r?.macd != null ? { time: t, value: r.macd } : null;
      })
      .filter(Boolean) as any;
    const sigData = chartTimes
      .map((t) => {
        const r = byTime.get(String(t));
        return r?.macd_signal != null ? { time: t, value: r.macd_signal } : null;
      })
      .filter(Boolean) as any;
    macdSeriesRef.current.setData(macdData);
    macdSignalRef.current.setData(sigData);
  }, [chartTimes, filteredIndicators, showMacd]);

  const chartSyncKey = `${barTf}|${chartStyle}|${showRsi}|${showMacd}|${chartTimes.length}`;
  useMfNavIndicatorSync({
    indByTime,
    priceByTime,
    showRsi,
    showMacd,
    layoutKey: chartSyncKey,
    chartApiRef: chartApi,
    mainSeriesRef: seriesRef,
    rsiChartApiRef: rsiChartApi,
    rsiSeriesRef: rsiSeriesRef,
    macdChartApiRef: macdChartApi,
    macdSeriesRef: macdSeriesRef,
    macdSignalRef: macdSignalRef,
  });

  // Holdings
  const topHoldings = useMemo(() => {
    const hs = holdings?.holdings || [];
    return hs
      .filter((h: any) => {
        const nm = String(h?.name ?? "").trim();
        if (!nm) return false;
        if (/^-?\d+(\.\d+)?$/.test(nm)) return false;
        return true;
      })
      .sort((a: any, b: any) => (Number(b.weight_pct ?? 0) - Number(a.weight_pct ?? 0)))
      .slice(0, 10);
  }, [holdings]);

  // PDF download
  const pdfHref = selectedScheme ? `/api/mf/report/${selectedScheme.scheme_code}` : null;

  const yahooFinanceHref = useMemo(() => {
    if (!selectedScheme) return null;
    if (selectedScheme.yahoo_finance_url?.trim()) return selectedScheme.yahoo_finance_url.trim();
    const sym = selectedScheme.yahoo_finance_symbol?.trim();
    if (sym) return `https://finance.yahoo.com/quote/${encodeURIComponent(sym)}`;
    const q = encodeURIComponent(selectedScheme.scheme_name || String(selectedScheme.scheme_code));
    return `https://finance.yahoo.com/search?q=${q}`;
  }, [selectedScheme]);

  // Refresh data
  const refreshData = () => {
    if (selectedScheme?.scheme_code) {
      void loadSchemeData(selectedScheme.scheme_code);
    }
  };

  // Enable analysis
  const [enabling, setEnabling] = useState(false);
  const enableAnalysis = async () => {
    if (!selectedScheme?.scheme_code) return;
    setEnabling(true);
    try {
      await mfApi.enableScheme(selectedScheme.scheme_code);
      toast.success("Analysis enabled");
      await refreshData();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to enable analysis");
    } finally {
      setEnabling(false);
    }
  };

  return (
    <div className="flex h-[calc(100vh-4rem)] w-full -mx-6 -mt-6 overflow-hidden">
      {/* Main chart area */}
      <div className="flex flex-col flex-1 min-w-0 bg-[#0a0a0c]">
        {/* Toolbar */}
        <div
          className="flex items-center gap-2 px-3 py-2 border-b border-border bg-card shrink-0 flex-wrap"
          data-testid="mf-chart-toolbar"
        >
          {/* Scheme selector */}
          <div className="relative" ref={dropdownRef}>
            <button
              onClick={() => { setDropdownOpen((o) => !o); setSchemeSearch(""); }}
              className="h-8 px-3 flex items-center justify-between gap-2 rounded-md border border-border bg-background text-sm hover:bg-muted/50 transition-colors min-w-[280px]"
            >
              <span className="truncate font-medium">
                {selectedScheme ? selectedScheme.scheme_name : "Select Scheme..."}
              </span>
              <Search className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            </button>

            {dropdownOpen && (
              <div className="absolute top-10 left-0 z-50 w-[400px] rounded-md border border-border bg-popover shadow-xl flex flex-col overflow-hidden">
                <div className="flex items-center gap-2 px-3 py-2 border-b border-border">
                  <Search className="h-4 w-4 text-muted-foreground shrink-0" />
                  <input
                    autoFocus
                    type="text"
                    value={schemeSearch}
                    onChange={(e) => setSchemeSearch(e.target.value)}
                    placeholder="Search scheme name, AMC, category..."
                    className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                  />
                  {schemeSearch && (
                    <button onClick={() => setSchemeSearch("")} className="text-muted-foreground hover:text-foreground">
                      ×
                    </button>
                  )}
                </div>
                <div className="overflow-y-auto max-h-80">
                  {filteredSchemes.length === 0 ? (
                    <div className="text-sm text-muted-foreground text-center py-6">No schemes found</div>
                  ) : (
                    filteredSchemes.map((s) => (
                      <button
                        key={s.scheme_code}
                        onClick={() => {
                          setSelectedScheme(s);
                          setDropdownOpen(false);
                        }}
                        className={`w-full flex flex-col gap-0.5 px-3 py-2 text-left hover:bg-muted/50 transition-colors border-b border-border/40 last:border-0 ${
                          s.scheme_code === selectedScheme?.scheme_code ? "bg-primary/10" : ""
                        }`}
                      >
                        <span className="font-medium text-sm truncate">{s.scheme_name}</span>
                        <span className="text-xs text-muted-foreground">
                          AMFI {s.scheme_code} · {s.amc_name} · {s.category}
                        </span>
                      </button>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Bar timeframe (NAV resampling: D / W / M) */}
          <div className="flex gap-0.5 border border-border/60 rounded-md p-0.5" title="Bar timeframe (OHLC from NAV)">
            {BAR_TF.map((b) => (
              <Button
                key={b.value}
                size="sm"
                variant={barTf === b.value ? "default" : "ghost"}
                className="h-7 px-2 text-xs min-w-[2rem]"
                data-testid={`mf-bar-tf-${b.value}`}
                onClick={() => setBarTf(b.value)}
              >
                {b.label}
              </Button>
            ))}
          </div>

          <div className="flex gap-0.5 border border-border/60 rounded-md p-0.5" title="Main pane style">
            {CHART_STYLES.map((st) => (
              <Button
                key={st.value}
                size="sm"
                variant={chartStyle === st.value ? "secondary" : "ghost"}
                className="h-7 px-2 text-xs"
                data-testid={`mf-chart-style-${st.value}`}
                onClick={() => setChartStyle(st.value)}
              >
                {st.label}
              </Button>
            ))}
          </div>

          {/* Timeframes */}
          <div className="flex gap-0.5">
            {TIMEFRAMES.map((tf) => (
              <Button
                key={tf.value}
                size="sm"
                variant={timeframe === tf.value ? "default" : "ghost"}
                className="h-7 px-2 text-xs"
                onClick={() => setTimeframe(tf.value)}
              >
                {tf.label}
              </Button>
            ))}
          </div>

          <div className="w-px h-6 bg-border/60 mx-1" />

          {/* Indicators */}
          {[
            { k: "ema20" as const, label: "EMA20" },
            { k: "ema50" as const, label: "EMA50" },
            { k: "rsi" as const, label: "RSI" },
            { k: "macd" as const, label: "MACD" },
          ].map((it) => (
            <Button
              key={it.k}
              size="sm"
              variant={activeInds.has(it.k) ? "secondary" : "ghost"}
              className="h-7 px-2 text-xs"
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

          <div className="flex-1" />

          {/* Actions */}
          <Button variant="outline" size="sm" onClick={refreshData} disabled={loading} className="h-7">
            <RefreshCw className={`h-3.5 w-3.5 mr-1 ${loading ? "animate-spin" : ""}`} /> Refresh
          </Button>

          {pdfHref && (
            <Link href={pdfHref} target="_blank">
              <Button size="sm" className="h-7">
                <Download className="h-3.5 w-3.5 mr-1" /> 1-Pager PDF
              </Button>
            </Link>
          )}

          <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => setSidebarOpen((o) => !o)}>
            <ChevronRight className={`h-4 w-4 transition-transform ${sidebarOpen ? "rotate-180" : ""}`} />
          </Button>
        </div>

        {/* Chart area */}
        <div className="flex-1 min-h-0 flex flex-col relative overflow-hidden">
          <div ref={chartRef} className="w-full flex-1 min-h-0" data-testid="mf-main-chart" />

          {showRsi && (
            <div className="shrink-0 border-t border-border" style={{ height: "120px" }} data-testid="mf-rsi-pane">
              <div className="px-2 py-0.5 text-[10px] text-violet-400 font-medium bg-card border-b border-border">RSI (14)</div>
              <div ref={rsiRef} className="w-full" style={{ height: "calc(100% - 20px)" }} />
            </div>
          )}

          {showMacd && (
            <div className="shrink-0 border-t border-border" style={{ height: "120px" }}>
              <div className="px-2 py-0.5 text-[10px] text-blue-400 font-medium bg-card border-b border-border">MACD</div>
              <div ref={macdRef} className="w-full" style={{ height: "calc(100% - 20px)" }} />
            </div>
          )}
        </div>

        {/* Bottom info bar */}
        <div className="shrink-0 border-t border-border bg-card px-3 py-2 flex items-center gap-4 text-xs" data-testid="mf-nav-banner">
          <span className="font-medium">{selectedScheme?.scheme_name}</span>
          <span className="text-muted-foreground">AMFI {selectedScheme?.scheme_code}</span>
          <span className="text-muted-foreground">NAV: {selectedScheme?.latest_nav?.toFixed(4) ?? "—"}</span>
          <span className="text-muted-foreground">Date: {selectedScheme?.latest_nav_date ?? "—"}</span>
          {metrics?.is_52w_high && <Badge variant="outline" className="text-[10px]">52W High</Badge>}
          {signals.length > 0 && (
            <Badge variant="outline" className="text-[10px] text-yellow-400 border-yellow-500/30">
              {signals.length} Signal{signals.length > 1 ? "s" : ""}
            </Badge>
          )}
        </div>
      </div>

      {/* Right sidebar */}
      {sidebarOpen && (
        <div className="w-80 shrink-0 border-l border-border bg-card flex flex-col overflow-hidden">
          {/* Tabs */}
          <div className="flex border-b border-border shrink-0">
            {[
              { key: "overview", label: "Overview", icon: Activity },
              { key: "holdings", label: "Holdings", icon: PieChart },
              { key: "signals", label: "Signals", icon: TrendingUp },
              { key: "patterns", label: "Patterns", icon: ListOrdered },
              { key: "links", label: "Links", icon: Globe },
            ].map((tab) => (
              <button
                key={tab.key}
                type="button"
                data-testid={
                  tab.key === "patterns" ? "mf-patterns-tab" : tab.key === "links" ? "mf-links-tab" : undefined
                }
                onClick={() => setActiveTab(tab.key as typeof activeTab)}
                className={`flex-1 py-2 text-[11px] font-medium transition-colors flex items-center justify-center gap-1 ${
                  activeTab === tab.key
                    ? "text-primary border-b-2 border-primary"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <tab.icon className="h-3.5 w-3.5" />
                {tab.label}
              </button>
            ))}
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-3 space-y-3">
            {/* Overview Tab */}
            {activeTab === "overview" && (
              <>
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <BarChart3 className="h-4 w-4" /> Returns / Risk
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="text-xs space-y-2">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">1W</span>
                      <span>{metrics?.ret_7d != null ? `${metrics.ret_7d.toFixed(1)}%` : "—"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">1M</span>
                      <span>{metrics?.ret_30d != null ? `${metrics.ret_30d.toFixed(1)}%` : "—"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">3M</span>
                      <span>{metrics?.ret_90d != null ? `${metrics.ret_90d.toFixed(1)}%` : "—"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">1Y</span>
                      <span>{metrics?.ret_365d != null ? `${metrics.ret_365d.toFixed(1)}%` : "—"}</span>
                    </div>
                    {selectedScheme?.returns_json && (
                      <>
                        <div className="pt-2 border-t border-border/60" />
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">3Y (mfdata)</span>
                          <span>{(selectedScheme.returns_json as any)?.return_3y != null ? `${Number((selectedScheme.returns_json as any).return_3y).toFixed(1)}%` : "—"}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">5Y (mfdata)</span>
                          <span>{(selectedScheme.returns_json as any)?.return_5y != null ? `${Number((selectedScheme.returns_json as any).return_5y).toFixed(1)}%` : "—"}</span>
                        </div>
                      </>
                    )}
                    <div className="pt-2 border-t border-border/60">
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Expense</span>
                        <span>{selectedScheme?.expense_ratio != null ? `${selectedScheme.expense_ratio.toFixed(2)}%` : "—"}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Min SIP</span>
                        <span>{selectedScheme?.min_sip != null ? `₹${selectedScheme.min_sip.toFixed(0)}` : "—"}</span>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">Scheme Info</CardTitle>
                  </CardHeader>
                  <CardContent className="text-xs space-y-2">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Category</span>
                      <span>{selectedScheme?.category ?? "—"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">AMC</span>
                      <span>{selectedScheme?.amc_name ?? "—"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Risk</span>
                      <span>{selectedScheme?.risk_label ?? "—"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Plan</span>
                      <span>{selectedScheme?.plan_type ?? "—"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Option</span>
                      <span>{selectedScheme?.option_type ?? "—"}</span>
                    </div>
                  </CardContent>
                </Card>

                {!selectedScheme?.monitored && (
                  <Button size="sm" onClick={enableAnalysis} disabled={enabling || loading} className="w-full">
                    {enabling ? "Enabling…" : "Enable Analysis"}
                  </Button>
                )}
              </>
            )}

            {/* Holdings Tab */}
            {activeTab === "holdings" && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <PieChart className="h-4 w-4" /> Holdings
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {!selectedScheme?.family_id ? (
                    <div className="text-sm text-muted-foreground">Holdings need scheme enrichment.</div>
                  ) : !holdings ? (
                    <div className="text-sm text-muted-foreground">No holdings snapshot yet.</div>
                  ) : (
                    <div className="space-y-2">
                      <div className="text-xs text-muted-foreground mb-2">
                        Family {selectedScheme.family_id} · Month {holdings.month}
                      </div>
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="text-muted-foreground">
                            <th className="text-left py-1">Name</th>
                            <th className="text-right py-1">Weight</th>
                          </tr>
                        </thead>
                        <tbody>
                          {topHoldings.map((h: any) => (
                            <tr key={`${h.holding_type}:${h.name}`} className="border-t border-border/40">
                              <td className="py-1.5 pr-2">
                                <div className="truncate max-w-[180px]">{h.name}</div>
                                <div className="text-[10px] text-muted-foreground">{h.holding_type}</div>
                              </td>
                              <td className="py-1.5 text-right text-muted-foreground">
                                {h.weight_pct != null ? `${Number(h.weight_pct).toFixed(2)}%` : "—"}
                              </td>
                            </tr>
                          ))}
                          {!topHoldings.length && (
                            <tr>
                              <td colSpan={2} className="py-4 text-center text-muted-foreground">No holdings.</td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {/* Signals Tab */}
            {activeTab === "signals" && (
              <div className="space-y-2">
                {signals.length === 0 ? (
                  <div className="text-sm text-muted-foreground text-center py-6">No signals yet.</div>
                ) : (
                  signals.map((s) => (
                    <Card key={s.id} className={s.confidence_score >= 80 ? "border-green-500/30" : ""}>
                      <CardContent className="p-3">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm font-medium">{s.signal_type}</span>
                          <Badge variant="outline" className={s.confidence_score >= 80 ? "text-green-400" : s.confidence_score >= 70 ? "text-yellow-400" : ""}>
                            {s.confidence_score.toFixed(0)}%
                          </Badge>
                        </div>
                        <div className="text-xs text-muted-foreground mt-1">
                          {s.nav_date ? `NAV date: ${s.nav_date}` : "Portfolio signal"}
                        </div>
                        {s.llm_analysis && (
                          <div className="text-xs text-muted-foreground mt-2 line-clamp-3">{s.llm_analysis}</div>
                        )}
                      </CardContent>
                    </Card>
                  ))
                )}
              </div>
            )}

            {/* Patterns Tab */}
            {activeTab === "patterns" && (
              <div className="space-y-2" data-testid="mf-patterns-sidebar">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs text-muted-foreground">
                    {patternSidebarRows.length} pattern{patternSidebarRows.length === 1 ? "" : "s"} (window)
                  </span>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-7 text-xs"
                    data-testid="mf-patterns-reset-range"
                    onClick={() => chartApi.current?.timeScale().fitContent()}
                  >
                    Reset range
                  </Button>
                </div>
                {patternSidebarRows.length === 0 ? (
                  <div className="text-sm text-muted-foreground text-center py-6">No patterns in this window.</div>
                ) : (
                  <div className="space-y-1 max-h-[calc(100vh-12rem)] overflow-y-auto pr-1">
                    {patternSidebarRows.map((row, i) => (
                      <button
                        type="button"
                        key={`${row.kind}-${row.t}-${i}`}
                        data-testid="mf-pattern-row"
                        className="w-full text-left rounded-md border border-border/60 px-2 py-1.5 hover:bg-muted/40 transition-colors"
                        onClick={() => jumpToTime(row.t)}
                      >
                        <div className="text-[11px] font-medium truncate">{row.label}</div>
                        <div className="text-[10px] text-muted-foreground flex justify-between gap-2">
                          <span>{row.t}</span>
                          <span className="shrink-0">{row.kind}</span>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Links Tab */}
            {activeTab === "links" && (
              <div className="space-y-3">
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">External Links</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {yahooFinanceHref && (
                      <Link href={yahooFinanceHref} target="_blank" rel="noopener noreferrer">
                        <Button variant="default" size="sm" className="w-full" data-testid="mf-links-yahoo">
                          <ExternalLink className="h-3.5 w-3.5 mr-2" /> Yahoo Finance
                        </Button>
                      </Link>
                    )}
                    {selectedScheme?.valueresearch_url ? (
                      <Link href={selectedScheme.valueresearch_url} target="_blank" className="flex items-center gap-2 text-sm hover:underline">
                        <ExternalLink className="h-3.5 w-3.5" /> ValueResearch
                      </Link>
                    ) : (
                      <div className="text-sm text-muted-foreground">No ValueResearch link</div>
                    )}
                    {selectedScheme?.morningstar_url ? (
                      <Link href={selectedScheme.morningstar_url} target="_blank" className="flex items-center gap-2 text-sm hover:underline">
                        <ExternalLink className="h-3.5 w-3.5" /> Morningstar
                      </Link>
                    ) : (
                      <div className="text-sm text-muted-foreground">No Morningstar link</div>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">Quick Actions</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <Link href={`/mf/schemes/${selectedScheme?.scheme_code}`} target="_blank">
                      <Button variant="outline" size="sm" className="w-full">
                        Open Detail Page <ExternalLink className="h-3.5 w-3.5 ml-1" />
                      </Button>
                    </Link>
                    {pdfHref && (
                      <Link href={pdfHref} target="_blank">
                        <Button variant="outline" size="sm" className="w-full">
                          Download PDF <Download className="h-3.5 w-3.5 ml-1" />
                        </Button>
                      </Link>
                    )}
                  </CardContent>
                </Card>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
