"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { mfApi, type MFIndicatorRecord, type MFOhlcBar, type MFNavPoint, type MFPatternsResponse, type MFScheme, type MFSignal } from "@/lib/api";
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
} from "lucide-react";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/v1";

type IndKey = "ema20" | "ema50" | "rsi" | "macd";
type ChartStyle = "candles" | "heikin" | "line";

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

export default function MFChartToolPage() {
  // Scheme selection
  const [schemes, setSchemes] = useState<MFScheme[]>([]);
  const [selectedScheme, setSelectedScheme] = useState<MFScheme | null>(null);
  const [schemeSearch, setSchemeSearch] = useState("");
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Data states
  const [nav, setNav] = useState<MFNavPoint[]>([]);
  const [bars, setBars] = useState<MFOhlcBar[]>([]);
  const [indicators, setIndicators] = useState<MFIndicatorRecord[]>([]);
  const [patterns, setPatterns] = useState<MFPatternsResponse | null>(null);
  const [metrics, setMetrics] = useState<any>(null);
  const [holdings, setHoldings] = useState<any>(null);
  const [signals, setSignals] = useState<MFSignal[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshingHoldings, setRefreshingHoldings] = useState(false);
  const [latestAmfiDate, setLatestAmfiDate] = useState<string | null>(null);
  const [variantSuggestion, setVariantSuggestion] = useState<MFScheme | null>(null);
  const [switchingVariant, setSwitchingVariant] = useState(false);

  // Chart refs
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

  // UI states
  const [barTf, setBarTf] = useState<"1d" | "1w" | "1M">("1d");
  const [timeframe, setTimeframe] = useState<"1M" | "3M" | "6M" | "1Y" | "3Y" | "5Y" | "10Y" | "MAX">("MAX");
  const [activeInds, setActiveInds] = useState<Set<IndKey>>(new Set(["ema20", "ema50", "rsi"]));
  const [chartStyle, setChartStyle] = useState<ChartStyle>("candles");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [activeTab, setActiveTab] = useState<"overview" | "holdings" | "signals" | "patterns" | "links">("overview");

  const showRsi = activeInds.has("rsi");
  const showMacd = activeInds.has("macd");

  // Default style: candles on D, Heikin Ashi on W/M (but user can override).
  useEffect(() => {
    if (barTf === "1d" && chartStyle === "heikin") setChartStyle("candles");
    if (barTf !== "1d" && chartStyle === "candles") setChartStyle("heikin");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [barTf]);

  // Load schemes list
  useEffect(() => {
    void mfApi.schemes(false, "").then((s) => {
      setSchemes(s);
      if (s.length > 0 && !selectedScheme) {
        setSelectedScheme(s[0]);
      }
    });
  }, []);

  // Fetch latest AMFI date from pipeline status (used to detect stale scheme variants).
  useEffect(() => {
    void mfApi
      .status()
      .then((st) => {
        const d = (st as any)?.latest_nav_run?.stats_json?.latest_date;
        if (typeof d === "string" && d.length >= 10) setLatestAmfiDate(d.slice(0, 10));
      })
      .catch(() => {
        // non-fatal
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

  // Load scheme data
  const loadSchemeData = useCallback(async (schemeCode: number) => {
    setLoading(true);
    try {
      const lim = barTf === "1d" ? 2500 : 5000;
      const ha = chartStyle === "heikin";
      const [s, n, ohlc, inds, pats, m, sigs] = await Promise.all([
        mfApi.scheme(schemeCode),
        mfApi.nav(schemeCode, lim, barTf),
        mfApi.ohlc(schemeCode, lim, barTf, ha),
        mfApi.indicators(schemeCode, lim, barTf),
        mfApi.patterns(schemeCode, 220, barTf),
        mfApi.metrics(schemeCode),
        mfApi.signals("all", 400),
      ]);
      setSelectedScheme(s);
      setNav(n);
      setBars(ohlc);
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

  const refreshHoldingsNow = useCallback(async () => {
    const fam = selectedScheme?.family_id;
    if (!fam) {
      toast.message("Holdings need one-time scheme enrichment first (Enable analysis).");
      return;
    }
    setRefreshingHoldings(true);
    try {
      const res = await mfApi.refreshHoldings(fam);
      if (res.skipped) {
        toast.message(res.reason ?? "Holdings refresh is disabled");
        return;
      }
      if (!res.fetched) {
        toast.message(res.error ? `Holdings not available: ${res.error}` : "Holdings not available for this fund yet");
        return;
      }
      const h = await mfApi.holdings(fam);
      setHoldings(h);
      toast.success("Holdings updated");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to refresh holdings");
    } finally {
      setRefreshingHoldings(false);
    }
  }, [selectedScheme?.family_id]);

  useEffect(() => {
    if (selectedScheme?.scheme_code) {
      void loadSchemeData(selectedScheme.scheme_code);
    }
  }, [selectedScheme?.scheme_code, loadSchemeData]);

  // If the selected scheme variant is stale vs the latest AMFI date, suggest a better-matched scheme_code.
  useEffect(() => {
    const s = selectedScheme;
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
        if (!candidates.length) {
          setVariantSuggestion(null);
          return;
        }
        candidates.sort((a, b) => String(b.latest_nav_date).localeCompare(String(a.latest_nav_date)));
        const best = candidates[0];
        if (best.scheme_code !== s.scheme_code && String(best.latest_nav_date) > String(s.latest_nav_date)) {
          setVariantSuggestion(best);
        } else {
          setVariantSuggestion(null);
        }
      })
      .catch(() => setVariantSuggestion(null));

    return () => {
      cancelled = true;
    };
  }, [selectedScheme?.scheme_code, selectedScheme?.scheme_name, selectedScheme?.latest_nav_date, latestAmfiDate]);

  const switchToSuggestedVariant = useCallback(async () => {
    if (!selectedScheme || !variantSuggestion) return;
    setSwitchingVariant(true);
    try {
      // If the current one is monitored, move monitoring to the newer scheme_code.
      if (selectedScheme.monitored) {
        await Promise.all([
          mfApi.updateScheme(selectedScheme.scheme_code, { monitored: false }),
          mfApi.updateScheme(variantSuggestion.scheme_code, { monitored: true }),
        ]);
      }
      setSelectedScheme(variantSuggestion);
      toast.success("Switched to the latest scheme variant");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to switch scheme variant");
    } finally {
      setSwitchingVariant(false);
    }
  }, [selectedScheme, variantSuggestion]);

  // Filter data by timeframe
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

    const seen = new Set<string>();
    const unique: typeof out = [];
    for (const it of out.sort((a, b) => b.time.localeCompare(a.time))) {
      const k = `${it.kind}:${it.time}:${it.direction ?? ""}:${it.label}`;
      if (seen.has(k)) continue;
      seen.add(k);
      unique.push(it);
    }
    return unique.slice(0, 250);
  }, [patterns]);

  const focusOnTime = useCallback((t: string) => {
    if (!t) return;
    setTimeframe("MAX");
    // Defer until the chart renders the MAX dataset.
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
  }, [bars]);

  // Init main chart
  useEffect(() => {
    if (!chartRef.current) return;
    const c = createChart(chartRef.current, {
      width: chartRef.current.clientWidth,
      ...patternOsChartMfCardOptions({ height: 320 }),
    });
    const candles = c.addSeries(CandlestickSeries, {
      ...patternOsCandlestickSeriesDefaults,
    });
    const line = c.addSeries(LineSeries, {
      color: "#38bdf8",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
    });
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

  // Signal markers with overlap detection
  useEffect(() => {
    const markersApi = chartStyle === "line" ? lineMarkersRef.current : candleMarkersRef.current;
    if (!markersApi) return;
    const markers: SeriesMarker<Time>[] = [];

    const min = filteredBars.length ? filteredBars[0].time : null;
    const max = filteredBars.length ? filteredBars[filteredBars.length - 1].time : null;

    // Group signals by date to detect overlaps
    const signalsByDate = new Map<string, MFSignal[]>();
    for (const s of signals) {
      if (!s.nav_date) continue;
      if (min && max && (s.nav_date < min || s.nav_date > max)) continue;
      if (!signalsByDate.has(s.nav_date)) {
        signalsByDate.set(s.nav_date, []);
      }
      signalsByDate.get(s.nav_date)!.push(s);
    }

    // Collapse to 1 marker per day (prevents clutter/overlap).
    signalsByDate.forEach((sigs, date) => {
      const best = [...sigs].sort((a, b) => (b.confidence_score ?? 0) - (a.confidence_score ?? 0))[0];
      const col = best.confidence_score >= 80 ? "#22c55e" : best.confidence_score >= 70 ? "#f59e0b" : "#ef4444";
      const m: SeriesMarker<Time> = {
        time: date as Time,
        position: "aboveBar",
        color: col,
        shape: sigs.length > 1 ? "square" : "circle",
        size: sigs.length > 1 ? 2 : 1,
      };
      if (sigs.length > 1) m.text = String(sigs.length);
      markers.push(m);
    });

    // Pattern markers
    const talib = (patterns?.talib_candlestick_patterns || []) as any[];
    const native = (patterns?.candlestick_patterns || []) as any[];
    const allPats = [
      ...talib.map((p) => ({ time: p?.time, label: p?.name, direction: p?.direction })),
      ...native.map((p) => ({ time: p?.date, label: p?.pattern, direction: p?.direction })),
    ].filter((p) => p.time && p.label);

    const patInWindow = allPats.filter((p) => !min || !max || (String(p.time) >= min && String(p.time) <= max));
    // Collapse patterns per day + direction; show counts, not overlapping labels.
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
  }, [showRsi, showMacd]);

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
  }, [showRsi, showMacd]);

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

  // Crosshair sync
  const syncingCrosshair = useRef(false);
  useEffect(() => {
    const main = chartApi.current;
    const mainSeries = chartStyle === "line" ? lineSeriesRef.current : candleSeriesRef.current;
    if (!main || !mainSeries) return;

    const rsiChart = rsiChartApi.current;
    const rsiSeries = rsiSeriesRef.current;
    const macdChart = macdChartApi.current;

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
          const targetSeries = rec?.macd != null ? macdSeriesRef.current : macdSignalRef.current;
          if (v != null && targetSeries) macdChart.setCrosshairPosition(v, t as any, targetSeries as any);
          else macdChart.clearCrosshairPosition();
        }
      } finally {
        syncingCrosshair.current = false;
      }
    };

    main.subscribeCrosshairMove(onMainMove);

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
        <div className="flex items-center gap-2 px-3 py-2 border-b border-border bg-card shrink-0 flex-wrap">
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

          {/* Bar timeframe (D/W/M) */}
          <div className="flex gap-0.5">
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
                variant={barTf === it.v ? "default" : "ghost"}
                className="h-7 px-2 text-xs"
                onClick={() => setBarTf(it.v)}
                title="Bar timeframe"
              >
                {it.label}
              </Button>
            ))}
            {barTf !== "1d" ? (
              <Badge variant="outline" className="ml-1 text-[10px]" title="Weekly/Monthly uses Heikin Ashi candles">
                Heikin Ashi
              </Badge>
            ) : null}
            <span className="ml-2 text-[10px] text-muted-foreground" title="Number of bars shown (after aggregation)">
              {filteredBars.length ? `${filteredBars.length} bars` : ""}
            </span>
          </div>

          <div className="w-px h-6 bg-border/60 mx-1" />

          {/* Chart style */}
          <div className="flex gap-0.5">
            {[
              { v: "line" as const, label: "Line" },
              { v: "candles" as const, label: "Candles" },
              { v: "heikin" as const, label: "Heikin" },
            ].map((it) => (
              <Button
                key={it.v}
                size="sm"
                variant={chartStyle === it.v ? "default" : "ghost"}
                className="h-7 px-2 text-xs"
                onClick={() => setChartStyle(it.v)}
                disabled={it.v === "heikin" && barTf === "1d"}
                title={it.v === "heikin" && barTf === "1d" ? "Heikin Ashi applies to W/M" : "Chart style"}
              >
                {it.label}
              </Button>
            ))}
          </div>

          <div className="w-px h-6 bg-border/60 mx-1" />

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
          {variantSuggestion ? (
            <div className="absolute top-2 left-2 right-2 z-10">
              <Card className="border-yellow-500/30 bg-card/80 backdrop-blur">
                <CardContent className="p-2 flex items-center justify-between gap-2 text-xs">
                  <div className="min-w-0">
                    <div className="font-medium truncate">This scheme variant looks outdated.</div>
                    <div className="text-muted-foreground truncate">
                      Latest NAV here: {selectedScheme?.latest_nav_date} Â· Better match available: AMFI {variantSuggestion.scheme_code} ({variantSuggestion.latest_nav_date})
                    </div>
                  </div>
                  <Button size="sm" onClick={switchToSuggestedVariant} disabled={switchingVariant}>
                    {switchingVariant ? "Switchingâ€¦" : "Switch"}
                  </Button>
                </CardContent>
              </Card>
            </div>
          ) : null}
          <div ref={chartRef} className="w-full flex-1 min-h-0" />

          {showRsi && (
            <div className="shrink-0 border-t border-border" style={{ height: "120px" }}>
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
        <div className="shrink-0 border-t border-border bg-card px-3 py-2 flex items-center gap-4 text-xs">
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
              { key: "patterns", label: "Patterns", icon: TrendingDown },
              { key: "links", label: "Links", icon: Globe },
            ].map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key as any)}
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
                    <div className="space-y-2">
                      <div className="text-sm text-muted-foreground">Holdings need one-time scheme enrichment.</div>
                      <div className="text-[11px] text-muted-foreground">Tip: open the scheme detail and click “Enable analysis”.</div>
                    </div>
                  ) : !holdings ? (
                    <div className="space-y-2">
                      <div className="text-sm text-muted-foreground">No holdings snapshot yet.</div>
                      <Button size="sm" variant="outline" onClick={refreshHoldingsNow} disabled={refreshingHoldings}>
                        {refreshingHoldings ? "Fetchingâ€¦" : "Fetch holdings now"}
                      </Button>
                    </div>
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
              <div className="space-y-2">
                {patternItems.length === 0 ? (
                  <div className="text-sm text-muted-foreground text-center py-6">No patterns in range.</div>
                ) : (
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm flex items-center justify-between">
                        <span className="flex items-center gap-2">
                          <TrendingDown className="h-4 w-4" /> Patterns
                        </span>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => chartApi.current?.timeScale().fitContent()}
                        >
                          Reset
                        </Button>
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="p-0">
                      <div className="max-h-[520px] overflow-y-auto">
                        <table className="w-full text-xs">
                          <thead className="sticky top-0 bg-card border-b border-border/60">
                            <tr>
                              <th className="text-left font-medium px-3 py-2">Date</th>
                              <th className="text-left font-medium px-3 py-2">Pattern</th>
                            </tr>
                          </thead>
                          <tbody>
                            {patternItems.map((p, i) => (
                              <tr
                                key={`${p.kind}:${p.time}:${p.label}:${i}`}
                                className="border-b border-border/30 hover:bg-muted/20 cursor-pointer"
                                onClick={() => focusOnTime(p.time)}
                                title="Click to jump"
                              >
                                <td className="px-3 py-2 text-muted-foreground whitespace-nowrap">{p.time}</td>
                                <td className="px-3 py-2">
                                  <div className="flex items-center gap-2">
                                    <span className={p.direction === "bullish" ? "text-green-400" : p.direction === "bearish" ? "text-red-400" : "text-foreground"}>
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
                    </CardContent>
                  </Card>
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
