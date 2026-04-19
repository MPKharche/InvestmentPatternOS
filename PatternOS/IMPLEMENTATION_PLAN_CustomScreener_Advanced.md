# Implementation Plan: Custom Screener & Advanced Tools

**Plan Status:** Awaiting Confirmation | **Effort Estimate:** 10-12 days total

---

## 📋 Overview

These features transform PatternOS from a **pattern detection system** into a full **research & backtesting platform**.

### Feature 1: Custom Screener Builder (P2, 3 days)
**Value:** Let users define their own screening rules (technical + fundamental) and run them on the full Nifty 500 universe.

### Feature 2: Backtest Result Repository (P3, 2 days)
**Value:** Historical record of all backtest runs with comparison, cloning, and performance attribution.

### Feature 3: Portfolio Stress Testing (P3, 3 days)
**Value:** Upload portfolio CSV → test against historical crisis scenarios (2008, 2020, 2022) → get risk metrics.

### Feature 4: Technical Indicator Playground (P3, 2 days)
**Value:** Interactive indicator builder with parameter tweaking and visual signal plotting.

---

## 🎯 Feature 1: Custom Screener Builder (3 days)

### Architecture
```
Frontend: /builder [new page] with form builder UI
Backend:  POST /api/v1/screener/save   (save rule set)
          POST /api/v1/screener/run    (run scan)
          GET  /api/v1/screener/list   (list saved screeners)
          GET  /api/v1/screener/{id}/results (view results)
DB:       screener_criteria (JSON), screener_results (cached)
```

### 1.1 Database Schema

**New Table: `screener_criteria`**
```sql
CREATE TABLE screener_criteria (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(200) NOT NULL,
    description     TEXT,
    asset_class     VARCHAR(30) DEFAULT 'equity',
    scope           VARCHAR(30) DEFAULT 'nifty500',  -- 'nifty50', 'nifty500', 'custom'
    custom_symbols  TEXT[],  -- if scope='custom'
    rules_json      JSONB NOT NULL,  -- { "conditions": [...], "logic": "AND" }
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

**New Table: `screener_results` (cache)**
```sql
CREATE TABLE screener_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    screener_id     UUID NOT NULL REFERENCES screener_criteria(id) ON DELETE CASCADE,
    symbol          VARCHAR(20) NOT NULL,
    signal_date     DATE NOT NULL,
    metrics_json    JSONB,  -- { "pe": 22.5, "rsi": 67, ... }
    passed          BOOLEAN NOT NULL,
    score           FLOAT,  -- 0-100 match score
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(screener_id, symbol, signal_date)
);
CREATE INDEX idx_screener_results_lookup ON screener_results(screener_id, passed DESC, signal_date DESC);
```

**New Table: `screener_runs` (audit log)**
```sql
CREATE TABLE screener_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    screener_id     UUID NOT NULL REFERENCES screener_criteria(id),
    triggered_at    TIMESTAMPTZ DEFAULT NOW(),
    symbols_total   INTEGER NOT NULL,
    symbols_passed  INTEGER NOT NULL,
    duration_sec    FLOAT NOT NULL,
    filters_json    JSONB,  -- runtime params (date range, etc.)
    status          VARCHAR(20) DEFAULT 'completed'
);
```

### 1.2 Backend API Routes (`app/api/routes/screener.py`)

```python
router = APIRouter(prefix="/screener", tags=["screener"])

# CRUD
@router.post("/", response_model=ScreenerOut)          # create
@router.get("/", response_model=list[ScreenerOut])     # list all
@router.get("/{id}", response_model=ScreenerOut)       # get one
@router.patch("/{id}", response_model=ScreenerOut)     # update
@router.delete("/{id}", status_code=204)              # delete

# Execution
@router.post("/run")   # run now, async job, returns run_id
@router.get("/run/{run_id}/status")  # poll status
@router.get("/run/{run_id}/results") # get matching symbols

