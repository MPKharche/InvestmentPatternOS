/**
 * Typed API client — all backend calls go through here.
 * Base URL is read from NEXT_PUBLIC_API_BASE_URL env var.
 */

// Default to same-origin API proxy (see next.config.ts rewrites) so non-technical users
// don't need to think about ports/CORS in local setup.
const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/v1";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const maxRetries = 3;
  const backoffMs = 1000;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const res = await fetch(`${BASE}${path}`, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });

      if (!res.ok) {
        // If it's a 5xx error or 429 (Rate Limit), retry
        if ((res.status >= 500 || res.status === 429) && attempt < maxRetries) {
          const delay = backoffMs * Math.pow(2, attempt);
          await new Promise((resolve) => setTimeout(resolve, delay));
          continue;
        }
        const err = await res.text();
        throw new Error(`API error ${res.status}: ${err}`);
      }
      return res.json() as Promise<T>;
    } catch (error) {
      if (attempt === maxRetries) {
        throw error;
      }
      const delay = backoffMs * Math.pow(2, attempt);
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }
  throw new Error("Request failed after maximum retries");
}

// ─── Types ────────────────────────────────────────────────────────────────────

export interface UniverseItem {
  id: string;
  symbol: string;
  exchange: string;
  asset_class: string;
  name: string | null;
  active: boolean;
  sector: string | null;
  index_name: string | null;
}

export interface Pattern {
  id: string;
  name: string;
  description: string | null;
  asset_class: string;
  timeframes: string[];
  status: string;
  current_version: number;
  created_at: string;
  updated_at: string;
}

export interface PatternVersion {
  id: string;
  pattern_id: string;
  version: number;
  rulebook_json: Record<string, unknown>;
  change_summary: string | null;
  approved_at: string | null;
  created_at: string;
}

export interface Signal {
  id: string;
  pattern_id: string;
  pattern_name: string | null;
  symbol: string;
  exchange: string;
  timeframe: string;
  triggered_at: string;
  confidence_score: number;
  base_score: number | null;
  status: string;
  llm_analysis: string | null;
  key_levels: {
    entry?: number;
    support?: number;
    resistance?: number;
    stop_loss?: number;
  } | null;
  /** Pre-inbox AI equity desk (stance, headline, body, sources, searx_used, crawl_used). */
  equity_research_note?: Record<string, unknown> | null;
  /** When enough OHLCV exists after the signal bar, projected % from entry (else null). */
  forward_horizon_returns?: {
    entry_bar_date?: string;
    entry_close?: number;
    horizons_trading_days?: Record<string, number>;
    pct?: Record<string, number | null>;
  } | null;
}

export interface Outcome {
  id: string;
  signal_id: string;
  result: string | null;
  exit_price: number | null;
  pnl_pct: number | null;
  notes: string | null;
  feedback: string | null;
  recorded_at: string;
}

export interface PatternStats {
  pattern_id: string;
  pattern_name: string;
  total_signals: number;
  reviewed: number;
  executed: number;
  hit_target: number;
  stopped_out: number;
  win_rate: number | null;
  avg_pnl_pct: number | null;
}

export interface AnalyticsSummary {
  total_signals: number;
  pending_review: number;
  executed_trades: number;
  hit_target: number;
  stopped_out: number;
  active_patterns: number;
  overall_win_rate: number | null;
}

export interface LearningLog {
  id: string;
  pattern_id: string;
  source: string;
  insight_text: string;
  version_applied: number | null;
  created_at: string;
}

export interface ChatMessage {
  role: string;
  content: string;
  created_at?: string;
}

export interface ChatResponse {
  pattern_id: string;
  reply: string;
  rulebook_draft: Record<string, unknown> | null;
}

export interface PatternEvent {
  id: string;
  symbol: string;
  timeframe: string;
  detected_at: string;
  entry_price: number | null;
  /** Present when event came from a backtest run; use to scope roll-ups. */
  backtest_run_id?: string | null;
  ret_5d: number | null;
  ret_10d: number | null;
  ret_20d: number | null;
  /** ~1m / ~3m / ~6m forward (trading-day approx on daily bars). */
  ret_21d: number | null;
  ret_63d: number | null;
  ret_126d: number | null;
  max_gain_20d: number | null;
  max_loss_20d: number | null;
  outcome: string | null;
  indicator_snapshot: Record<string, number> | null;
  user_feedback: string | null;
  user_notes: string | null;
}

