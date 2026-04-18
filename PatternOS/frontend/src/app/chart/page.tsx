"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  createChart,
  CandlestickSeries,
  LineSeries,
  HistogramSeries,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
  ColorType,
  CrosshairMode,
  PriceScaleMode,
  LineStyle,
} from "lightweight-charts";
import { universeApi, signalsApi, type UniverseItem, type Signal } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { ConfidenceBadge } from "@/components/confidence-badge";
import { toast } from "sonner";
import {
  ArrowUpToLine, ChevronRight, Minus, Move, RefreshCw, TrendingUp, ZoomIn,
} from "lucide-react";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

const TIMEFRAMES = [
  { value: "1d", label: "D" },
  { value: "1h", label: "1H" },
  { value: "1w", label: "W" },
  { value: "1M", label: "M" },
];

// ── Types ─────────────────────────────────────────────────────────────────────
interface OHLCVBar {
  time: string; open: number; high: number; low: number; close: number; volume?: number;
}

interface IndicatorBar {
  time: string;
  ema_20?: number | null; ema_50?: number | null; ema_200?: number | null;
  sma_20?: number | null;
  bb_upper?: number | null; bb_mid?: number | null; bb_lower?: number | null;
  rsi?: number | null;
  macd?: number | null; macd_signal?: number | null; macd_hist?: number | null;
  atr?: number | null;
  stoch_k?: number | null; stoch_d?: number | null;
  adx?: number | null; adx_di_pos?: number | null; adx_di_neg?: number | null;
  obv?: number | null;
}

interface CdlPattern { date: string; pattern: string; direction: string; description: string; }
interface ChartPattern {
  type: string; direction: string; confidence: number;
  start_date: string; end_date: string;
  key_levels: { resistance?: number; support?: number; target?: number; stop?: number };
  description: string;
}

type DrawTool = "cursor" | "hline" | "trendline";
interface DrawnSeries { id: string; series: ISeriesApi<"Line">; }

// Indicator toggles
type IndKey = "ema20" | "ema50" | "ema200" | "sma20" | "bb" | "rsi" | "macd" | "stoch" | "adx" | "obv" | "cdl";

// Indicator catalog
interface IndDef {
  key: IndKey;
  name: string;
  description: string;
  category: "moving_avg" | "oscillator" | "volatility" | "volume" | "patterns";
  color: string;
}

const IND_CATALOG: IndDef[] = [
  { key: "ema20",  name: "EMA 20",          description: "Exponential Moving Average (20)",             category: "moving_avg",  color: "#22c55e" },
  { key: "ema50",  name: "EMA 50",          description: "Exponential Moving Average (50)",             category: "moving_avg",  color: "#3b82f6" },
  { key: "ema200", name: "EMA 200",         description: "Exponential Moving Average (200)",            category: "moving_avg",  color: "#f59e0b" },
  { key: "sma20",  name: "SMA 20",          description: "Simple Moving Average (20)",                  category: "moving_avg",  color: "#a78bfa" },
  { key: "bb",     name: "Bollinger Bands", description: "Bollinger Bands (20, 2\u03c3)",               category: "volatility",  color: "#6366f1" },
  { key: "rsi",    name: "RSI 14",          description: "Relative Strength Index (14)",                category: "oscillator",  color: "#a78bfa" },
  { key: "macd",   name: "MACD",            description: "Moving Average Convergence Divergence (12,26,9)", category: "oscillator", color: "#3b82f6" },
  { key: "stoch",  name: "Stochastic",      description: "Stochastic Oscillator (14,3)",               category: "oscillator",  color: "#fb923c" },
  { key: "adx",    name: "ADX",             description: "Average Directional Index (14)",              category: "oscillator",  color: "#c084fc" },
  { key: "obv",    name: "OBV",             description: "On-Balance Volume",                          category: "volume",      color: "#818cf8" },
  { key: "cdl",    name: "CDL Patterns",    description: "Candlestick Pattern Markers",                category: "patterns",    color: "#f472b6" },
];

type IndCategory = "all" | "moving_avg" | "oscillator" | "volatility" | "volume" | "patterns";

const CATEGORY_LABELS: Record<IndCategory, string> = {
  all: "All",
  moving_avg: "Moving Avg",
  oscillator: "Oscillators",
  volatility: "Volatility",
  volume: "Volume",
  patterns: "Patterns",
};

// ── Time-scale sync guard (prevents recursive range updates) ─────────────────
let _syncing = false;
function syncRange(source: IChartApi, ...targets: (IChartApi | null)[]) {
  if (_syncing) return;
  const range = source.timeScale().getVisibleLogicalRange();
  if (!range) return;
  _syncing = true;
  for (const t of targets) {
    try { t?.timeScale().setVisibleLogicalRange(range); } catch { /**/ }
  }
  _syncing = false;
}

// ── Chart colour constants ────────────────────────────────────────────────────
const BG = "#0a0a0c";
const GRID = "#111115";
const CHART_OPTS = {
  layout: { background: { type: ColorType.Solid, color: BG }, textColor: "#9ca3af", fontSize: 11 },
  grid: { vertLines: { color: GRID }, horzLines: { color: GRID } },
  crosshair: { mode: CrosshairMode.Normal, vertLine: { color: "#374151", labelBackgroundColor: "#1f2937" }, horzLine: { color: "#374151", labelBackgroundColor: "#1f2937" } },
  timeScale: { borderColor: "#1f2937", timeVisible: true, secondsVisible: false },
};