# Presets (optional)
@router.get("/presets/technical")  # e.g., "RSI oversold", "MACD crossover"
@router.get("/presets/fundamental") # e.g., "Low P/E", "High ROE"
```

**Pydantic Schemas:**
```python
class ScreenerCreate(BaseModel):
    name: str
    description: Optional[str]
    asset_class: str = "equity"
    scope: str = "nifty500"  # "nifty50" | "nifty500" | "custom"
    custom_symbols: Optional[list[str]] = None
    rules: dict               # { "logic": "AND", "conditions": [...] }
    # condition: { "field": "rsi", "operator": "<", "value": 30, "timeframe": "1d" }

class ScreenerOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    scope: str
    rules: dict
    created_at: datetime
    updated_at: datetime

class ScreenerRunRequest(BaseModel):
    screener_id: str
    timeframe: str = "1d"
    use_cache: bool = True  # skip if < 24h old

class ScreenerRunResult(BaseModel):
    run_id: str
    status: str  # "queued" | "running" | "completed"
    symbols_total: int
    symbols_passed: int
    results: list[dict]  # symbol, metrics, passed, score
    duration_seconds: float
```

### 1.3 Rule Engine

**Condition Format:**
```json
{
  "logic": "AND",  // OR also allowed
  "conditions": [
    { "field": "rsi", "operator": "<", "value": 30 },
    { "field": "pe", "operator": "between", "min": 10, "max": 25 },
    { "field": "sma20_cross_above_sma50", "operator": "==", "value": true },
    { "field": "volume_ratio", "operator": ">", "value": 1.5 }
  ]
}
```

**Supported Fields:**
- Technical: `rsi`, `macd`, `macd_hist`, `sma_20`, `sma_50`, `sma_200`, `close_vs_sma`, `bb_upper`, `bb_lower`, `atr`
- Fundamental: `pe`, `pb`, `roe`, `debt_to_equity`, `dividend_yield`, `beta`, `market_cap`
- Pattern flags: `ema_crossover_bullish`, `macd_divergence_bullish`, etc.

**Implementation approach:**
- Reuse existing `app.scanner.evaluator._evaluate_condition()` logic (extract from `evaluate_pattern`)
- For multi-indicator conditions (like "SMA20 > SMA50"), compute both indicators first
- Cache results per symbol+timeframe for 24h (like ScreeningCache)

### 1.4 Frontend (`/builder` page)

**UI Components:**
1. **Screener List** — table of saved screeners with "Run", "Edit", "Delete"
2. **Screener Builder** — drag-and-drop rule builder:
   - Add condition cards (dropdown field, operator input, value input)
   - Group with AND/OR logic
   - Preview rule syntax (JSON)
   - Select scope: Nifty 50 / Nifty 500 / Custom list (text input)
3. **Run Modal** — pick timeframe (1d/1w), show progress, "View Results" button
4. **Results Table** — sortable columns: Symbol, Price, RSI, P/E, Pass/Fail badge, Score bar

**Files:**
- `frontend/src/app/screener/page.tsx` (main listing)
- `frontend/src/app/screener/builder/page.tsx` (create/edit)
- `frontend/src/app/screener/{id}/results/page.tsx` (view results)
- `frontend/src/lib/api.ts` — add `screenerApi` object

**UX flow:**
```
/screener → [list] → [Run] → /screener/{id}/results
          → [Create] → /screener/builder → save → back to list