export interface BacktestRun {
  id: string;
  version_num: number;
  status: string;
  engine?: "internal" | "vectorbt" | string;
  symbols_scanned: number;
  events_found: number;
  success_count: number;
  failure_count: number;
  neutral_count: number;
  success_rate: number | null;
  avg_ret_5d: number | null;
  avg_ret_10d: number | null;
  avg_ret_20d: number | null;
  stats_json?: Record<string, unknown> | null;
  started_at: string;
  completed_at: string | null;
}

/** LLM-estimated deltas vs current backtest (percentage points where noted). */
export interface RulebookSuggestionDelta {
  success_rate_pct?: number | null;
  coverage_events_pct?: number | null;
  avg_raw_ret_1w_pct?: number | null;
  avg_raw_ret_1m_pct?: number | null;
  avg_raw_ret_3m_pct?: number | null;
}

export interface RulebookSuggestion {
  type: string;
  condition: string;
  rationale: string;
  estimated_delta?: RulebookSuggestionDelta | null;
  apply_patch?: Record<string, unknown> | null;
}

export interface PatternStudyResult {
  id: string;
  analysis: string;
  success_factors: string[] | null;
  failure_factors: string[] | null;
  rulebook_suggestions: RulebookSuggestion[] | null;
  confidence_improvements: string[] | null;
  created_at: string;
}

export interface PatternCandidate {
  id: string;
  title: string;
  objective: string;
  source_type: string;
  screenshot_refs: string[] | null;
  traits_json: Record<string, unknown>;
  draft_rules_json: Record<string, unknown>;
  conditions_json: Record<string, unknown>;
  universes_json: string[];
  status: string;
  validation_summary: Record<string, unknown> | null;
  revision_notes: string | null;
  linked_pattern_id: string | null;
  created_at: string;
  updated_at: string;
}

export type PatternCandidateCreate = {
  title: string;
  objective: string;
  source_type?: string;
  screenshot_refs?: string[];
  traits_json?: Record<string, unknown>;
  draft_rules_json?: Record<string, unknown>;
  conditions_json?: Record<string, unknown>;
  universes_json?: string[];
};

export type PatternCandidateUpdate = {
  title?: string;
  objective?: string;
  screenshot_refs?: string[];
  traits_json?: Record<string, unknown>;
  draft_rules_json?: Record<string, unknown>;
  conditions_json?: Record<string, unknown>;
  universes_json?: string[];
  status?: string;
  validation_summary?: Record<string, unknown>;
  revision_notes?: string;
};

// ─── Universe ─────────────────────────────────────────────────────────────────

export const universeApi = {
  list: (activeOnly = true, search?: string, indexName?: string) => {
    const params = new URLSearchParams({ active_only: String(activeOnly) });
    if (search) params.set("search", search);
    if (indexName) params.set("index_name", indexName);
    return request<UniverseItem[]>(`/universe/?${params}`);
  },
  indices: () => request<string[]>("/universe/indices"),
  add: (body: { symbol: string; exchange: string; asset_class: string; name?: string }) =>
    request<UniverseItem>("/universe/", { method: "POST", body: JSON.stringify(body) }),
  toggle: (id: string) =>
    request<UniverseItem>(`/universe/${id}/toggle`, { method: "PATCH" }),
  remove: (id: string) =>
    request<void>(`/universe/${id}`, { method: "DELETE" }),
};

// ─── Patterns ─────────────────────────────────────────────────────────────────

