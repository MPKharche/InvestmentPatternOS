-- ============================================================================
-- Custom Screener: user-defined rule-based screening
-- Supports both equity and mutual fund screening
-- ============================================================================

CREATE TABLE IF NOT EXISTS screener_criteria (
    id              UUID NOT NULL DEFAULT gen_random_uuid(),
    name            VARCHAR(200) NOT NULL,
    description     TEXT,
    asset_class     VARCHAR(30) NOT NULL DEFAULT 'equity',  -- equity|mf
    scope           VARCHAR(30) NOT NULL DEFAULT 'nifty500', -- nifty50|nifty500|custom
    custom_symbols  JSONB,  -- array of strings if scope='custom'
    rules_json      JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_screener_criteria_asset ON screener_criteria(asset_class);
CREATE INDEX IF NOT EXISTS idx_screener_criteria_scope ON screener_criteria(scope);

-- Cached screening results (24h TTL pattern)
CREATE TABLE IF NOT EXISTS screener_results (
    id              UUID NOT NULL DEFAULT gen_random_uuid(),
    screener_id     UUID NOT NULL REFERENCES screener_criteria(id) ON DELETE CASCADE,
    symbol          VARCHAR(20) NOT NULL,
    signal_date     DATE NOT NULL,
    metrics_json    JSONB,
    passed          BOOLEAN NOT NULL DEFAULT FALSE,
    score           FLOAT,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_screener_result ON screener_results(screener_id, symbol, signal_date);
CREATE INDEX IF NOT EXISTS idx_screener_results_lookup ON screener_results(screener_id, passed DESC, signal_date DESC);

-- Execution audit log
CREATE TABLE IF NOT EXISTS screener_runs (
    id              UUID NOT NULL DEFAULT gen_random_uuid(),
    screener_id     UUID NOT NULL REFERENCES screener_criteria(id) ON DELETE CASCADE,
    triggered_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbols_total   INTEGER NOT NULL,
    symbols_passed  INTEGER NOT NULL,
    duration_sec    FLOAT NOT NULL,
    filters_json    JSONB,
    status          VARCHAR(20) NOT NULL DEFAULT 'completed',
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_screener_runs_screener ON screener_runs(screener_id, triggered_at DESC);