```

### 1.5 Scheduled Scans (Optional)

- Daily cron job: run all "monitored" screeners at 7:15 AM IST
- Store results in `screener_results`; push Telegram alerts if configured

---

## 🎯 Feature 2: Backtest Result Repository (2 days)

### Problem
Currently backtest results are ephemeral — lost after server restart, no comparison across runs.

### Solution
Persist every `BacktestRun` + `PatternEvent` with ability to compare versions.

### 2.1 DB Changes (already exists, just extend)

**Existing tables:** `backtest_runs`, `pattern_events` (already have `backtest_run_id` foreign key)

**Add to `backtest_runs`:**
- `params_json` — store full scan parameters (symbols, scope, start/end dates, pattern_version)
- `notes` — user annotation
- `tags` — for grouping (e.g., "production", "experiment", "macd-tuning")

**Add index:**
```sql
CREATE INDEX idx_backtest_runs_pattern ON backtest_runs(pattern_id, triggered_at DESC);
CREATE INDEX idx_pattern_events_run ON pattern_events(backtest_run_id);
```

### 2.2 API Routes (extend existing `studio.py`)

```python
@router.get("/studio/{pattern_id}/backtest/runs")   # already exists — extend
@router.get("/studio/{pattern_id}/backtest/runs/{run_id}")  # detail with stats
@router.post("/studio/{pattern_id}/backtest/compare")       # compare 2+ runs
@router.patch("/studio/backtest/runs/{run_id}")             # add notes/tags
@router.post("/studio/backtest/runs/{run_id}/clone")        # clone with modifications
```

**Compare response:**
```json
{
  "runs": [
    { "run_id": "...", "version": 1, "success_rate": 62.3, "avg_ret_20d": 2.1, ... },
    { "run_id": "...", "version": 2, "success_rate": 68.1, "avg_ret_20d": 2.4, ... }
  ],
  "comparison": {
    "success_rate_delta_pct": +5.8,
    "event_count_delta": +124,
    "improved_metrics": ["avg_ret_20d", "max_gain_20d"],
    "degraded_metrics": ["max_loss_20d"]
  }
}
```

### 2.3 Frontend

**Pages:**
- `/studio/{patternId}/runs` — table of historical runs with chart trend overlay
- `/studio/{patternId}/runs/{runId}` — detailed metrics + event list + download CSV
- Compare mode: multi-select runs → side-by-side comparison matrix

---

## 🎯 Feature 3: Portfolio Stress Testing (3 days)

### Problem
"I hold RELIANCE + TCS + HDFC. How would my portfolio have done in 2020 crash?"

### Solution
Upload CSV → map to symbols → simulate historical drawdowns.

### 3.1 DB Schema

**New Table: `portfolio_snapshots`**
```sql
CREATE TABLE portfolio_snapshots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         VARCHAR(100),           -- optional multi-user
    name            VARCHAR(200) NOT NULL,  -- "My Tech Portfolio"
    positions_json  JSONB NOT NULL,         -- [{"symbol": "RELIANCE", "qty": 100, "avg_price": 2500}, ...]
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

**New Table: `stress_test_runs`**
```sql
CREATE TABLE stress_test_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id        UUID REFERENCES portfolio_snapshots(id),
    scenario            VARCHAR(50) NOT NULL,  -- "2008_crash", "2020_covid", "2022_inflation", "custom"
    start_date          DATE NOT NULL,
    end_date            DATE NOT NULL,
    initial_value       NUMERIC NOT NULL,
    final_value         NUMERIC,
    max_drawdown_pct    FLOAT,
    var_95              FLOAT,   -- Value at Risk
    beta_weighted       FLOAT,
    results_json        JSONB,   -- per-symbol P&L
    triggered_at        TIMESTAMPTZ DEFAULT NOW(),
    completed_at        TIMESTAMPTZ
);
```

### 3.2 Predefined Scenarios

```python
SCENARIOS = {
    "2008_crisis":      {"start": "2008-09-01", "end": "2009-03-01", "description": "Global Financial Crisis"},
    "2020_covid":       {"start": "2020-02-15", "end": "2020-04-30", "description": "COVID-19 Market Crash"},
    "2022_inflation":   {"start": "2022-01-01", "end": "2022-06-30", "description": "Rate Hike Cycle"},
    "2023_bank_crisis": {"start": "2023-03-01", "end": "2023-05-01", "description": "US Regional Bank Crisis"},
    "nifty_2022":       {"start": "2022-01-01", "end": "2022-12-31", "description": "Nifty -5% in 2022"},
}
```

### 3.3 API Routes