export const patternsApi = {
  list: () => request<Pattern[]>("/patterns/"),
  get: (id: string) => request<Pattern>(`/patterns/${id}`),
  create: (body: { name: string; description?: string; asset_class?: string; timeframes?: string[] }) =>
    request<Pattern>("/patterns/", { method: "POST", body: JSON.stringify(body) }),
  setStatus: (id: string, status: string) =>
    request<{ ok: boolean }>(`/patterns/${id}/status?status=${status}`, { method: "PATCH" }),
  versions: (id: string) => request<PatternVersion[]>(`/patterns/${id}/versions`),
  createVersion: (id: string, body: { rulebook_json: Record<string, unknown>; change_summary?: string | null }) =>
    request<PatternVersion>(`/patterns/${id}/versions`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  learning: (id: string) => request<LearningLog[]>(`/patterns/${id}/learning`),
};

// ─── Studio ───────────────────────────────────────────────────────────────────

export const studioApi = {
  listCandidates: (status?: string) => {
    const q = status ? `?status=${encodeURIComponent(status)}` : "";
    return request<PatternCandidate[]>(`/studio/candidates${q}`);
  },
  getCandidate: (id: string) => request<PatternCandidate>(`/studio/candidates/${id}`),
  createCandidate: (body: PatternCandidateCreate) =>
    request<PatternCandidate>("/studio/candidates", { method: "POST", body: JSON.stringify(body) }),
  updateCandidate: (id: string, body: PatternCandidateUpdate) =>
    request<PatternCandidate>(`/studio/candidates/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  finalizeCandidate: (id: string) =>
    request<{ ok: boolean; pattern_id: string; message?: string }>(
      `/studio/candidates/${id}/finalize`,
      { method: "POST", body: JSON.stringify({}) }
    ),
  chat: (body: { pattern_id?: string; message: string }) =>
    request<ChatResponse>("/studio/chat", { method: "POST", body: JSON.stringify(body) }),
  history: (patternId: string) =>
    request<ChatMessage[]>(`/studio/${patternId}/history`),
  runBacktest: (patternId: string, params?: { scope?: string; symbols?: string; engine?: "internal" | "vectorbt" }) => {
    const engine = params?.engine ?? "internal";
    const qs = new URLSearchParams({ engine });
    const body = { ...(params ?? {}) };
    delete (body as any).engine;
    return request<{ run_id: string; status: string }>(`/studio/${patternId}/backtest?${qs}`, {
      method: "POST",
      body: JSON.stringify(body)
    });
  },
  getBacktestRuns: (patternId: string) =>
    request<BacktestRun[]>(`/studio/${patternId}/backtest/runs`),
  getEvents: (
    patternId: string,
    params?: {
      symbol?: string;
      outcome?: string;
      backtest_run_id?: string;
      limit?: number;
      offset?: number;
    }
  ) => {
    const p = new URLSearchParams();
    if (params?.symbol) p.set("symbol", params.symbol);
    if (params?.outcome) p.set("outcome", params.outcome);
    if (params?.backtest_run_id) p.set("backtest_run_id", params.backtest_run_id);
    if (params?.limit !== undefined) p.set("limit", String(params.limit));
    if (params?.offset !== undefined) p.set("offset", String(params.offset));
    return request<{ total: number; events: PatternEvent[] }>(`/studio/${patternId}/events?${p}`);
  },
  updateEventFeedback: (eventId: string, feedback: string, notes?: string) =>
    fetch(`${BASE}/studio/events/${eventId}/feedback`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feedback, notes: notes ?? null }),
    }).then((r) => r.json()),
  generateStudy: (patternId: string) =>
    request<PatternStudyResult>(`/studio/${patternId}/study`, { method: "POST", body: JSON.stringify({}) }),
  getLatestStudy: (patternId: string) =>
    request<PatternStudyResult | null>(`/studio/${patternId}/study/latest`),
  applyStudyPatches: (patternId: string, body: { patches: Record<string, unknown>[]; change_summary: string }) =>
    request<{ ok: boolean; version: number; pattern_version_id: string }>(
      `/studio/${patternId}/study/apply-patches`,
      { method: "POST", body: JSON.stringify(body) }
    ),
};

// ─── Signals ─────────────────────────────────────────────────────────────────

export const signalsApi = {
  list: (status = "pending", patternId?: string, limit = 50) => {
    const params = new URLSearchParams({ status, limit: String(limit) });
    if (patternId) params.set("pattern_id", patternId);
    return request<Signal[]>(`/signals/?${params}`);
  },
  get: (id: string) => request<Signal>(`/signals/${id}`),
  review: (id: string, body: {
    action: string;
    entry_price?: number;
    sl_price?: number;
    target_price?: number;
    notes?: string;
  }) =>
    request<{ ok: boolean }>(`/signals/${id}/review`, { method: "POST", body: JSON.stringify(body) }),
};

// ─── Outcomes ─────────────────────────────────────────────────────────────────

export const outcomesApi = {
  list: () => request<Outcome[]>("/outcomes/"),
  get: (signalId: string) => request<Outcome>(`/outcomes/${signalId}`),
  create: (signalId: string, body: {
    result: string;
    exit_price?: number;
    pnl_pct?: number;
    notes?: string;
    feedback?: string;
  }) =>
    request<Outcome>(`/outcomes/${signalId}`, { method: "POST", body: JSON.stringify(body) }),
};

// ─── Analytics ────────────────────────────────────────────────────────────────

export const analyticsApi = {
  summary: () => request<AnalyticsSummary>("/analytics/summary"),
  patterns: () => request<PatternStats[]>("/analytics/patterns"),
};

// ─── Scanner ──────────────────────────────────────────────────────────────────

export const scannerApi = {
  run: (patternId?: string, symbols?: string[], scope?: string) =>
    request<{ signals_created: number; symbols_scanned: number; duration_seconds: number }>(
      "/scanner/run",
      {
        method: "POST",
        body: JSON.stringify({
          pattern_id: patternId,
          symbols: symbols?.length ? symbols : undefined,
          scope: scope || "nifty50",
        }),
      }
    ),
};

// ─── Data ─────────────────────────────────────────────────────────────────────

export interface StockPrice {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface StockFundamentals {
  pe_ratio?: number | null;
  pb_ratio?: number | null;
  debt_to_equity?: number | null;
  roe?: number | null;
  dividend_yield?: number | null;
  beta?: number | null;
  market_cap?: number | null;
  enterprise_value?: number | null;
  forward_pe?: number | null;
  trailing_pe?: number | null;
  eps?: number | null;
  revenue_per_share?: number | null;
}

export interface StockDataResponse {
  symbol: string;
  exchange: string;
  timeframe: string;
  prices: StockPrice[];
  fundamentals: StockFundamentals | null;
}

export interface IndexDataResponse {
  index: string;
  timeframe: string;
  prices: StockPrice[];
}

export interface PCRData {
  symbol: string;
  pcr: number | null;
  total_ce_oi: number;
  total_pe_oi: number;
}

export interface OptionContract {
  "strike": number;
  "CE_LastPrice"?: number | null;
  "PE_LastPrice"?: number | null;
  "CE_OI"?: number | null;
  "PE_OI"?: number | null;
  [key: string]: unknown;
}

export interface OptionChainResponse {
  symbol: string;
  contracts: OptionContract[];
}

export const dataApi = {
  getStock: (symbol: string, options?: { timeframe?: string; days?: number; exchange?: string; includeFundamentals?: boolean }) => {
    const params = new URLSearchParams();
    if (options?.timeframe) params.set("timeframe", options.timeframe);
    if (options?.days) params.set("days", String(options.days));
    if (options?.exchange) params.set("exchange", options.exchange);
    if (options?.includeFundamentals !== undefined) params.set("include_fundamentals", String(options.includeFundamentals));
    return request<StockDataResponse>(`/data/stock/${encodeURIComponent(symbol)}?${params}`);
  },
  getIndex: (indexName: string, options?: { timeframe?: string; days?: number }) => {
    const params = new URLSearchParams();
    if (options?.timeframe) params.set("timeframe", options.timeframe);
    if (options?.days) params.set("days", String(options.days));
    return request<IndexDataResponse>(`/data/index/${encodeURIComponent(indexName)}?${params}`);
  },
  getPCR: (symbol?: string) => {
    const params = new URLSearchParams();
    if (symbol) params.set("symbol", symbol);
    return request<PCRData>(`/data/fno/pcr?${params}`);
  },
  getQuote: (symbol: string) => request<any>(`/data/fno/quote?symbol=${encodeURIComponent(symbol)}`),
  getOptionChain: (symbol: string, expiry?: string) => {
    const params = new URLSearchParams();
    if (expiry) params.set("expiry", expiry);
    return request<OptionChainResponse>(`/data/fno/option-chain?symbol=${encodeURIComponent(symbol)}&${params}`);
  },
};

// ─── Compare ───────────────────────────────────────────────────────────────────

export interface ComparisonItem {
  symbol: string;
  fundamentals: StockFundamentals;
  technicals: {
    sma20?: number | null;
    sma50?: number | null;
    rsi_14?: number | null;
    macd: { macd: number | null; signal: number | null; histogram: number | null };
    above_sma20: boolean | null;
    above_sma50: boolean | null;
    price: number | null;
    error?: string;
  };
}

export interface ComparisonResponse {
  comparisons: ComparisonItem[];
}

export interface CorrelationResponse {
  symbols: string[];
  correlation: Record<string, Record<string, number | null>>;
  method: string;
  period_days: number;
}

export const compareApi = {
  stocks: (symbols: string, exchange = "NSE") => request<ComparisonResponse>(`/compare/stocks?symbols=${encodeURIComponent(symbols)}&exchange=${exchange}`),
  correlation: (symbols: string, days = 90, exchange = "NSE") => {
    const params = new URLSearchParams({ days: String(days), exchange });
    return request<CorrelationResponse>(`/compare/correlation?symbols=${encodeURIComponent(symbols)}&${params}`);
  },
};

// ─── F&O Analysis ─────────────────────────────────────────────────────────────

export interface OIBuildupResponse {
  symbol: string;
  expiry: string;
  total_ce_oi: number;
  total_pe_oi: number;
  pcr: number | null;
  top_call_strikes: OptionContract[];
  top_put_strikes: OptionContract[];
}

export interface NiftyOiHistoryResponse {
  symbol: string;
  data: Array<{
    date: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    oi: number;
    oi_change: number;
  }>;
}

export const fnoApi = {
  pcr: (symbol?: string) => request<PCRData>(`/fno/pcr?${symbol ? `symbol=${encodeURIComponent(symbol)}` : ""}`),
  oiBuildup: (symbol: string, days = 5) => request<OIBuildupResponse>(`/fno/oi-buildup?symbol=${encodeURIComponent(symbol)}&days=${days}`),
  niftyOiHistory: (days = 30) => request<NiftyOiHistoryResponse>(`/fno/nifty-oi-history?days=${days}`),
};

// ─── Analytics extensions ────────────────────────────────────────────────────

export interface PatternPerformanceItem {
  pattern_id: string;
  pattern_name: string;
  signals: number;
  wins: number;
  losses: number;
  win_rate: number;
  avg_return_5d: number | null;
  avg_return_10d: number | null;
  avg_return_20d: number | null;
  avg_return_63d: number | null;
  avg_max_gain_20d: number | null;
  avg_max_loss_20d: number | null;
}

export interface SectorHeatmapItem {
  sector: string;
  avg_return: number;
  symbol_count: number;
  best_performer: string | null;
  best_return: number | null;
  worst_performer: string | null;
  worst_return: number | null;
}

export const analyticsApiExtended = {
  patternPerformance: (params?: {
    pattern_id?: string;
    timeframe?: string;
    sector?: string;
    min_signals?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.pattern_id) qs.set("pattern_id", params.pattern_id);
    if (params?.timeframe) qs.set("timeframe", params.timeframe);
    if (params?.sector) qs.set("sector", params.sector);
    if (params?.min_signals) qs.set("min_signals", String(params.min_signals));
    return request<PatternPerformanceItem[]>(`/analytics/pattern-performance?${qs}`);
  },
  sectors: (timeframe = "1d", days = 30) => request<SectorHeatmapItem[]>(`/analytics/sectors?timeframe=${timeframe}&days=${days}`),
  outcomes: (params?: { pattern_id?: string; symbol?: string; result?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.pattern_id) qs.set("pattern_id", params.pattern_id);
    if (params?.symbol) qs.set("symbol", params.symbol);
    if (params?.result) qs.set("result", params.result);
    if (params?.limit) qs.set("limit", String(params.limit));
    return request<any[]>(`/analytics/outcomes?${qs}`);
  },
};

// ============================================================================
// Custom Screener
// ============================================================================

export interface ScreenerCondition {
  field: string;
  operator: string;
  value?: number | string | boolean | null;
  min?: number;
  max?: number;
}

export interface ScreenerRules {
  logic: "AND" | "OR";
  conditions: ScreenerCondition[];
}

export interface Screener {
  id: string;
  name: string;
  description: string | null;
  asset_class: "equity" | "mf";
  scope: "nifty50" | "nifty500" | "custom";
  custom_symbols?: string[] | null;
  rules: ScreenerRules;
  created_at: string;
  updated_at: string;
}

export interface ScreenerResultItem {
  id: string;
  symbol: string;
  date: string;
  passed: boolean;
  score: number | null;
  metrics: Record<string, unknown>;
}

export interface ScreenerRun {
  id: string;
  triggered_at: string;
  symbols_total: number;
  symbols_passed: number;
  duration_sec: number;
  status: "queued" | "running" | "completed" | "failed";
}

export interface ScreenerRunDetail extends ScreenerRun {
  filters?: Record<string, unknown> | null;
  results?: ScreenerResultItem[];
}

export const screenerApi = {
  // CRUD
  list: (assetClass?: "equity" | "mf") => {
    const params = new URLSearchParams();
    if (assetClass) params.set("asset_class", assetClass);
    return request<Screener[]>(`/screener/?${params}`);
  },
  get: (id: string) => request<Screener>(`/screener/${id}`),
  create: (body: {
    name: string;
    description?: string;
    asset_class: string;
    scope: "nifty50" | "nifty500" | "custom";
    custom_symbols?: string[];
    rules: ScreenerRules;
  }) => request<Screener>("/screener/", { method: "POST", body: JSON.stringify(body) }),
  update: (id: string, body: Partial<{ name: string; description: string; rules: ScreenerRules; scope: string; custom_symbols: string[] }>) =>
    request<Screener>(`/screener/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  delete: (id: string) => request<void>(`/screener/${id}`, { method: "DELETE" }),

  // Execution
  run: (body: { screener_id: string; timeframe?: string; use_cache?: boolean }) =>
    request<{ run_id: string; status: string }>("/screener/run", { method: "POST", body: JSON.stringify(body) }),
  getRunStatus: (runId: string) => request<ScreenerRun>(`/screener/run/${runId}/status`),
  getRunResults: (runId: string) => request<ScreenerResultItem[]>(`/screener/run/${runId}/results`),

  // Results
  getResults: (id: string, passedOnly?: boolean, limit = 100) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (passedOnly) params.set("passed_only", "true");
    return request<ScreenerResultItem[]>(`/screener/${id}/results?${params}`);
  },
  getRuns: (id: string, limit = 20) =>
    request<ScreenerRun[]>(`/screener/${id}/runs?limit=${limit}`),
};

// ============================================================================

export interface MFScheme {
  scheme_code: number;
  scheme_name: string | null;
  isin_growth?: string | null;
  isin_reinvest?: string | null;
  family_id?: number | null;
  family_name?: string | null;
  amc_name?: string | null;
  amc_slug?: string | null;
  category?: string | null;
  plan_type?: string | null;
  option_type?: string | null;
  risk_label?: string | null;
  expense_ratio?: number | null;
  aum?: number | null;
  min_sip?: number | null;
  min_lumpsum?: number | null;
  exit_load?: string | null;
  benchmark?: string | null;
  launch_date?: string | null;
  latest_nav?: number | null;
  latest_nav_date?: string | null;
  is_active?: boolean;
  monitored?: boolean;
  notes?: string | null;
  valueresearch_url?: string | null;
  morningstar_url?: string | null;
  valueresearch_link_status?: string | null;
  morningstar_link_status?: string | null;
  morningstar_sec_id?: string | null;
  returns_json?: Record<string, unknown> | null;
  ratios_json?: Record<string, unknown> | null;
  updated_at?: string | null;
}

export interface MFNavPoint {
  nav_date: string;
  nav: number;
}

export interface MFSignal {
  id: string;
  scheme_code: number;
  scheme_name?: string | null;
  family_id?: number | null;
  signal_type: string;
  nav_date?: string | null;
  triggered_at: string;
  base_score?: number | null;
  confidence_score: number;
  status: string;
  llm_analysis?: string | null;
  context_json?: Record<string, unknown> | null;
  reviewed_at?: string | null;
  review_action?: string | null;
  review_notes?: string | null;
}

export interface MFIndicatorRecord {
  time: string;
  ema_20?: number | null;
  ema_50?: number | null;
  ema_200?: number | null;
  sma_20?: number | null;
  bb_upper?: number | null;
  bb_mid?: number | null;
  bb_lower?: number | null;
  bb_width?: number | null;
  rsi?: number | null;
  macd?: number | null;
  macd_signal?: number | null;
  macd_hist?: number | null;
  atr?: number | null;
  stoch_k?: number | null;
  stoch_d?: number | null;
  adx?: number | null;
  adx_di_pos?: number | null;
  adx_di_neg?: number | null;
  obv?: number | null;
}

export interface MFPatternsResponse {
  chart_patterns: any[];
  candlestick_patterns: any[];
  talib_candlestick_patterns: any[];
}

export interface MFIngestionStatus {
  latest_nav_run?: any | null;
  latest_holdings_run?: any | null;
  monitored_schemes: number;
  schemes_total: number;
  nav_rows_total: number;
  signals_pending: number;
  providers?: MFProviderState[] | null;
}

export interface MFProviderState {
  provider: string;
  paused_until?: string | null;
  consecutive_failures: number;
  last_error?: string | null;
  updated_at?: string | null;
}

export interface MFRulebook {
  id: string;
  name: string;
  status: string;
  current_version: number;
  created_at: string;
  updated_at: string;
}

export interface MFRulebookVersion {
  id: string;
  rulebook_id: string;
  version: number;
  rulebook_json: Record<string, unknown>;
  change_summary?: string | null;
  created_at: string;
}

export const mfApi = {
  status: () => request<MFIngestionStatus>("/mf/pipeline/status"),
  runNav: () => request<{ ok: boolean; stats: any }>("/mf/pipeline/nav/run", { method: "POST", body: JSON.stringify({}) }),
  runHoldings: () => request<{ ok: boolean; stats: any }>("/mf/pipeline/holdings/run", { method: "POST", body: JSON.stringify({}) }),
  runHoldingsBootstrap: () => request<{ ok: boolean; stats: any }>("/mf/pipeline/holdings/bootstrap", { method: "POST", body: JSON.stringify({}) }),
  runBackfill: () => request<{ ok: boolean; stats: any }>("/mf/pipeline/backfill/run", { method: "POST", body: JSON.stringify({}) }),
  runNavGapfill: () => request<{ ok: boolean; stats: any }>("/mf/pipeline/nav/gapfill", { method: "POST", body: JSON.stringify({}) }),
  checkLinks: () => request<{ ok: boolean; stats: any }>("/mf/pipeline/links/check", { method: "POST", body: JSON.stringify({}) }),
  navQuality: (params?: { monitored_only?: boolean; amc_query?: string; gap_days?: number; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.monitored_only != null) qs.set("monitored_only", String(params.monitored_only));
    if (params?.amc_query) qs.set("amc_query", params.amc_query);
    if (params?.gap_days != null) qs.set("gap_days", String(params.gap_days));
    if (params?.limit != null) qs.set("limit", String(params.limit));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return request<any>(`/mf/nav/quality${suffix}`);
  },
  providers: () => request<MFProviderState[]>("/mf/providers"),
  pauseProvider: (provider: string, body: { minutes?: number; reason?: string }) =>
    request<MFProviderState>(`/mf/providers/${encodeURIComponent(provider)}/pause`, { method: "POST", body: JSON.stringify(body) }),
  resumeProvider: (provider: string) =>
    request<MFProviderState>(`/mf/providers/${encodeURIComponent(provider)}/resume`, { method: "POST", body: JSON.stringify({}) }),
  schemes: (monitoredOnly = false, query?: string) => {
    const params = new URLSearchParams({ monitored_only: String(monitoredOnly), limit: "200", offset: "0" });
    if (query) params.set("query", query);
    return request<MFScheme[]>(`/mf/schemes?${params}`);
  },
  scheme: (schemeCode: number) => request<MFScheme>(`/mf/schemes/${schemeCode}`),
  updateScheme: (schemeCode: number, body: { monitored?: boolean; notes?: string }) =>
    request<MFScheme>(`/mf/schemes/${schemeCode}`, { method: "PATCH", body: JSON.stringify(body) }),
  updateSchemeLinks: (
    schemeCode: number,
    body: {
      valueresearch_url?: string | null;
      morningstar_url?: string | null;
      morningstar_sec_id?: string | null;
    }
  ) => request<MFScheme>(`/mf/schemes/${schemeCode}`, { method: "PATCH", body: JSON.stringify(body) }),
  enableScheme: (schemeCode: number) =>
    request<{ ok: boolean; monitored: boolean; enriched: boolean; metrics: number; signals: number; nav_date?: string }>(
      `/mf/schemes/${schemeCode}/enable`,
      { method: "POST", body: JSON.stringify({}) }
    ),
  nav: (schemeCode: number, limit = 400) =>
    request<MFNavPoint[]>(`/mf/schemes/${schemeCode}/nav?limit=${limit}`),
  metrics: (schemeCode: number) => request<any>(`/mf/schemes/${schemeCode}/metrics`),
  indicators: (schemeCode: number, limit = 420) =>
    request<MFIndicatorRecord[]>(`/mf/schemes/${schemeCode}/indicators?limit=${limit}`),
  patterns: (schemeCode: number, lookback = 180) =>
    request<MFPatternsResponse>(`/mf/schemes/${schemeCode}/patterns?lookback=${lookback}`),
  holdings: (familyId: number) => request<any>(`/mf/families/${familyId}/holdings`),
  refreshHoldings: (familyId: number) =>
    request<{ ok: boolean; fetched?: boolean; month?: string; skipped?: boolean; reason?: string; error?: string }>(
      `/mf/families/${familyId}/holdings/refresh`,
      { method: "POST", body: JSON.stringify({}) }
    ),
  signals: (status = "pending", limit = 200) =>
    request<MFSignal[]>(`/mf/signals?status=${encodeURIComponent(status)}&limit=${limit}`),
  reviewSignal: (id: string, body: { action: string; notes?: string }) =>
    request<{ ok: boolean }>(`/mf/signals/${id}/review`, { method: "POST", body: JSON.stringify(body) }),
  rulebooks: () => request<MFRulebook[]>("/mf/rulebooks"),
  rulebookCurrent: (rulebookId: string) => request<MFRulebookVersion>(`/mf/rulebooks/${rulebookId}/current`),
  rulebookVersions: (rulebookId: string) => request<MFRulebookVersion[]>(`/mf/rulebooks/${rulebookId}/versions`),
  createRulebook: (body: { name: string; status: string; rulebook_json: any; change_summary?: string }) =>
    request<MFRulebook>("/mf/rulebooks", { method: "POST", body: JSON.stringify(body) }),
  updateRulebook: (rulebookId: string, body: { name?: string; status?: string }) =>
    request<MFRulebook>(`/mf/rulebooks/${rulebookId}`, { method: "PUT", body: JSON.stringify(body) }),
  createRulebookVersion: (rulebookId: string, body: { rulebook_json: any; change_summary?: string; set_current?: boolean }) =>
    request<MFRulebookVersion>(`/mf/rulebooks/${rulebookId}/versions`, { method: "POST", body: JSON.stringify(body) }),
  activateRulebookVersion: (rulebookId: string, version: number) =>
    request<MFRulebook>(`/mf/rulebooks/${rulebookId}/activate`, { method: "POST", body: JSON.stringify({ version }) }),
};
