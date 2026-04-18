-- Mutual Funds module schema (NAV warehouse + holdings + rulebooks + signals)
-- Idempotent: safe to run multiple times.

-- ----------------------------------------------------------------
-- Schemes master
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mf_schemes (
    scheme_code     INTEGER PRIMARY KEY,
    isin_growth     VARCHAR(20),
    isin_reinvest   VARCHAR(20),
    scheme_name     TEXT,

    -- mfdata.in enrichment
    family_id       INTEGER,
    family_name     TEXT,
    amc_name        TEXT,
    amc_slug        TEXT,
    category        TEXT,
    plan_type       VARCHAR(20),
    option_type     VARCHAR(30),
    risk_label      TEXT,
    expense_ratio   NUMERIC(8,4),
    aum             NUMERIC(18,2),
    min_sip         NUMERIC(12,2),
    min_lumpsum     NUMERIC(12,2),
    exit_load       TEXT,
    benchmark       TEXT,
    launch_date     DATE,

    latest_nav      NUMERIC(18,6),
    latest_nav_date DATE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,

    monitored       BOOLEAN NOT NULL DEFAULT FALSE,
    notes           TEXT,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mf_schemes_family_id ON mf_schemes(family_id);
CREATE INDEX IF NOT EXISTS idx_mf_schemes_monitored ON mf_schemes(monitored);

-- ----------------------------------------------------------------
-- NAV warehouse (potentially very large)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mf_nav_daily (
    scheme_code INTEGER NOT NULL REFERENCES mf_schemes(scheme_code) ON DELETE CASCADE,
    nav_date    DATE NOT NULL,
    nav         NUMERIC(18,6) NOT NULL,
    source      VARCHAR(20) NOT NULL DEFAULT 'amfi', -- seed_parquet|amfi
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (scheme_code, nav_date)
);

CREATE INDEX IF NOT EXISTS idx_mf_nav_daily_nav_date ON mf_nav_daily(nav_date);

-- ----------------------------------------------------------------
-- Derived NAV metrics (monitored schemes only)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mf_nav_metrics_daily (
    scheme_code INTEGER NOT NULL REFERENCES mf_schemes(scheme_code) ON DELETE CASCADE,
    nav_date    DATE NOT NULL,

    day_change      NUMERIC(18,6),
    day_change_pct  NUMERIC(10,4),

    ret_7d    NUMERIC(10,4),
    ret_30d   NUMERIC(10,4),
    ret_90d   NUMERIC(10,4),
    ret_365d  NUMERIC(10,4),

    rolling_52w_high_nav NUMERIC(18,6),
    is_52w_high          BOOLEAN NOT NULL DEFAULT FALSE,

    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (scheme_code, nav_date)
);

-- ----------------------------------------------------------------
-- Holdings snapshots (monthly, per family_id)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mf_family_holdings_snapshot (
    family_id   INTEGER NOT NULL,
    month       DATE NOT NULL, -- first day of month
    total_aum   NUMERIC(18,2),
    equity_pct  NUMERIC(10,4),
    debt_pct    NUMERIC(10,4),
    other_pct   NUMERIC(10,4),
    fetched_at  TIMESTAMPTZ,
    raw_json    JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (family_id, month)
);

CREATE TABLE IF NOT EXISTS mf_holdings (
    family_id   INTEGER NOT NULL,
    month       DATE NOT NULL,
    holding_type VARCHAR(10) NOT NULL, -- equity|debt|other
    name        TEXT NOT NULL,

    weight_pct       NUMERIC(10,4),
    market_value     NUMERIC(18,2),
    quantity         NUMERIC(18,4),
    month_change_qty NUMERIC(18,4),
    month_change_pct NUMERIC(10,4),

    -- debt-specific
    credit_rating TEXT,
    maturity_date DATE,

    -- optional identifiers (if available)
    isin   VARCHAR(20),
    ticker TEXT,
    sector TEXT,

    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (family_id, month, holding_type, name)
);

CREATE TABLE IF NOT EXISTS mf_sector_alloc (
    family_id INTEGER NOT NULL,
    month     DATE NOT NULL,
    sector    TEXT NOT NULL,
    weight_pct NUMERIC(10,4) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (family_id, month, sector)
);

-- ----------------------------------------------------------------
-- Rulebooks + versions (MF-specific)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mf_rulebooks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(160) NOT NULL UNIQUE,
    status          VARCHAR(20) NOT NULL DEFAULT 'active', -- active|paused|draft
    current_version INTEGER NOT NULL DEFAULT 1,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mf_rulebook_versions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rulebook_id    UUID NOT NULL REFERENCES mf_rulebooks(id) ON DELETE CASCADE,
    version        INTEGER NOT NULL,
    rulebook_json  JSONB NOT NULL,
    change_summary TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (rulebook_id, version)
);

-- ----------------------------------------------------------------
-- MF signals + review workflow
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mf_signals (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scheme_code      INTEGER NOT NULL REFERENCES mf_schemes(scheme_code) ON DELETE CASCADE,
    family_id        INTEGER,
    signal_type      VARCHAR(60) NOT NULL,
    nav_date         DATE, -- nullable for holdings-only signals
    triggered_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    base_score       NUMERIC(10,4),
    confidence_score NUMERIC(10,4) NOT NULL,
    context_json     JSONB,
    llm_analysis     TEXT,
    status           VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending|reviewed|dismissed
    reviewed_at      TIMESTAMPTZ,
    review_action    VARCHAR(40),
    review_notes     TEXT,
    UNIQUE (scheme_code, signal_type, nav_date)
);

CREATE INDEX IF NOT EXISTS idx_mf_signals_status ON mf_signals(status);
CREATE INDEX IF NOT EXISTS idx_mf_signals_triggered_at ON mf_signals(triggered_at DESC);

-- ----------------------------------------------------------------
-- Ingestion run tracking
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mf_ingestion_runs (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_type   VARCHAR(40) NOT NULL, -- historical_seed|daily_nav|monthly_holdings|manual
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status     VARCHAR(20) NOT NULL DEFAULT 'running', -- running|success|failed
    stats_json JSONB,
    error_text TEXT
);