```python
router = APIRouter(prefix="/stress-test", tags=["stress-test"])

@router.post("/portfolio")               # create portfolio from JSON/CSV upload
@router.get("/portfolio/{id}")           # get positions
@router.put("/portfolio/{id}")           # update positions
@router.delete("/portfolio/{id}")        # delete

@router.post("/run")                     # run stress test (async job)
@router.get("/run/{run_id}")             # get results
@router.get("/portfolio/{id}/runs")      # history of runs

@router.get("/scenarios")                # list predefined scenarios
```

### 3.4 Calculation Logic

```python
def run_stress_test(positions: list[Position], scenario: Scenario) -> StressResult:
    """
    For each symbol:
      1. Get price at scenario start (from stock_prices cache or yfinance)
      2. Get price at scenario end
      3. Compute % return
      4. Weight by position value → portfolio return

    Metrics:
      - final_value = Σ(qty * end_price)
      - max_drawdown = min(portfolio_value during period) / initial - 1
      - var_95 = historical VaR (5th percentile of daily returns)
      - beta_weighted = Σ(position_beta * weight)
    """
    pass
```

### 3.5 Frontend

**Pages:**
- `/stress-test/portfolios` — list + upload CSV
- `/stress-test/portfolios/{id}` — positions table + "Run Test" button
- `/stress-test/run/{id}` — scenario selector, results dashboard:
  - Portfolio value chart (start → end)
  - Max drawdown indicator
  - Top 5 losers/gainers
  - VaR gauge

**CSV format:**
```csv
symbol,qty,avg_price
RELIANCE,100,2500
TCS,50,3500
HDFC,200,1600
```

---

## 🎯 Feature 4: Technical Indicator Playground (2 days)

### Problem
"Show me RSI(14) vs RSI(21) for RELIANCE with MACD(12,26,9) overlay."

### Solution
Interactive chart with selectable indicators, parameter tuning, and signal markers.

### 4.1 API Extension (extend `/data/stock/{symbol}`)

```python
# Existing: /data/stock/{symbol}?timeframe=1d&days=120
# Add query params:
@router.get("/stock/{symbol}/indicators")
def get_stock_indicators(
    symbol: str,
    timeframe: str = "1d",
    days: int = 120,
    indicators: str = Query("all", description="comma-separated: sma,ema,rsi,macd,bb,atr"),
    rsi_period: int = Query(14),
    sma_periods: str = Query("20,50,200", description="comma-separated"),
    macd_fast: int = Query(12),
    macd_slow: int = Query(26),
    macd_signal: int = Query(9),
):
    """
    Return OHLCV + pre-computed technical indicators.
    Response: { prices: [...], indicators: { "rsi": [...], "sma_20": [...], ... } }
    """
```

**Response format:**
```json
{
  "symbol": "RELIANCE.NS",
  "timeframe": "1d",
  "prices": [
    {"date": "2026-04-01", "open": 1300, "high": 1310, "low": 1290, "close": 1305, "volume": 1000000}
  ],
  "indicators": {
    "rsi_14": [45.2, 52.1, ...],
    "sma_20": [1298.5, 1301.2, ...],
    "macd": [12.5, 13.2, ...],
    "macd_signal": [11.8, 12.1, ...],
    "macd_hist": [0.7, 1.1, ...],
    "bb_upper": [1320, 1325, ...],
    "bb_lower": [1280, 1275, ...]
  },
  "signals": [
    {"date": "2026-04-10", "type": "macd_crossover_bullish", "price": 1350}
  ]
}
```

### 4.2 Frontend

**Page:** `/indicators` or `/chart/advanced`

**Components:**
1. **Symbol selector** + timeframe (1d/1h/1w)
2. **Price chart** (candlestick) — use existing `mplfinance` or lightweight-charts
3. **Indicator toggles** — checkboxes: SMA(20,50,200), EMA(20), RSI(14/21), MACD, Bollinger Bands, ATR
4. **Parameter inputs** — number inputs for periods (when indicator selected)
5. **Signal markers** — vertical lines at divergence/breakout events
6. **Export** button — download CSV of indicators

