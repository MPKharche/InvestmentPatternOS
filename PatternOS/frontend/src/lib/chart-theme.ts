/**
 * Shared lightweight-charts styling for equity Chart Tool, signals widget, and MF charts.
 */
import { ColorType, CrosshairMode } from "lightweight-charts";

/** Canonical dark surface (equity Chart Tool, indicator playground). */
export const PATTERN_OS_BG = "#0a0a0c";
export const PATTERN_OS_GRID = "#111115";

/** Base options for equity `/chart` main chart and oscillator panels. */
export const patternOsChartToolBase = {
  layout: {
    background: { type: ColorType.Solid, color: PATTERN_OS_BG },
    textColor: "#9ca3af",
    fontSize: 11,
  },
  grid: {
    vertLines: { color: PATTERN_OS_GRID },
    horzLines: { color: PATTERN_OS_GRID },
  },
  crosshair: {
    mode: CrosshairMode.Normal,
    vertLine: { color: "#374151", labelBackgroundColor: "#1f2937" },
    horzLine: { color: "#374151", labelBackgroundColor: "#1f2937" },
  },
  timeScale: { borderColor: "#1f2937", timeVisible: true, secondsVisible: false },
} as const;

/** Default candle colours across PatternOS charts. */
export const patternOsCandlestickSeriesDefaults = {
  upColor: "#22c55e",
  downColor: "#ef4444",
  borderUpColor: "#22c55e",
  borderDownColor: "#ef4444",
  wickUpColor: "#22c55e",
  wickDownColor: "#ef4444",
} as const;

const MF_GRID = "rgba(148,163,184,0.08)";
const MF_SCALE_BORDER = "rgba(148,163,184,0.15)";

/**
 * MF charts on cards: transparent background with same crosshair semantics as equity.
 */
export function patternOsChartMfCardOptions(opts?: {
  height?: number;
  /** Upper panes often hide the timeline; bottom pane shows it. */
  timeScaleVisible?: boolean;
}) {
  const tv = opts?.timeScaleVisible !== false;
  return {
    layout: {
      background: { type: ColorType.Solid, color: "transparent" },
      textColor: "#e5e7eb",
      fontSize: 11,
    },
    grid: {
      vertLines: { color: MF_GRID },
      horzLines: { color: MF_GRID },
    },
    crosshair: patternOsChartToolBase.crosshair,
    rightPriceScale: { borderColor: MF_SCALE_BORDER, minimumWidth: 72 },
    timeScale: {
      borderColor: MF_SCALE_BORDER,
      visible: tv,
      timeVisible: true,
      secondsVisible: false,
    },
    ...(opts?.height != null ? { height: opts.height } : {}),
  };
}

/** RSI/MACD sub-panes under MF main chart (locked scroll; synced range). */
export function patternOsChartMfSubPaneOptions(args: {
  height: number;
  timeScaleVisible: boolean;
}) {
  return {
    ...patternOsChartMfCardOptions({ height: args.height, timeScaleVisible: args.timeScaleVisible }),
    handleScroll: false,
    handleScale: false,
  };
}
