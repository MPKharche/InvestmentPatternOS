-- Stress Testing Feature: portfolio snapshots + stress test runs
-- Migration: 016_stress_test_tables.sql

-- Portfolio snapshots (user uploaded positions)
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         VARCHAR(100),                  -- optional multi-user support
    name            VARCHAR(200) NOT NULL,         -- e.g. "My Tech Portfolio"
    positions_json  JSONB NOT NULL,                -- [{"symbol": "RELIANCE", "qty": 100, "avg_price": 2500}, ...]
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_user ON portfolio_snapshots(user_id);

-- Stress test runs
CREATE TABLE IF NOT EXISTS stress_test_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id        UUID REFERENCES portfolio_snapshots(id) ON DELETE CASCADE,
    scenario            VARCHAR(50) NOT NULL,        -- "2008_crisis", "2020_covid", "2022_inflation", "custom"
    start_date          DATE NOT NULL,
    end_date            DATE NOT NULL,
    initial_value       NUMERIC NOT NULL,
    final_value         NUMERIC,
    max_drawdown_pct    FLOAT,
    var_95              FLOAT,                       -- Value at Risk (95% confidence)
    beta_weighted       FLOAT,
    results_json        JSONB,                       -- per-symbol P&L breakdown
    triggered_at        TIMESTAMPTZ DEFAULT NOW(),
    completed_at        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_stress_test_portfolio ON stress_test_runs(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_stress_test_scenario ON stress_test_runs(scenario);

COMMENT ON COLUMN portfolio_snapshots.positions_json IS 'Array of position objects: {symbol, qty, avg_price}';
COMMENT ON COLUMN stress_test_runs.scenario IS 'Predefined crisis or custom date range scenario';
COMMENT ON COLUMN stress_test_runs.results_json IS 'Breakdown per symbol: {symbol: {qty, start_price, end_price, pnl, return_pct}}';
