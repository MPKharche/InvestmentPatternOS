"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import {
  createChart,
  LineSeries,
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

export default function MFSchemeDetailPage() {
  const params = useParams<{ scheme_code: string }>();
  const schemeCode = Number(params.scheme_code);

  const [scheme, setScheme] = useState<MFScheme | null>(null);
  const [nav, setNav] = useState<MFNavPoint[]>([]);
  const [indicators, setIndicators] = useState<MFIndicatorRecord[]>([]);
  const [patterns, setPatterns] = useState<MFPatternsResponse | null>(null);
  const [metrics, setMetrics] = useState<any>(null);
  const [holdings, setHoldings] = useState<any>(null);
  const [signals, setSignals] = useState<MFSignal[]>([]);
  const [loading, setLoading] = useState(true);

  const chartRef = useRef<HTMLDivElement>(null);
  const chartApi = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Line"> | null>(null);
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

  const [timeframe, setTimeframe] = useState<"1M" | "3M" | "6M" | "1Y" | "3Y" | "5Y" | "10Y" | "MAX">("MAX");
  const [barTf, setBarTf] = useState<"1d" | "1w" | "1M">("1d");
  const [rawOhlc, setRawOhlc] = useState<MFOhlcBar[]>([]);
  const [activeInds, setActiveInds] = useState<Set<IndKey>>(new Set(["ema20", "ema50", "rsi"]));
  const showRsi = activeInds.has("rsi");
  const showMacd = activeInds.has("macd");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const indLimit = barTf === "1M" ? 8200 : barTf === "1w" ? 3800 : 5200;
      const emptyOhlc = { scheme_code: schemeCode, tf: barTf, style: "line" as const, series: [] as MFOhlcBar[] };
      const [s, n, ohlcRes, inds, pats, m, sigs] = await Promise.all([
        mfApi.scheme(schemeCode),
        mfApi.nav(schemeCode, 5000),
        mfApi.ohlc(schemeCode, barTf, "line", 5000).catch(() => emptyOhlc),
        mfApi.indicators(schemeCode, indLimit, barTf),
        mfApi.patterns(schemeCode, 220, barTf),
        mfApi.metrics(schemeCode),
        mfApi.signals("all", 400),
      ]);
      setScheme(s);
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
  }, [schemeCode, barTf]);

  useEffect(() => {
    void load();
  }, [load]);

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

  // Init chart
  useEffect(() => {
    if (!chartRef.current) return;
    const c = createChart(chartRef.current, {
      layout: { textColor: "#e5e7eb", background: { type: ColorType.Solid, color: "transparent" } },
      grid: { vertLines: { color: "rgba(148,163,184,0.08)" }, horzLines: { color: "rgba(148,163,184,0.08)" } },
      // Force consistent plot widths across panes so X alignment stays visually synced.
      rightPriceScale: { borderColor: "rgba(148,163,184,0.15)", minimumWidth: 72 },
      // In multi-panel mode we show the timeline only on the bottom-most pane to avoid "out of sync" labels.
      timeScale: { borderColor: "rgba(148,163,184,0.15)", visible: false },
      height: 260,
    });
    const s = c.addSeries(LineSeries, { color: "#38bdf8", lineWidth: 2, priceLineVisible: false, lastValueVisible: true });
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
  }, []);

  // Set chart data (resampled close when OHLC available)
  useEffect(() => {
    if (!seriesRef.current) return;
    if (!chartTimes.length) return;
    const data =
      filteredOhlc.length > 0
        ? filteredOhlc.map((o) => ({ time: o.time as Time, value: o.close }))
        : filteredNav.map((p) => ({ time: p.nav_date as Time, value: p.nav }));
    seriesRef.current.setData(data);
    chartApi.current?.timeScale().fitContent();
  }, [chartTimes, filteredOhlc, filteredNav]);

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

  useEffect(() => {
    if (!markersRef.current) return;
    const markers: SeriesMarker<Time>[] = [];

    const min = chartWindow?.start ?? (filteredNav.length ? filteredNav[0].nav_date : null);
    const max = chartWindow?.end ?? (filteredNav.length ? filteredNav[filteredNav.length - 1].nav_date : null);

    for (const s of signals) {
      if (!s.nav_date) continue;
      // Only show markers within the visible timeframe window to avoid clutter.
      if (min && max && (s.nav_date < min || s.nav_date > max)) continue;
      const col = s.confidence_score >= 80 ? "#22c55e" : s.confidence_score >= 70 ? "#f59e0b" : "#ef4444";
      markers.push({
        time: s.nav_date as Time,
        position: "aboveBar",
        color: col,
        shape: "circle",
        text: s.signal_type.slice(0, 12),
      });
    }

    const talib = (patterns?.talib_candlestick_patterns || []) as any[];
    const native = (patterns?.candlestick_patterns || []) as any[];
    const allPats = [
      ...talib.map((p) => ({ time: p?.time, label: p?.name, direction: p?.direction })),
      ...native.map((p) => ({ time: p?.date, label: p?.pattern, direction: p?.direction })),
    ].filter((p) => p.time && p.label);

    const patInWindow = allPats.filter((p) => !min || !max || (String(p.time) >= min && String(p.time) <= max));
    // Keep the chart readable: only show the most recent few pattern marks.
    patInWindow.sort((a, b) => String(a.time).localeCompare(String(b.time)));
    const recent = patInWindow.slice(Math.max(0, patInWindow.length - 8));
    for (const p of recent) {
      const bullish = p.direction === "bullish";
      markers.push({
        time: p.time as Time,
        position: bullish ? "belowBar" : "aboveBar",
        color: bullish ? "#22c55e" : "#ef4444",
        shape: bullish ? "arrowUp" : "arrowDown",
        text: String(p.label || "").slice(0, 12),
      });
    }
    markersRef.current.setMarkers(markers);
  }, [signals, patterns, filteredNav, chartWindow]);

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
  }, [showRsi]);

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
  }, [showRsi, showMacd, chartTimes.length, barTf]);

  // Sync crosshair across panes so the vertical marker aligns (main chart drives).
  const syncingCrosshair = useRef(false);
  useEffect(() => {
    const main = chartApi.current;
    const mainSeries = seriesRef.current;
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
        const px = priceByTime.get(t);
        if (px != null) main.setCrosshairPosition(px, t as any, mainSeries as any);
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
        const px = priceByTime.get(t);
        if (px != null) main.setCrosshairPosition(px, t as any, mainSeries as any);
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
  }, [indByTime, priceByTime, showRsi, showMacd]);

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

  const pdfHref = `/api/mf/report/${schemeCode}`;

  const [linksOpen, setLinksOpen] = useState(false);
  const [vrUrl, setVrUrl] = useState("");
  const [vrFundId, setVrFundId] = useState("");
  const [msUrl, setMsUrl] = useState("");
  const [msId, setMsId] = useState("");
  const [yahooSymbol, setYahooSymbol] = useState("");
  const [yahooUrl, setYahooUrl] = useState("");
  const [savingLinks, setSavingLinks] = useState(false);

  const externalSiteSearch = (siteHost: string) => {
    const q = `${scheme?.scheme_name ?? `Scheme ${schemeCode}`} ${scheme?.amc_name ?? ""}`.trim();
    return `https://www.google.com/search?q=${encodeURIComponent(`site:${siteHost} ${q}`)}`;
  };

  useEffect(() => {
    setVrUrl(scheme?.valueresearch_url ?? "");
    setVrFundId(scheme?.value_research_fund_id != null ? String(scheme.value_research_fund_id) : "");
    setMsUrl(scheme?.morningstar_url ?? "");
    setMsId(scheme?.morningstar_sec_id ?? "");
    setYahooSymbol(scheme?.yahoo_finance_symbol ?? "");
    setYahooUrl(scheme?.yahoo_finance_url ?? "");
  }, [
    scheme?.valueresearch_url,
    scheme?.value_research_fund_id,
    scheme?.morningstar_url,
    scheme?.morningstar_sec_id,
    scheme?.yahoo_finance_symbol,
    scheme?.yahoo_finance_url,
  ]);

  const saveLinks = async () => {
    setSavingLinks(true);
    try {
      const vrIdTrim = vrFundId.trim();
      let vrIdNum: number | null = null;
      if (vrIdTrim !== "") {
        const n = parseInt(vrIdTrim, 10);
        vrIdNum = Number.isFinite(n) ? n : null;
      }
      const res = await mfApi.updateSchemeLinks(schemeCode, {
        valueresearch_url: vrUrl.trim() || null,
        morningstar_url: msUrl.trim() || null,
        yahoo_finance_url: yahooUrl.trim() || null,
        morningstar_sec_id: msId.trim() || null,
        value_research_fund_id: vrIdNum,
        yahoo_finance_symbol: yahooSymbol.trim() || null,
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
                  <Label>Value Research fund id</Label>
                  <Input value={vrFundId} onChange={(e) => setVrFundId(e.target.value)} placeholder="e.g. 15822" />
                  <p className="text-[11px] text-muted-foreground">Numeric id from valueresearchonline.com fund URLs (stable deep link).</p>
                </div>
                <div className="space-y-1.5">
                  <Label>ValueResearch URL (optional override)</Label>
                  <Input value={vrUrl} onChange={(e) => setVrUrl(e.target.value)} placeholder="https://..." />
                </div>
                <div className="space-y-1.5">
                  <Label>Morningstar URL</Label>
                  <Input value={msUrl} onChange={(e) => setMsUrl(e.target.value)} placeholder="https://..." />
                </div>
                <div className="space-y-1.5">
                  <Label>Morningstar SECID (optional)</Label>
                  <Input value={msId} onChange={(e) => setMsId(e.target.value)} placeholder="f0gbr06s37" />
                </div>
                <div className="space-y-1.5">
                  <Label>Yahoo Finance symbol</Label>
                  <Input value={yahooSymbol} onChange={(e) => setYahooSymbol(e.target.value)} placeholder="e.g. 0P0000XWAB.BO" />
                </div>
                <div className="space-y-1.5">
                  <Label>Yahoo quote URL (optional override)</Label>
                  <Input value={yahooUrl} onChange={(e) => setYahooUrl(e.target.value)} placeholder="https://finance.yahoo.com/quote/…" />
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
          {scheme?.morningstar_url ? (
            <Link href={scheme.morningstar_url} target="_blank">
              <Button variant="outline" size="sm">Morningstar</Button>
            </Link>
          ) : null}
          <Link href={scheme?.yahoo_finance_url ?? externalSiteSearch("finance.yahoo.com")} target="_blank">
            <Button variant="outline" size="sm">Yahoo Finance</Button>
          </Link>
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
            {scheme?.nav_days_in_db != null && scheme.nav_days_in_db > 0 ? (
              <p className="text-xs text-muted-foreground font-normal mt-1">
                {scheme.nav_days_in_db.toLocaleString()} day(s) in database
                {scheme.nav_date_min && scheme.nav_date_max
                  ? ` (${scheme.nav_date_min} → ${scheme.nav_date_max})`
                  : null}
                {nav.length >= 5000 && scheme.nav_days_in_db > 5000
                  ? " — chart uses the most recent 5,000 points."
                  : null}
              </p>
            ) : null}
          </CardHeader>
          <CardContent>
            {scheme?.nav_days_in_db != null && scheme.nav_days_in_db < 30 ? (
              <div
                className="mb-3 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-100/90"
                role="status"
              >
                <p className="font-medium text-amber-50">Sparse NAV history</p>
                <p className="mt-1 text-xs leading-relaxed opacity-95">
                  This chart reads daily NAV from the database (<code className="rounded bg-black/30 px-1">mf_nav_daily</code>
                  ). Only {scheme.nav_days_in_db} row(s) exist for AMFI {schemeCode}. The Kaggle historical load does not run on deploy — run{" "}
                  <code className="rounded bg-black/30 px-1">backend/scripts/mf_seed_historical.py</code> against{" "}
                  <strong>this</strong> Postgres (see script docstring), then{" "}
                  <Link href="/mf/pipelines" className="underline font-medium text-amber-50">
                    MF → Pipeline runs
                  </Link>
                  : Sync priority AMC watchlist, then Run NAV. Daily AMFI alone only adds the latest file date per ingest.
                </p>
              </div>
            ) : null}
            <div className="flex flex-col gap-2 mb-2">
              <div className="flex flex-wrap items-center gap-2">
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
                {(
                  [
                    { value: "1d" as const, label: "D" },
                    { value: "1w" as const, label: "W" },
                    { value: "1M" as const, label: "M" },
                  ] as const
                ).map((b) => (
                  <Button
                    key={b.value}
                    size="sm"
                    variant={barTf === b.value ? "secondary" : "outline"}
                    title="Bar timeframe (NAV resampling)"
                    onClick={() => setBarTf(b.value)}
                  >
                    {b.label}
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
      </div>
    </div>
  );
}