**Tech:** Reuse `app/charts/render.py` for generating plots, or use client-side lightweight-charts for interactivity.

---

## 📊 Common Components

### Shared Frontend State
- `useTechnicalIndicators(symbol, timeframe, config)` hook
- `useComparison(symbols)` for correlation view
- `useStressTest(portfolioId)` for scenario runs

### Shared Backend Utilities
- `app/scanner/indicators.py` — already has `compute_indicators()`, extend for ATR, BB width
- `app/scanner/criteria_checks.py` — already has divergence detection, expose as public API

---

## 🔄 Dependencies & Order

**Phase A (Independent):**
1. Custom Screener Builder — no dependencies on other new features
2. Backtest Repository — depends on existing backtest system, just add persistence/UI

**Phase B (Depends on A):**
3. Stress Testing — needs portfolio upload + price data from yfinance cache
4. Indicator Playground — can build in parallel (uses same data layer)

**Recommended order:**
```
Week 1: Custom Screener Builder (backend + frontend)
Week 2: Backtest Repository (UI + comparison charts)
Week 3: Stress Testing (CSV parser + scenario engine + frontend)
Week 4: Indicator Playground (interactive chart tuning)
```

---

## 📁 File Structure Changes

```
backend/
├── app/
│   ├── api/
│   │   └── routes/
│   │       ├── screener.py           [NEW]
│   │       └── stress_test.py         [NEW]
│   ├── db/
│   │   ├── models.py                  [ADD: ScreenerCriteria, ScreenerResult, ScreenerRun, PortfolioSnapshot, StressTestRun]
│   │   └── migrations/
│   │       └── 013_screener.sql       [NEW]
│   │       └── 014_stress_test.sql    [NEW]
│   ├── screener/
│   │   ├── engine.py                  [NEW: rule evaluator]
│   │   ├── criteria.py                [NEW: condition check functions]
│   │   └── presets.py                 [NEW: built-in templates]
│   ├── stress_test/
│   │   ├── engine.py                  [NEW: scenario runner]
│   │   ├── scenarios.py               [NEW: crisis date ranges]
│   │   └── portfolio_parser.py        [NEW: CSV → positions]
│   └── indicators/
│       └── playground.py              [NEW: param-tunable indicator compute]
frontend/
├── src/
│   ├── app/
│   │   ├── screener/
│   │   │   ├── page.tsx               [NEW: list]
│   │   │   ├── builder/page.tsx       [NEW: create/edit]
│   │   │   └── [id]/results/page.tsx  [NEW]
│   │   ├── studio/
│   │   │   └── [patternId]/runs/page.tsx  [NEW]
│   │   ├── stress-test/
│   │   │   ├── portfolios/page.tsx    [NEW]
│   │   │   ├── portfolio/[id]/page.tsx [NEW]
│   │   │   └── run/[id]/page.tsx      [NEW]
│   │   └── indicators/page.tsx        [NEW]
│   └── lib/
│       └── api.ts                     [EXTEND: screenerApi, stressTestApi, indicatorsApi]
```

---

## 🧪 Testing Plan

**Unit tests** — `backend/tests/`:
- `test_screener_engine.py`: rule evaluation against known outcomes
- `test_stress_scenarios.py`: known crisis period returns for NIFTY
- `test_indicator_params.py`: test varying RSI/SMA periods

**Manual smoke test:**
1. Create screener: `RSI < 30 AND PE < 20` → run on Nifty 50
2. Run backtest → view `/studio/.../runs` → confirm results persisted
3. Upload portfolio CSV → run 2020 scenario → check max drawdown matches known NIFTY crash (~40%)
4. Toggle RSI(14) vs RSI(21) on chart → verify overlay

---