// ── Component ─────────────────────────────────────────────────────────────────
export default function ChartPage() {
  // Main chart
  const mainRef  = useRef<HTMLDivElement>(null);
  const rsiRef   = useRef<HTMLDivElement>(null);
  const macdRef  = useRef<HTMLDivElement>(null);
  const stochRef = useRef<HTMLDivElement>(null);
  const adxRef   = useRef<HTMLDivElement>(null);

  const chartRef     = useRef<IChartApi | null>(null);
  const rsiChartRef  = useRef<IChartApi | null>(null);
  const macdChartRef = useRef<IChartApi | null>(null);
  const stochChartRef = useRef<IChartApi | null>(null);
  const adxChartRef  = useRef<IChartApi | null>(null);

  const candleRef  = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeRef  = useRef<ISeriesApi<"Histogram"> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const drawnLines = useRef<DrawnSeries[]>([]);
  const drawStart  = useRef<{ price: number; time: Time } | null>(null);
  const pendingTrend = useRef<ISeriesApi<"Line"> | null>(null);
  // Cached markers for focus/reset
  const sigMarkersRef = useRef<SeriesMarker<Time>[]>([]);
  const cdlMarkersRef = useRef<SeriesMarker<Time>[]>([]);

  // Indicator overlay series refs
  const overlayRefs = useRef<Partial<Record<IndKey, ISeriesApi<"Line">[]>>>({});
  const obvRef          = useRef<ISeriesApi<"Line"> | null>(null);
  const rsiSeriesRef    = useRef<ISeriesApi<"Line"> | null>(null);
  const macdLineRef     = useRef<ISeriesApi<"Line"> | null>(null);
  const macdSignalRef   = useRef<ISeriesApi<"Line"> | null>(null);
  const macdHistRef     = useRef<ISeriesApi<"Histogram"> | null>(null);
  const stochKRef       = useRef<ISeriesApi<"Line"> | null>(null);
  const stochDRef       = useRef<ISeriesApi<"Line"> | null>(null);
  const adxLineRef      = useRef<ISeriesApi<"Line"> | null>(null);
  const adxPosRef       = useRef<ISeriesApi<"Line"> | null>(null);
  const adxNegRef       = useRef<ISeriesApi<"Line"> | null>(null);

  const [symbols, setSymbols]       = useState<UniverseItem[]>([]);
  const [symbol, setSymbol]         = useState("");
  const [timeframe, setTimeframe]   = useState("1d");
  const [signals, setSignals]       = useState<Signal[]>([]);
  const [activeSignal, setActiveSignal] = useState<Signal | null>(null);
  const [tool, setTool]             = useState<DrawTool>("cursor");
  const [loading, setLoading]       = useState(false);
  const [ohlcInfo, setOhlcInfo]     = useState<{ o: number; h: number; l: number; c: number; chg: number } | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Ticker combobox state
  const [dropdownOpen, setDropdownOpen]         = useState(false);
  const [tickerSearch, setTickerSearch]         = useState("");
  const [tickerIndexFilter, setTickerIndexFilter] = useState("All");
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Indicator toggles — default: EMA20, EMA50, RSI
  const [activeInds, setActiveInds] = useState<Set<IndKey>>(new Set(["ema20", "ema50", "rsi"]));

  // Indicator picker panel
  const [showIndicatorPanel, setShowIndicatorPanel] = useState(false);
  const [indSearch, setIndSearch] = useState("");
  const [indCategory, setIndCategory] = useState<IndCategory>("all");

  // Derived booleans from activeInds (replaces separate useState for these)
  const showRsi  = activeInds.has("rsi");
  const showMacd = activeInds.has("macd");
  const showStoch = activeInds.has("stoch");
  const showAdx   = activeInds.has("adx");

  // Pattern data
  const [cdlPatterns, setCdlPatterns] = useState<CdlPattern[]>([]);
  const [chartPatterns, setChartPatterns] = useState<ChartPattern[]>([]);
  const [showPatterns, setShowPatterns] = useState(false);
  const [activePattern, setActivePattern] = useState<ChartPattern | null>(null);
  const [activeCdlPattern, setActiveCdlPattern] = useState<CdlPattern | null>(null);

  // ── Init main chart ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (!mainRef.current) return;

    const chart = createChart(mainRef.current, {
      ...CHART_OPTS,
      width: mainRef.current.clientWidth,
      height: mainRef.current.clientHeight,
      rightPriceScale: { borderColor: "#1f2937", mode: PriceScaleMode.Normal, scaleMargins: { top: 0.08, bottom: 0.28 } },
    });

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e", downColor: "#ef4444",
      borderUpColor: "#22c55e", borderDownColor: "#ef4444",
      wickUpColor: "#22c55e", wickDownColor: "#ef4444",
    });

    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" }, priceScaleId: "vol",
    });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

    const markers = createSeriesMarkers(candles);

    chart.subscribeCrosshairMove((param) => {
      if (!param.time) return;
      const bar = param.seriesData.get(candles) as OHLCVBar | undefined;
      if (bar && "open" in bar) {
        const chg = ((bar.close - bar.open) / bar.open) * 100;
        setOhlcInfo({ o: bar.open, h: bar.high, l: bar.low, c: bar.close, chg });
      }
    });

    chartRef.current  = chart;
    candleRef.current = candles;
    volumeRef.current = volume;
    markersRef.current = markers;

    // ── Sync sub-panels when main chart scrolls/zooms ──────────────────────
    chart.timeScale().subscribeVisibleLogicalRangeChange(() => {
      syncRange(chart, rsiChartRef.current, macdChartRef.current, stochChartRef.current, adxChartRef.current);
    });

    const ro = new ResizeObserver(() => {
      if (mainRef.current) chart.applyOptions({ width: mainRef.current.clientWidth, height: mainRef.current.clientHeight });
    });
    ro.observe(mainRef.current);
    return () => { ro.disconnect(); chart.remove(); };
  }, []);

  // ── Init RSI sub-chart ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!rsiRef.current || !showRsi) return;

    const c = createChart(rsiRef.current, {
      ...CHART_OPTS,
      width:  rsiRef.current.clientWidth,
      height: rsiRef.current.clientHeight,
      rightPriceScale: { borderColor: "#1f2937", scaleMargins: { top: 0.1, bottom: 0.1 } },
      timeScale: { ...CHART_OPTS.timeScale, visible: false },
    });

    const rsiLine = c.addSeries(LineSeries, { color: "#a78bfa", lineWidth: 1, title: "RSI", priceLineVisible: false });

    rsiChartRef.current  = c;
    rsiSeriesRef.current = rsiLine;

    // Sync initial position from main, then keep in lockstep
    const initRange = chartRef.current?.timeScale().getVisibleLogicalRange();
    if (initRange) { try { c.timeScale().setVisibleLogicalRange(initRange); } catch { /**/ } }
    c.timeScale().subscribeVisibleLogicalRangeChange(() => {
      syncRange(c, chartRef.current, macdChartRef.current, stochChartRef.current, adxChartRef.current);
    });

    const ro = new ResizeObserver(() => {
      if (rsiRef.current) c.applyOptions({ width: rsiRef.current.clientWidth, height: rsiRef.current.clientHeight });
    });
    ro.observe(rsiRef.current);
    return () => { ro.disconnect(); c.remove(); rsiChartRef.current = null; rsiSeriesRef.current = null; };
  }, [showRsi]);

  // ── Init MACD sub-chart ─────────────────────────────────────────────────────
  useEffect(() => {
    if (!macdRef.current || !showMacd) return;

    const c = createChart(macdRef.current, {
      ...CHART_OPTS,
      width:  macdRef.current.clientWidth,
      height: macdRef.current.clientHeight,
      rightPriceScale: { borderColor: "#1f2937", scaleMargins: { top: 0.1, bottom: 0.1 } },
      timeScale: { ...CHART_OPTS.timeScale, visible: false },
    });

    const macdLine   = c.addSeries(LineSeries,      { color: "#3b82f6", lineWidth: 1, title: "MACD",   priceLineVisible: false });
    const signalLine = c.addSeries(LineSeries,      { color: "#f59e0b", lineWidth: 1, title: "Signal", priceLineVisible: false });
    const histSeries = c.addSeries(HistogramSeries, { priceScaleId: "right", title: "Hist" });

    macdChartRef.current  = c;
    macdLineRef.current   = macdLine;
    macdSignalRef.current = signalLine;
    macdHistRef.current   = histSeries;

    // Sync initial position from main, then keep in lockstep
    const initRange = chartRef.current?.timeScale().getVisibleLogicalRange();
    if (initRange) { try { c.timeScale().setVisibleLogicalRange(initRange); } catch { /**/ } }
    c.timeScale().subscribeVisibleLogicalRangeChange(() => {
      syncRange(c, chartRef.current, rsiChartRef.current, stochChartRef.current, adxChartRef.current);
    });

    const ro = new ResizeObserver(() => {
      if (macdRef.current) c.applyOptions({ width: macdRef.current.clientWidth, height: macdRef.current.clientHeight });
    });
    ro.observe(macdRef.current);
    return () => { ro.disconnect(); c.remove(); macdChartRef.current = null; };
  }, [showMacd]);

  // ── Init Stochastic sub-chart ───────────────────────────────────────────────
  useEffect(() => {
    if (!stochRef.current || !showStoch) return;

    const c = createChart(stochRef.current, {
      ...CHART_OPTS,
      width:  stochRef.current.clientWidth,
      height: stochRef.current.clientHeight,
      rightPriceScale: { borderColor: "#1f2937", scaleMargins: { top: 0.1, bottom: 0.1 } },
      timeScale: { ...CHART_OPTS.timeScale, visible: false },
    });

    const kLine = c.addSeries(LineSeries, { color: "#e2e8f0", lineWidth: 1, title: "%K", priceLineVisible: false });
    const dLine = c.addSeries(LineSeries, { color: "#f97316", lineWidth: 1, lineStyle: LineStyle.Dashed, title: "%D", priceLineVisible: false });

    stochChartRef.current = c;
    stochKRef.current = kLine;
    stochDRef.current = dLine;

    const initRange = chartRef.current?.timeScale().getVisibleLogicalRange();
    if (initRange) { try { c.timeScale().setVisibleLogicalRange(initRange); } catch { /**/ } }
    c.timeScale().subscribeVisibleLogicalRangeChange(() => {
      syncRange(c, chartRef.current, rsiChartRef.current, macdChartRef.current, adxChartRef.current);
    });

    const ro = new ResizeObserver(() => {
      if (stochRef.current) c.applyOptions({ width: stochRef.current.clientWidth, height: stochRef.current.clientHeight });
    });
    ro.observe(stochRef.current);
    return () => { ro.disconnect(); c.remove(); stochChartRef.current = null; stochKRef.current = null; stochDRef.current = null; };
  }, [showStoch]);

  // ── Init ADX sub-chart ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!adxRef.current || !showAdx) return;

    const c = createChart(adxRef.current, {
      ...CHART_OPTS,
      width:  adxRef.current.clientWidth,
      height: adxRef.current.clientHeight,
      rightPriceScale: { borderColor: "#1f2937", scaleMargins: { top: 0.1, bottom: 0.1 } },
      timeScale: { ...CHART_OPTS.timeScale, visible: false },
    });

    const adxLine = c.addSeries(LineSeries, { color: "#c084fc", lineWidth: 1, title: "ADX",  priceLineVisible: false });
    const posLine = c.addSeries(LineSeries, { color: "#22c55e", lineWidth: 1, title: "+DI",  priceLineVisible: false });
    const negLine = c.addSeries(LineSeries, { color: "#ef4444", lineWidth: 1, title: "-DI",  priceLineVisible: false });

    adxChartRef.current = c;
    adxLineRef.current  = adxLine;
    adxPosRef.current   = posLine;
    adxNegRef.current   = negLine;

    const initRange = chartRef.current?.timeScale().getVisibleLogicalRange();
    if (initRange) { try { c.timeScale().setVisibleLogicalRange(initRange); } catch { /**/ } }
    c.timeScale().subscribeVisibleLogicalRangeChange(() => {
      syncRange(c, chartRef.current, rsiChartRef.current, macdChartRef.current, stochChartRef.current);
    });

    const ro = new ResizeObserver(() => {
      if (adxRef.current) c.applyOptions({ width: adxRef.current.clientWidth, height: adxRef.current.clientHeight });
    });
    ro.observe(adxRef.current);
    return () => { ro.disconnect(); c.remove(); adxChartRef.current = null; adxLineRef.current = null; adxPosRef.current = null; adxNegRef.current = null; };
  }, [showAdx]);

  // ── Load universe ───────────────────────────────────────────────────────────
  useEffect(() => {
    void universeApi.list(true)
      .then((items) => {
        setSymbols(items);
        if (items.length > 0) setSymbol(items[0].symbol);
      })
      .catch((e) => {
        const msg = e instanceof Error ? e.message : "Failed to load universe";
        toast.error(msg);
      });
  }, []);

  // ── Close dropdown on outside click ─────────────────────────────────────────
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

  // ── Close dropdown on ESC ────────────────────────────────────────────────────
  useEffect(() => {
    if (!dropdownOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDropdownOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [dropdownOpen]);

  // ── Filtered symbols for combobox ────────────────────────────────────────────
  const INDEX_TABS = ["All", "Nifty 50", "Nifty Next 50", "Nifty Midcap 150", "Nifty Smallcap 250"];
  const filteredSymbols = symbols.filter((s) => {
    const matchIndex = tickerIndexFilter === "All" || s.index_name === tickerIndexFilter;
    if (!matchIndex) return false;
    if (!tickerSearch) return true;
    const q = tickerSearch.toUpperCase();
    return s.symbol.toUpperCase().includes(q) || (s.name ?? "").toUpperCase().includes(q);
  }).slice(0, 80);

  // ── Load indicators overlay series ─────────────────────────────────────────
  const applyIndicatorOverlays = useCallback((indBars: IndicatorBar[]) => {
    const chart = chartRef.current;
    if (!chart) return;

    // Remove old overlays (except OBV which has separate ref)
    Object.values(overlayRefs.current).forEach((seriesList) => {
      seriesList?.forEach((s) => { try { chart.removeSeries(s); } catch { /**/ } });
    });
    overlayRefs.current = {};

    // Remove OBV overlay if present
    if (obvRef.current) {
      try { chart.removeSeries(obvRef.current); } catch { /**/ }
      obvRef.current = null;
    }

    const validBars = (getter: (b: IndicatorBar) => number | null | undefined) =>
      indBars.filter((b) => getter(b) != null).map((b) => ({ time: b.time as Time, value: getter(b) as number }));

    if (activeInds.has("ema20")) {
      const s = chart.addSeries(LineSeries, { color: "#22c55e", lineWidth: 1, title: "EMA20", priceLineVisible: false, crosshairMarkerVisible: false });
      s.setData(validBars((b) => b.ema_20));
      overlayRefs.current.ema20 = [s];
    }
    if (activeInds.has("ema50")) {
      const s = chart.addSeries(LineSeries, { color: "#3b82f6", lineWidth: 1, title: "EMA50", priceLineVisible: false, crosshairMarkerVisible: false });
      s.setData(validBars((b) => b.ema_50));
      overlayRefs.current.ema50 = [s];
    }
    if (activeInds.has("ema200")) {
      const s = chart.addSeries(LineSeries, { color: "#f59e0b", lineWidth: 1, title: "EMA200", priceLineVisible: false, crosshairMarkerVisible: false });
      s.setData(validBars((b) => b.ema_200));
      overlayRefs.current.ema200 = [s];
    }
    if (activeInds.has("sma20")) {
      const s = chart.addSeries(LineSeries, { color: "#a78bfa", lineWidth: 1, lineStyle: LineStyle.Dashed, title: "SMA20", priceLineVisible: false, crosshairMarkerVisible: false });
      s.setData(validBars((b) => b.sma_20));
      overlayRefs.current.sma20 = [s];
    }
    if (activeInds.has("bb")) {
      const upper = chart.addSeries(LineSeries, { color: "#6366f180", lineWidth: 1, lineStyle: LineStyle.Dashed, title: "BB+", priceLineVisible: false, crosshairMarkerVisible: false });
      const mid   = chart.addSeries(LineSeries, { color: "#6366f1",   lineWidth: 1, lineStyle: LineStyle.Dotted, title: "BB~", priceLineVisible: false, crosshairMarkerVisible: false });
      const lower = chart.addSeries(LineSeries, { color: "#6366f180", lineWidth: 1, lineStyle: LineStyle.Dashed, title: "BB-", priceLineVisible: false, crosshairMarkerVisible: false });
      upper.setData(validBars((b) => b.bb_upper));
      mid.setData(validBars((b) => b.bb_mid));
      lower.setData(validBars((b) => b.bb_lower));
      overlayRefs.current.bb = [upper, mid, lower];
    }
    if (activeInds.has("obv")) {
      const s = chart.addSeries(LineSeries, { color: "#818cf8", lineWidth: 1, title: "OBV", priceLineVisible: false, crosshairMarkerVisible: false, priceScaleId: "obv" });
      s.setData(validBars((b) => b.obv));
      obvRef.current = s;
    }
  }, [activeInds]);

  // ── Load data ───────────────────────────────────────────────────────────────
  const loadChart = useCallback(async (sym: string, tf: string) => {
    if (!candleRef.current || !volumeRef.current || !markersRef.current || !sym) return;
    setLoading(true);
    try {
      const [ohlcvRes, indRes, patternsRes, sigsAll] = await Promise.all([
        fetch(`${BASE}/scanner/ohlcv?symbol=${encodeURIComponent(sym)}&timeframe=${tf}`),
        fetch(`${BASE}/scanner/indicators?symbol=${encodeURIComponent(sym)}&timeframe=${tf}`),
        fetch(`${BASE}/scanner/chart-patterns?symbol=${encodeURIComponent(sym)}&timeframe=${tf}`),
        signalsApi.list("all", undefined, 200),
      ]);

      let bars: OHLCVBar[]       = ohlcvRes.ok  ? await ohlcvRes.json()   : [];
      const indBars: IndicatorBar[] = indRes.ok    ? await indRes.json()     : [];
      const patternsData            = patternsRes.ok ? await patternsRes.json() : {};

      if (!bars.length) return;

      // Sort bars by time (ascending) - required by lightweight-charts
      bars = bars.slice().sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime());

      // OHLCV
      candleRef.current.setData(bars.map((b) => ({ time: b.time as Time, open: b.open, high: b.high, low: b.low, close: b.close })));
      volumeRef.current.setData(bars.map((b) => ({ time: b.time as Time, value: b.volume ?? 0, color: b.close >= b.open ? "#22c55e30" : "#ef444430" })));
      chartRef.current?.timeScale().fitContent();

      // Filter indBars to only dates present in OHLCV (so overlays align with candles)
      const barDateSet = new Set(bars.map((b) => b.time));
      const alignedIndBars = indBars.filter((b) => barDateSet.has(b.time));

      // Indicator overlays
      applyIndicatorOverlays(alignedIndBars);

      // RSI sub-chart
      if (showRsi && rsiSeriesRef.current) {
        const rsiData = alignedIndBars.filter((b) => b.rsi != null).map((b) => ({ time: b.time as Time, value: b.rsi as number }));
        rsiSeriesRef.current.setData(rsiData);
        rsiChartRef.current?.timeScale().fitContent();
      }

      // MACD sub-chart
      if (showMacd && macdLineRef.current && macdSignalRef.current && macdHistRef.current) {
        const toLine = (getter: (b: IndicatorBar) => number | null | undefined) =>
          alignedIndBars.filter((b) => getter(b) != null).map((b) => ({ time: b.time as Time, value: getter(b) as number }));
        macdLineRef.current.setData(toLine((b) => b.macd));
        macdSignalRef.current.setData(toLine((b) => b.macd_signal));
        macdHistRef.current.setData(
          alignedIndBars.filter((b) => b.macd_hist != null).map((b) => ({
            time: b.time as Time,
            value: b.macd_hist as number,
            color: (b.macd_hist ?? 0) >= 0 ? "#22c55e60" : "#ef444460",
          }))
        );
        macdChartRef.current?.timeScale().fitContent();
      }

      // Stochastic sub-chart
      if (showStoch && stochKRef.current && stochDRef.current) {
        const toLine = (getter: (b: IndicatorBar) => number | null | undefined) =>
          alignedIndBars.filter((b) => getter(b) != null).map((b) => ({ time: b.time as Time, value: getter(b) as number }));
        stochKRef.current.setData(toLine((b) => b.stoch_k));
        stochDRef.current.setData(toLine((b) => b.stoch_d));
        stochChartRef.current?.timeScale().fitContent();
      }

      // ADX sub-chart
      if (showAdx && adxLineRef.current && adxPosRef.current && adxNegRef.current) {
        const toLine = (getter: (b: IndicatorBar) => number | null | undefined) =>
          alignedIndBars.filter((b) => getter(b) != null).map((b) => ({ time: b.time as Time, value: getter(b) as number }));
        adxLineRef.current.setData(toLine((b) => b.adx));
        adxPosRef.current.setData(toLine((b) => b.adx_di_pos));
        adxNegRef.current.setData(toLine((b) => b.adx_di_neg));
        adxChartRef.current?.timeScale().fitContent();
      }

      // Pattern data
      setCdlPatterns(patternsData.candlestick_patterns ?? []);
      setChartPatterns(patternsData.chart_patterns ?? []);

      // Signal markers
      const symSigs = sigsAll.filter((s) => s.symbol === sym);
      setSignals(symSigs);
      const barDates = new Set(bars.map((b) => b.time));
      const markerList: SeriesMarker<Time>[] = symSigs
        .filter((s) => barDates.has(s.triggered_at.split("T")[0]))
        .map((s) => ({
          time: s.triggered_at.split("T")[0] as Time,
          position: "belowBar" as const,
          color: s.confidence_score >= 80 ? "#22c55e" : "#f59e0b",
          shape: "arrowUp" as const,
          text: `${s.pattern_name ?? "Signal"} ${s.confidence_score.toFixed(0)}%`,
          size: s.confidence_score >= 80 ? 2 : 1,
        }));
      sigMarkersRef.current = markerList;

      // Candlestick pattern markers
      const cdlMarkerList: SeriesMarker<Time>[] = (patternsData.candlestick_patterns ?? [])
        .filter((p: CdlPattern) => barDates.has(p.date))
        .map((p: CdlPattern) => ({
          time: p.date as Time,
          position: p.direction === "bullish" ? ("belowBar" as const) : ("aboveBar" as const),
          color: p.direction === "bullish" ? "#22c55e" : p.direction === "bearish" ? "#ef4444" : "#9ca3af",
          shape: "circle" as const,
          text: p.pattern,
          size: 1,
        }));
      cdlMarkersRef.current = cdlMarkerList;

      const showCdl = activeInds.has("cdl");
      const allMarkers = showCdl
        ? [...markerList, ...cdlMarkerList].sort((a, b) => String(a.time) < String(b.time) ? -1 : 1)
        : markerList;
      markersRef.current.setMarkers(allMarkers);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to load chart data";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, [applyIndicatorOverlays, showRsi, showMacd, showStoch, showAdx, activeInds]);

  useEffect(() => {
    if (symbol) void loadChart(symbol, timeframe);
  }, [symbol, timeframe, loadChart]);

  // ── Indicator toggle ────────────────────────────────────────────────────────
  const toggleInd = (key: IndKey) => {
    setActiveInds((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  };

  // ── Jump to signal ──────────────────────────────────────────────────────────
  const jumpToSignal = useCallback((sig: Signal) => {
    setActiveSignal(sig);
    const chart = chartRef.current;
    if (!chart) return;

    drawnLines.current.filter((d) => d.id.startsWith("kl_")).forEach((d) => {
      try { chart.removeSeries(d.series); } catch { /**/ }
    });
    drawnLines.current = drawnLines.current.filter((d) => !d.id.startsWith("kl_"));

    if (sig.key_levels) {
      const defs = [
        { key: "entry"      as const, color: "#3b82f6", title: "Entry" },
        { key: "stop_loss"  as const, color: "#ef4444", title: "SL" },
        { key: "resistance" as const, color: "#f59e0b", title: "R" },
        { key: "support"    as const, color: "#22c55e", title: "S" },
      ];
      defs.forEach(({ key, color, title }) => {
        const val = sig.key_levels?.[key];
        if (!val || !chart) return;
        const s = chart.addSeries(LineSeries, { color, lineWidth: 1, lineStyle: LineStyle.Dashed, title, lastValueVisible: true, priceLineVisible: false });
        s.setData([
          { time: "2020-01-01" as Time, value: val },
          { time: new Date().toISOString().split("T")[0] as Time, value: val },
        ]);
        drawnLines.current.push({ id: `kl_${key}`, series: s });
      });
    }
    try { chart.timeScale().scrollToRealTime(); } catch { /**/ }
  }, []);

  // ── Jump to chart pattern ───────────────────────────────────────────────────
  const jumpToPattern = useCallback((p: ChartPattern) => {
    setActivePattern(p);
    setActiveCdlPattern(null);
    setShowPatterns(true);
    const chart = chartRef.current;
    if (!chart) return;

    // Remove previous pattern-level lines
    drawnLines.current.filter((d) => d.id.startsWith("pat_")).forEach((d) => {
      try { chart.removeSeries(d.series); } catch { /**/ }
    });
    drawnLines.current = drawnLines.current.filter((d) => !d.id.startsWith("pat_"));

    // Focus: show only signal markers (hide all CDL noise)
    markersRef.current?.setMarkers(sigMarkersRef.current);

    // Draw key level lines from pattern start to today
    const today = new Date().toISOString().split("T")[0] as Time;
    const levelDefs = [
      { key: "resistance" as const, color: "#f59e0b", title: "R" },
      { key: "support"    as const, color: "#22c55e", title: "S" },
      { key: "target"     as const, color: "#3b82f6", title: "T" },
      { key: "stop"       as const, color: "#ef4444", title: "Stop" },
    ];
    levelDefs.forEach(({ key, color, title }) => {
      const val = p.key_levels[key];
      if (!val) return;
      const s = chart.addSeries(LineSeries, {
        color, lineWidth: 1, lineStyle: LineStyle.Dashed,
        title, lastValueVisible: true, priceLineVisible: false,
      });
      s.setData([{ time: p.start_date as Time, value: val }, { time: today, value: val }]);
      drawnLines.current.push({ id: `pat_${key}`, series: s });
    });

    // Navigate: show start_date − 20 days … end_date + 30 days
    const pad = (dateStr: string, days: number) => {
      const d = new Date(dateStr);
      d.setDate(d.getDate() + days);
      return d.toISOString().split("T")[0] as Time;
    };
    try {
      chart.timeScale().setVisibleRange({
        from: pad(p.start_date, -20),
        to:   pad(p.end_date,   30),
      });
      syncRange(chart, rsiChartRef.current, macdChartRef.current, stochChartRef.current, adxChartRef.current);
    } catch { /**/ }
  }, []);

  // ── Jump to candlestick pattern ─────────────────────────────────────────────
  const jumpToCdl = useCallback((p: CdlPattern) => {
    setActiveCdlPattern(p);
    setActivePattern(null);
    setShowPatterns(true);
    const chart = chartRef.current;
    if (!chart) return;

    // Remove chart-pattern level lines
    drawnLines.current.filter((d) => d.id.startsWith("pat_")).forEach((d) => {
      try { chart.removeSeries(d.series); } catch { /**/ }
    });
    drawnLines.current = drawnLines.current.filter((d) => !d.id.startsWith("pat_"));

    // Focus: show only this CDL's marker + signal markers (hide all other CDL noise)
    const focusMarker: SeriesMarker<Time> = {
      time: p.date as Time,
      position: p.direction === "bullish" ? "belowBar" : "aboveBar",
      color: p.direction === "bullish" ? "#22c55e" : p.direction === "bearish" ? "#ef4444" : "#9ca3af",
      shape: "circle",
      text: `\u25b6 ${p.pattern}`,
      size: 2,
    };
    const focused = [...sigMarkersRef.current, focusMarker].sort((a, b) =>
      String(a.time) < String(b.time) ? -1 : 1
    );
    markersRef.current?.setMarkers(focused);

    const pad = (dateStr: string, days: number) => {
      const d = new Date(dateStr);
      d.setDate(d.getDate() + days);
      return d.toISOString().split("T")[0] as Time;
    };
    try {
      chart.timeScale().setVisibleRange({
        from: pad(p.date, -15),
        to:   pad(p.date, 15),
      });
      syncRange(chart, rsiChartRef.current, macdChartRef.current, stochChartRef.current, adxChartRef.current);
    } catch { /**/ }
  }, []);

  // ── Reset pattern focus ─────────────────────────────────────────────────────
  const resetPatternFocus = useCallback(() => {
    setActivePattern(null);
    setActiveCdlPattern(null);
    const chart = chartRef.current;
    if (!chart) return;
    // Remove pattern level lines
    drawnLines.current.filter((d) => d.id.startsWith("pat_")).forEach((d) => {
      try { chart.removeSeries(d.series); } catch { /**/ }
    });
    drawnLines.current = drawnLines.current.filter((d) => !d.id.startsWith("pat_"));
    // Restore all markers
    const allMarkers = [...sigMarkersRef.current, ...cdlMarkersRef.current].sort((a, b) =>
      String(a.time) < String(b.time) ? -1 : 1
    );
    markersRef.current?.setMarkers(allMarkers);
    // Return to recent data
    try { chart.timeScale().scrollToRealTime(); } catch { /**/ }
  }, []);

  // ── Drawing tools ───────────────────────────────────────────────────────────
  const handleChartClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (tool === "cursor" || !chartRef.current || !candleRef.current || !mainRef.current) return;
    const rect  = mainRef.current.getBoundingClientRect();
    const price = candleRef.current.coordinateToPrice(e.clientY - rect.top);
    const time  = chartRef.current.timeScale().coordinateToTime(e.clientX - rect.left);
    if (price == null || time == null) return;

    if (tool === "hline") {
      const s = chartRef.current.addSeries(LineSeries, { color: "#6366f1", lineWidth: 1, lineStyle: LineStyle.Dashed, title: price.toFixed(2), lastValueVisible: true, priceLineVisible: false });
      s.setData([{ time: "2020-01-01" as Time, value: price }, { time: new Date().toISOString().split("T")[0] as Time, value: price }]);
      drawnLines.current.push({ id: `h_${Date.now()}`, series: s });
    } else if (tool === "trendline") {
      if (!drawStart.current) {
        drawStart.current = { price, time };
        const s = chartRef.current.addSeries(LineSeries, { color: "#a78bfa", lineWidth: 2, lastValueVisible: false, priceLineVisible: false });
        s.setData([{ time, value: price }]);
        pendingTrend.current = s;
      } else {
        if (pendingTrend.current) {
          pendingTrend.current.setData([
            { time: drawStart.current.time, value: drawStart.current.price },
            { time, value: price },
          ]);
          drawnLines.current.push({ id: `t_${Date.now()}`, series: pendingTrend.current });
          pendingTrend.current = null;
        }
        drawStart.current = null;
      }
    }
  }, [tool]);

  const clearDrawings = () => {
    drawnLines.current.forEach((d) => { try { chartRef.current?.removeSeries(d.series); } catch { /**/ } });
    drawnLines.current = [];
    drawStart.current  = null;
    pendingTrend.current = null;
  };

  const selectedSym = symbols.find((s) => s.symbol === symbol);

  // ── Indicator picker filtered list ──────────────────────────────────────────
  const filteredInds = IND_CATALOG.filter((ind) => {
    const matchCat = indCategory === "all" || ind.category === indCategory;
    const matchSearch = !indSearch || ind.name.toLowerCase().includes(indSearch.toLowerCase()) || ind.description.toLowerCase().includes(indSearch.toLowerCase());
    return matchCat && matchSearch;
  });

  function ToolBtn({ t, icon: Icon, title }: { t: DrawTool; icon: React.ElementType; title: string }) {
    return (
      <Button size="icon" variant={tool === t ? "default" : "ghost"} className="h-7 w-7" title={title} onClick={() => setTool(t)}>
        <Icon className="h-3.5 w-3.5" />
      </Button>
    );
  }

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="flex h-[calc(100vh-4rem)] w-full -mx-6 -mt-6 overflow-hidden">

      {/* ── Chart column ──────────────────────────────────────────────────── */}
      <div className="flex flex-col flex-1 min-w-0 bg-[#0a0a0c]">

        {/* Toolbar */}
        <div className="flex items-center gap-1.5 px-2 py-1 border-b border-border bg-card shrink-0 flex-wrap">

          {/* Symbol combobox */}
          <div className="relative" ref={dropdownRef}>
            <button
              onClick={() => { setDropdownOpen((o) => !o); setTickerSearch(""); }}
              className="h-7 w-44 px-2 flex items-center justify-between gap-1 rounded-md border border-border bg-background text-xs hover:bg-muted/50 transition-colors"
            >
              <span className="truncate font-medium">{symbol ? symbol.replace(".NS", "") : "Symbol\u2026"}</span>
              <svg className="h-3 w-3 text-muted-foreground shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M6 9l6 6 6-6"/></svg>
            </button>

            {dropdownOpen && (
              <div className="absolute top-8 left-0 z-50 w-80 rounded-md border border-border bg-popover shadow-xl flex flex-col overflow-hidden">
                {/* Search input */}
                <div className="flex items-center gap-1.5 px-2 py-1.5 border-b border-border">
                  <svg className="h-3.5 w-3.5 text-muted-foreground shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
                  <input
                    autoFocus
                    type="text"
                    value={tickerSearch}
                    onChange={(e) => setTickerSearch(e.target.value)}
                    placeholder="Search symbol or name…"
                    className="flex-1 bg-transparent text-xs outline-none placeholder:text-muted-foreground"
                  />
                  {tickerSearch && (
                    <button onClick={() => setTickerSearch("")} className="text-muted-foreground hover:text-foreground">
                      <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
                    </button>
                  )}
                </div>

                {/* Index filter pills */}
                <div className="flex gap-1 px-2 py-1.5 border-b border-border overflow-x-auto scrollbar-none">
                  {INDEX_TABS.map((tab) => (
                    <button
                      key={tab}
                      onClick={() => setTickerIndexFilter(tab)}
                      className={`shrink-0 px-2 py-0.5 rounded-full text-[10px] font-medium transition-colors ${
                        tickerIndexFilter === tab
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      {tab === "Nifty Midcap 150" ? "Midcap" : tab === "Nifty Smallcap 250" ? "Smallcap" : tab}
                    </button>
                  ))}
                </div>

                {/* Results list */}
                <div className="overflow-y-auto max-h-64">
                  {filteredSymbols.length === 0 ? (
                    <div className="text-xs text-muted-foreground text-center py-6">No results</div>
                  ) : filteredSymbols.map((s) => (
                    <button
                      key={s.id}
                      onClick={() => { setSymbol(s.symbol); loadChart(s.symbol, timeframe); setDropdownOpen(false); }}
                      className={`w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-muted/50 transition-colors border-b border-border/40 last:border-0 ${
                        s.symbol === symbol ? "bg-primary/10" : ""
                      }`}
                    >
                      <span className="font-semibold text-xs w-16 shrink-0 truncate">{s.symbol.replace(".NS", "")}</span>
                      <span className="text-[10px] text-muted-foreground truncate flex-1">{s.name ?? ""}</span>
                      {s.index_name && (
                        <span className="shrink-0 text-[9px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground font-medium">
                          {s.index_name === "Nifty 50" ? "N50" : s.index_name === "Nifty Next 50" ? "NN50" : s.index_name === "Nifty Midcap 150" ? "Mid" : "Sm"}
                        </span>
                      )}
                    </button>
                  ))}
                </div>

                {/* Footer count */}
                <div className="px-3 py-1 text-[10px] text-muted-foreground border-t border-border bg-muted/20">
                  {filteredSymbols.length} of {symbols.filter((s) => tickerIndexFilter === "All" || s.index_name === tickerIndexFilter).length} symbols
                </div>
              </div>
            )}
          </div>

          {/* Timeframes */}
          <div className="flex gap-0.5">
            {TIMEFRAMES.map((tf) => (
              <Button key={tf.value} size="sm" variant={timeframe === tf.value ? "default" : "ghost"} className="h-7 px-2 text-xs" onClick={() => setTimeframe(tf.value)}>
                {tf.label}
              </Button>
            ))}
          </div>

          <Separator orientation="vertical" className="h-4 mx-0.5" />

          {/* Indicator picker button + active badges */}
          <div className="flex items-center gap-1 flex-wrap">
            {/* Open panel button */}
            <button
              onClick={() => setShowIndicatorPanel((v) => !v)}
              className={`flex items-center gap-1 h-7 px-2.5 rounded-md border text-xs font-medium transition-colors ${
                showIndicatorPanel
                  ? "bg-primary/20 border-primary/40 text-primary"
                  : "border-border text-muted-foreground hover:text-foreground hover:bg-muted/40"
              }`}
            >
              <span className="text-sm leading-none">&#8853;</span>
              Indicators
            </button>

            {/* Active indicator badges */}
            {Array.from(activeInds).map((key) => {
              const def = IND_CATALOG.find((d) => d.key === key);
              if (!def) return null;
              return (
                <span
                  key={key}
                  className="inline-flex items-center gap-1 h-5 px-1.5 rounded text-[10px] font-medium"
                  style={{ backgroundColor: `${def.color}22`, border: `1px solid ${def.color}55`, color: def.color }}
                >
                  {def.name}
                  <button
                    onClick={() => toggleInd(key)}
                    className="opacity-60 hover:opacity-100 leading-none"
                    style={{ color: def.color }}
                    title={`Remove ${def.name}`}
                  >
                    &#10005;
                  </button>
                </span>
              );
            })}
          </div>

          <Separator orientation="vertical" className="h-4 mx-0.5" />

          {/* Draw tools */}
          <ToolBtn t="cursor"    icon={Move}       title="Cursor" />
          <ToolBtn t="hline"     icon={Minus}      title="H-Line" />
          <ToolBtn t="trendline" icon={TrendingUp} title="Trend line" />
          <Button size="icon" variant="ghost" className="h-7 w-7" title="Fit all"     onClick={() => chartRef.current?.timeScale().fitContent()}><ZoomIn className="h-3.5 w-3.5" /></Button>
          <Button size="icon" variant="ghost" className="h-7 w-7" title="Clear drawings" onClick={clearDrawings}><RefreshCw className="h-3 w-3" /></Button>

          {/* OHLC readout */}
          {ohlcInfo && (
            <div className="flex items-center gap-2 ml-1 text-[11px] font-mono text-muted-foreground">
              <span>O <span className="text-foreground">{ohlcInfo.o.toFixed(2)}</span></span>
              <span>H <span className="text-green-400">{ohlcInfo.h.toFixed(2)}</span></span>
              <span>L <span className="text-red-400">{ohlcInfo.l.toFixed(2)}</span></span>
              <span>C <span className={ohlcInfo.chg >= 0 ? "text-green-400" : "text-red-400"}>{ohlcInfo.c.toFixed(2)}</span></span>
              <span className={ohlcInfo.chg >= 0 ? "text-green-400" : "text-red-400"}>{ohlcInfo.chg >= 0 ? "+" : ""}{ohlcInfo.chg.toFixed(2)}%</span>
            </div>
          )}

          {loading && <span className="text-[11px] text-muted-foreground animate-pulse ml-2">Loading…</span>}

          <Button size="icon" variant="ghost" className="h-7 w-7 ml-auto" onClick={() => setSidebarOpen((o) => !o)} title="Toggle panel">
            <ChevronRight className={`h-4 w-4 transition-transform ${sidebarOpen ? "rotate-180" : ""}`} />
          </Button>
        </div>

        {/* Chart area (main + sub-panels in flex column) */}
        <div className="flex-1 min-h-0 flex flex-col relative overflow-hidden">

          {/* Indicator Picker Panel (floating overlay) */}
          {showIndicatorPanel && (
            <div className="absolute top-2 left-2 z-50 w-72 rounded-lg border border-border bg-[#111115] shadow-2xl flex flex-col overflow-hidden" style={{ maxHeight: "calc(100% - 16px)" }}>
              {/* Header */}
              <div className="flex items-center justify-between px-3 py-2 border-b border-border shrink-0">
                <span className="text-sm font-semibold text-foreground">Indicators</span>
                <button onClick={() => setShowIndicatorPanel(false)} className="text-muted-foreground hover:text-foreground text-sm leading-none px-1">&#10005;</button>
              </div>

              {/* Search */}
              <div className="px-2 py-1.5 border-b border-border shrink-0">
                <div className="flex items-center gap-1.5 rounded-md border border-border bg-background px-2 py-1">
                  <svg className="h-3 w-3 text-muted-foreground shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
                  <input
                    type="text"
                    value={indSearch}
                    onChange={(e) => setIndSearch(e.target.value)}
                    placeholder="Search indicators…"
                    className="flex-1 bg-transparent text-xs outline-none placeholder:text-muted-foreground"
                  />
                  {indSearch && (
                    <button onClick={() => setIndSearch("")} className="text-muted-foreground hover:text-foreground text-xs">&#10005;</button>
                  )}
                </div>
              </div>

              {/* Category tabs */}
              <div className="flex gap-0.5 px-2 py-1.5 border-b border-border overflow-x-auto scrollbar-none shrink-0">
                {(Object.keys(CATEGORY_LABELS) as IndCategory[]).map((cat) => (
                  <button
                    key={cat}
                    onClick={() => setIndCategory(cat)}
                    className={`shrink-0 px-2 py-0.5 rounded-full text-[10px] font-medium transition-colors ${
                      indCategory === cat
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {CATEGORY_LABELS[cat]}
                  </button>
                ))}
              </div>

              {/* Indicator list */}
              <div className="overflow-y-auto flex-1">
                {filteredInds.length === 0 ? (
                  <div className="text-xs text-muted-foreground text-center py-8">No indicators match</div>
                ) : filteredInds.map((ind) => {
                  const active = activeInds.has(ind.key);
                  return (
                    <button
                      key={ind.key}
                      onClick={() => toggleInd(ind.key)}
                      className={`w-full flex items-center gap-2 px-3 py-2.5 border-b border-border/60 text-left transition-colors hover:bg-muted/30 ${
                        active ? "border-l-2 bg-muted/20" : ""
                      }`}
                      style={active ? { borderLeftColor: ind.color } : undefined}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-semibold text-foreground truncate">{ind.name}</div>
                        <div className="text-[10px] text-muted-foreground truncate">{ind.description}</div>
                      </div>
                      {/* Toggle indicator */}
                      <div
                        className={`shrink-0 w-4 h-4 rounded-full border-2 flex items-center justify-center transition-colors`}
                        style={{
                          borderColor: ind.color,
                          backgroundColor: active ? ind.color : "transparent",
                        }}
                      >
                        {active && (
                          <svg className="w-2 h-2" viewBox="0 0 8 8" fill="white"><path d="M1.5 4l2 2 3-3" stroke="white" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Main chart canvas */}
          <div
            ref={mainRef}
            className={`flex-1 min-h-0 ${tool !== "cursor" ? "cursor-crosshair" : "cursor-default"}`}
            onClick={handleChartClick}
          />

          {/* RSI sub-panel */}
          {showRsi && (
            <div className="shrink-0 border-t border-border" style={{ height: "100px" }}>
              <div className="px-2 py-0.5 text-[10px] text-violet-400 font-medium bg-card border-b border-border">RSI (14)</div>
              <div ref={rsiRef} className="w-full" style={{ height: "calc(100% - 20px)" }} />
            </div>
          )}

          {/* MACD sub-panel */}
          {showMacd && (
            <div className="shrink-0 border-t border-border" style={{ height: "100px" }}>
              <div className="px-2 py-0.5 text-[10px] text-blue-400 font-medium bg-card border-b border-border">MACD (12, 26, 9)</div>
              <div ref={macdRef} className="w-full" style={{ height: "calc(100% - 20px)" }} />
            </div>
          )}

          {/* Stochastic sub-panel */}
          {showStoch && (
            <div className="shrink-0 border-t border-border" style={{ height: "100px" }}>
              <div className="px-2 py-0.5 text-[10px] text-orange-400 font-medium bg-card border-b border-border">Stoch (14,3)</div>
              <div ref={stochRef} className="w-full" style={{ height: "calc(100% - 20px)" }} />
            </div>
          )}

          {/* ADX sub-panel */}
          {showAdx && (
            <div className="shrink-0 border-t border-border" style={{ height: "100px" }}>
              <div className="px-2 py-0.5 text-[10px] text-purple-400 font-medium bg-card border-b border-border">ADX (14)</div>
              <div ref={adxRef} className="w-full" style={{ height: "calc(100% - 20px)" }} />
            </div>
          )}
        </div>

        {/* Active signal strip */}
        {activeSignal && (
          <div className="shrink-0 border-t border-border bg-card px-4 py-2 flex items-center gap-4 text-xs">
            <span className="font-semibold">{activeSignal.symbol.replace(".NS", "")}</span>
            <span className="text-muted-foreground">{activeSignal.pattern_name}</span>
            <ConfidenceBadge score={activeSignal.confidence_score} />
            {activeSignal.key_levels?.entry     && <span className="text-blue-400">Entry: {activeSignal.key_levels.entry}</span>}
            {activeSignal.key_levels?.stop_loss && <span className="text-red-400">SL: {activeSignal.key_levels.stop_loss}</span>}
            {activeSignal.key_levels?.resistance && <span className="text-yellow-400">R: {activeSignal.key_levels.resistance}</span>}
            {activeSignal.llm_analysis && <span className="text-muted-foreground truncate max-w-sm">{activeSignal.llm_analysis}</span>}
            <Button size="sm" variant="ghost" className="h-6 text-xs ml-auto px-2" onClick={() => setActiveSignal(null)}>&#10005;</Button>
          </div>
        )}
      </div>

      {/* ── Right sidebar ─────────────────────────────────────────────────── */}
      {sidebarOpen && (
        <div className="w-64 shrink-0 border-l border-border bg-card flex flex-col overflow-hidden">

          {/* Tabs: Signals / Patterns */}
          <div className="flex border-b border-border shrink-0">
            {(["signals", "patterns"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setShowPatterns(tab === "patterns")}
                className={`flex-1 py-2 text-[11px] font-medium transition-colors ${
                  (tab === "patterns") === showPatterns
                    ? "text-primary border-b-2 border-primary"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {tab === "signals" ? `Signals (${signals.length})` : `Patterns (${chartPatterns.length + cdlPatterns.length})`}
              </button>
            ))}
          </div>

          {/* Signals tab */}
          {!showPatterns && (
            <>
              <div className="px-3 py-1.5 border-b border-border shrink-0">
                <p className="text-[10px] text-muted-foreground">{selectedSym?.symbol.replace(".NS", "") ?? "…"} · click to jump</p>
              </div>
              <div className="flex-1 overflow-y-auto">
                {signals.length === 0 ? (
                  <div className="text-xs text-muted-foreground text-center py-10 px-3">No signals yet.<br />Run a scan first.</div>
                ) : signals.map((sig) => (
                  <button key={sig.id} onClick={() => { setSymbol(sig.symbol); jumpToSignal(sig); }}
                    className={`w-full text-left px-3 py-2.5 border-b border-border/60 hover:bg-muted/40 transition-colors ${activeSignal?.id === sig.id ? "bg-primary/10 border-l-2 border-l-primary pl-2.5" : ""}`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-medium truncate max-w-[120px]">{sig.pattern_name ?? "Signal"}</span>
                      <ConfidenceBadge score={sig.confidence_score} />
                    </div>
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <Badge variant="outline" className={`text-[10px] px-1 py-0 h-4 ${sig.status === "pending" ? "text-yellow-400 border-yellow-500/30" : sig.status === "reviewed" ? "text-blue-400 border-blue-500/30" : "text-muted-foreground"}`}>
                        {sig.status}
                      </Badge>
                      <span className="text-[10px] text-muted-foreground">
                        {new Date(sig.triggered_at).toLocaleDateString("en-IN", { day: "2-digit", month: "short" })}
                      </span>
                    </div>
                    {sig.key_levels?.entry && (
                      <div className="flex gap-2 mt-1 text-[10px]">
                        <span className="text-blue-400">E {sig.key_levels.entry}</span>
                        {sig.key_levels.stop_loss && <span className="text-red-400">SL {sig.key_levels.stop_loss}</span>}
                      </div>
                    )}
                  </button>
                ))}
              </div>
              <div className="shrink-0 border-t border-border p-2 space-y-1.5">
                <Button variant="outline" size="sm" className="w-full text-xs h-7" onClick={() => { if (signals.length > 0) jumpToSignal(signals[0]); }}>
                  <ArrowUpToLine className="h-3 w-3 mr-1" /> Latest Signal
                </Button>
                <Button variant="ghost" size="sm" className="w-full text-xs h-7 text-muted-foreground" onClick={() => loadChart(symbol, timeframe)}>
                  <RefreshCw className="h-3 w-3 mr-1" /> Reload
                </Button>
              </div>
            </>
          )}

          {/* Patterns tab */}
          {showPatterns && (
            <div className="flex-1 overflow-y-auto">
              {/* Reset focus banner */}
              {(activePattern || activeCdlPattern) && (
                <div className="flex items-center justify-between px-3 py-2 bg-primary/10 border-b border-primary/30 shrink-0">
                  <span className="text-[10px] text-primary font-medium truncate">
                    {activePattern ? `Focused: ${activePattern.type.replace(/_/g, " ")}` : `Focused: ${activeCdlPattern?.pattern}`}
                  </span>
                  <button
                    onClick={resetPatternFocus}
                    className="ml-2 shrink-0 flex items-center gap-1 px-2 py-0.5 rounded text-[10px] bg-muted hover:bg-muted/80 text-muted-foreground hover:text-foreground border border-border transition-colors"
                  >
                    &#10005; Reset
                  </button>
                </div>
              )}
              {chartPatterns.length === 0 && cdlPatterns.length === 0 ? (
                <div className="text-xs text-muted-foreground text-center py-10 px-3">No patterns detected.<br />Load a symbol first.</div>
              ) : (
                <>
                  {/* Chart patterns */}
                  {chartPatterns.length > 0 && (
                    <div>
                      <div className="px-3 py-1.5 text-[10px] text-muted-foreground font-semibold uppercase tracking-wide border-b border-border bg-muted/30">
                        Chart Patterns ({chartPatterns.length})
                      </div>
                      {chartPatterns.map((p, i) => {
                        const isActive = activePattern?.type === p.type && activePattern?.start_date === p.start_date;
                        return (
                          <button
                            key={i}
                            onClick={() => jumpToPattern(p)}
                            className={`w-full text-left px-3 py-2.5 border-b border-border/60 transition-colors ${
                              isActive
                                ? "bg-primary/10 border-l-2 border-l-primary pl-2.5"
                                : "hover:bg-muted/30 cursor-pointer"
                            }`}
                          >
                            <div className="flex items-center justify-between mb-0.5">
                              <span className="text-xs font-medium capitalize">{p.type.replace(/_/g, " ")}</span>
                              <span className={`text-[10px] font-medium ${p.direction === "bullish" ? "text-green-400" : p.direction === "bearish" ? "text-red-400" : "text-muted-foreground"}`}>
                                {p.direction} · {p.confidence}%
                              </span>
                            </div>
                            <p className="text-[10px] text-muted-foreground leading-tight">{p.description}</p>
                            {p.key_levels?.target && (
                              <div className="flex gap-2 mt-1 text-[10px]">
                                {p.key_levels.resistance && <span className="text-yellow-400">R {p.key_levels.resistance}</span>}
                                {p.key_levels.support    && <span className="text-green-400">S {p.key_levels.support}</span>}
                                <span className="text-blue-400">T {p.key_levels.target}</span>
                              </div>
                            )}
                            <div className="text-[10px] text-muted-foreground/60 mt-0.5">
                              {p.start_date} → {p.end_date} · click to navigate ↗
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  )}

                  {/* Candlestick patterns */}
                  {cdlPatterns.length > 0 && (
                    <div>
                      <div className="px-3 py-1.5 text-[10px] text-muted-foreground font-semibold uppercase tracking-wide border-b border-border bg-muted/30">
                        Candlestick Patterns ({cdlPatterns.length})
                      </div>
                      {cdlPatterns.map((p, i) => {
                        const isCdlActive = activeCdlPattern?.pattern === p.pattern && activeCdlPattern?.date === p.date;
                        return (
                          <button
                            key={i}
                            onClick={() => jumpToCdl(p)}
                            className={`w-full text-left px-3 py-2 border-b border-border/60 transition-colors ${
                              isCdlActive ? "bg-primary/10 border-l-2 border-l-primary pl-2.5" : "hover:bg-muted/30 cursor-pointer"
                            }`}
                          >
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-medium">{p.pattern}</span>
                              <span className={`text-[10px] ${p.direction === "bullish" ? "text-green-400" : p.direction === "bearish" ? "text-red-400" : "text-muted-foreground"}`}>
                                {p.direction}
                              </span>
                            </div>
                            <div className="text-[10px] text-muted-foreground/60 mt-0.5">
                              {p.date} · click to navigate ↗
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
