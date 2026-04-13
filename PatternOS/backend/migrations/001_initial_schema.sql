-- PatternOS — Initial Schema
-- Run: psql -U postgres -d patternos -f 001_initial_schema.sql

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ----------------------------------------------------------------
-- Universe: stocks / instruments to scan
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS universe (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol      VARCHAR(20) NOT NULL,
    exchange    VARCHAR(20) NOT NULL DEFAULT 'NSE',
    asset_class VARCHAR(30) NOT NULL DEFAULT 'equity',
    name        VARCHAR(100),
    active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (symbol, exchange)
);

-- ----------------------------------------------------------------
-- Patterns: the rulebooks
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS patterns (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    asset_class VARCHAR(30) DEFAULT 'equity',
    timeframes  TEXT[] DEFAULT ARRAY['1d'],
    status      VARCHAR(20) NOT NULL DEFAULT 'active',  -- active | paused | draft
    current_version INTEGER NOT NULL DEFAULT 1,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------------
-- Pattern versions: full rulebook history
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pattern_versions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pattern_id     UUID NOT NULL REFERENCES patterns(id) ON DELETE CASCADE,
    version        INTEGER NOT NULL,
    rulebook_json  JSONB NOT NULL,
    change_summary TEXT,
    approved_at    TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (pattern_id, version)
);

-- ----------------------------------------------------------------
-- Signals: raw scanner output
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS signals (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pattern_id       UUID NOT NULL REFERENCES patterns(id),
    symbol           VARCHAR(20) NOT NULL,
    exchange         VARCHAR(20) NOT NULL DEFAULT 'NSE',
    timeframe        VARCHAR(10) NOT NULL DEFAULT '1d',
    triggered_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confidence_score NUMERIC(5,2) NOT NULL,  -- 0-100
    base_score       NUMERIC(5,2),
    rule_snapshot    JSONB,
    status           VARCHAR(20) NOT NULL DEFAULT 'pending'  -- pending | reviewed | dismissed
);

-- ----------------------------------------------------------------
-- Signal context: LLM analysis enrichment
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS signal_context (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id     UUID NOT NULL UNIQUE REFERENCES signals(id) ON DELETE CASCADE,
    chart_summary TEXT,
    llm_analysis  TEXT,
    key_levels    JSONB,   -- {support, resistance, entry, sl, target}
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------------
-- Reviews: your action on a signal
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reviews (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id    UUID NOT NULL UNIQUE REFERENCES signals(id) ON DELETE CASCADE,
    action       VARCHAR(20) NOT NULL,  -- executed | watching | skipped | dismissed
    entry_price  NUMERIC(12,4),
    sl_price     NUMERIC(12,4),
    target_price NUMERIC(12,4),
    notes        TEXT,
    reviewed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------------
-- Outcomes: trade result tracking
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS outcomes (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id    UUID NOT NULL UNIQUE REFERENCES signals(id) ON DELETE CASCADE,
    result       VARCHAR(20),  -- hit_target | stopped_out | partial | open | cancelled
    exit_price   NUMERIC(12,4),
    pnl_pct      NUMERIC(8,4),
    notes        TEXT,
    feedback     TEXT,
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------------
-- Learning log: LLM-generated insights per pattern
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS learning_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pattern_id      UUID NOT NULL REFERENCES patterns(id) ON DELETE CASCADE,
    source          VARCHAR(30) NOT NULL,  -- outcome_audit | manual | llm_suggestion
    insight_text    TEXT NOT NULL,
    version_applied INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------------
-- Pattern chat history: conversation for Studio
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pattern_chat (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pattern_id  UUID REFERENCES patterns(id) ON DELETE CASCADE,
    role        VARCHAR(10) NOT NULL,  -- user | assistant
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------------
-- Indexes
-- ----------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_signals_pattern     ON signals(pattern_id);
CREATE INDEX IF NOT EXISTS idx_signals_symbol      ON signals(symbol);
CREATE INDEX IF NOT EXISTS idx_signals_status      ON signals(status);
CREATE INDEX IF NOT EXISTS idx_signals_triggered   ON signals(triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_outcomes_result     ON outcomes(result);
CREATE INDEX IF NOT EXISTS idx_learning_pattern    ON learning_log(pattern_id);