## ⚠️ Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Rule evaluation slow on 500-stock universe | High | Cache results 24h, incremental daily runs, parallel processing |
| nsepy SSL failures continue | Medium | Fall back to yfinance price data (already have) |
| Complex rule syntax confuses users | High | Provide preset templates + rule builder UI (not JSON editor) |
| Frontend chart performance with 5000+ bars | Medium | Use WebGL-based chart (lightweight-charts) + data decimation |
| Stress test requires 15+ years of price history | Medium | Already cached in `stock_prices`; pre-seed Nifty 500 history |

---

## ✨ Success Criteria

**Custom Screener:**
- ✅ User can create "RSI oversold" screener in < 3 minutes
- ✅ Running on Nifty 500 returns results within 30 seconds (cached: < 2s)
- ✅ Saved screeners persist across server restarts

**Backtest Repository:**
- ✅ 10 backtest runs load in < 1 second
- ✅ Comparison view shows delta % for each metric

**Stress Testing:**
- ✅ CSV upload (100 symbols) → scenario run completes in < 20 seconds
- ✅ Results match known index drawdowns within ±2%

**Indicator Playground:**
- ✅ Switching indicators on/off is instant (< 200ms)
- ✅ Parameter changes trigger recompute in < 1s

---

## 📋 Implementation Checklist

**Custom Screener Builder:**
- [ ] DB models: `ScreenerCriteria`, `ScreenerResult`, `ScreenerRun`
- [ ] Migration: `013_screener.sql`
- [ ] Rule engine: `app/scanner/engine.py` extract → `app/screener/engine.py`
- [ ] API routes: `screener.py` (CRUD + run)
- [ ] Frontend: builder UI with condition cards
- [ ] Tests: 10 sample screeners (RSI, MACD, PE, volume)

**Backtest Repository:**
- [ ] Extend `backtest_runs` table (add `params_json`, `notes`, `tags`)
- [ ] API: GET `/studio/{pid}/runs/{run_id}` detail + compare endpoint
- [ ] Frontend: runs table + comparison matrix
- [ ] Tests: create run → retrieve → compare

**Stress Testing:**
- [ ] DB: `portfolio_snapshots`, `stress_test_runs`
- [ ] CSV parser: handle missing symbols, case-insensitive
- [ ] Scenario engine: fetch cached prices from `stock_prices`, compute metrics
- [ ] Frontend: portfolio manager + scenario selector + results dashboard
- [ ] Tests: known 2020 drawdown on NIFTY ETF

**Indicator Playground:**
- [ ] API: `/data/stock/{symbol}/indicators` with flexible params
- [ ] Frontend: multi-pane chart (price + RSI + MACD) with parameter controls
- [ ] Tests: indicator values match known values from TradingView

---

## PRD Summary

| Feature | Effort | Value | Complexity |
|---------|--------|-------|------------|
| Custom Screener | 3 days | High | Medium (rule engine + UI) |
| Backtest Repo | 2 days | Medium | Low (persistence + UI) |
| Stress Testing | 3 days | High | Medium (CSV + scenario math) |
| Indicator Playground | 2 days | Medium | Low (data fetch + chart) |
| **Total** | **10 days** | **Very High** | **Medium** |

---

## ❓ Questions Before Implementation

1. **Screener scope**: Should we include MF schemes in screeners or equity-only initially?
2. **Rule depth**: Minimum/maximum number of conditions per screener? (suggest 1-10)
3. **Stress test scenarios**: Any specific crises beyond the 4 listed? (e.g., 2016 demonetisation, 2024 elections)
4. **Indicator Playground**: Should we support multiple timeframes on same chart (e.g., weekly RSI on daily chart)?
5. **Backtest comparison metrics**: Which metrics matter most? (win rate, avg return, Sharpe, max drawdown)

---

## 🚀 Ready to Start

Please confirm:
1. ✅ Which feature should we implement **first**? (Recommend: **Custom Screener** — highest value, independent)
2. ✅ Any scope changes or constraints?
3. ✅ Predefined scenarios for stress test (add/remove any)?

Once confirmed, I'll begin with **Custom Screener** (Day 1: DB + API routes; Day 2: Rule engine; Day 3: Frontend builder).
