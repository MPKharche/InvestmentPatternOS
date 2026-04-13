/**
 * Typed API client — all backend calls go through here.
 * Base URL is read from NEXT_PUBLIC_API_BASE_URL env var.
 */

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API error ${res.status}: ${err}`);
  }
  return res.json() as Promise<T>;
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
  ret_5d: number | null;
  ret_10d: number | null;
  ret_20d: number | null;
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
  symbols_scanned: number;
  events_found: number;
  success_count: number;
  failure_count: number;
  neutral_count: number;
  success_rate: number | null;
  avg_ret_5d: number | null;
  avg_ret_10d: number | null;
  avg_ret_20d: number | null;
  started_at: string;
  completed_at: string | null;
}

export interface PatternStudyResult {
  id: string;
  analysis: string;
  success_factors: string[] | null;
  failure_factors: string[] | null;
  rulebook_suggestions: Array<{ type: string; condition: string; rationale: string }> | null;
  confidence_improvements: string[] | null;
  created_at: string;
}

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
  learning: (id: string) => request<LearningLog[]>(`/patterns/${id}/learning`),
};

// ─── Studio ───────────────────────────────────────────────────────────────────

export const studioApi = {
  chat: (body: { pattern_id?: string; message: string }) =>
    request<ChatResponse>("/studio/chat", { method: "POST", body: JSON.stringify(body) }),
  history: (patternId: string) =>
    request<ChatMessage[]>(`/studio/${patternId}/history`),
  runBacktest: (patternId: string, params?: { scope?: string; symbols?: string }) =>
    request<{ run_id: string; status: string }>(`/studio/${patternId}/backtest`, {
      method: "POST",
      body: JSON.stringify(params ?? {})
    }),
  getBacktestRuns: (patternId: string) =>
    request<BacktestRun[]>(`/studio/${patternId}/backtest/runs`),
  getEvents: (patternId: string, params?: { symbol?: string; outcome?: string; limit?: number; offset?: number }) => {
    const p = new URLSearchParams();
    if (params?.symbol) p.set("symbol", params.symbol);
    if (params?.outcome) p.set("outcome", params.outcome);
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
      { method: "POST", body: JSON.stringify({ pattern_id: patternId, symbols, scope: scope || "nifty50" }) }
    ),
};
