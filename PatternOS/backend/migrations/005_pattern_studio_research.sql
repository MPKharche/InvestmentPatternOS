-- Pattern backtest events (detected instances of a pattern)
CREATE TABLE IF NOT EXISTS pattern_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pattern_id UUID NOT NULL REFERENCES patterns(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    exchange VARCHAR(20) DEFAULT 'NSE',
    timeframe VARCHAR(10) DEFAULT '1d',
    detected_at DATE NOT NULL,           -- bar date when pattern triggered
    entry_price FLOAT,
    indicator_snapshot JSONB,            -- indicator values at detection
    chart_context TEXT,                  -- brief description of setup
    -- Post-event outcome (filled after price data available)
    ret_5d FLOAT,                        -- % return 5 days after
    ret_10d FLOAT,
    ret_20d FLOAT,
    max_gain_20d FLOAT,                  -- max % gain within 20 days
    max_loss_20d FLOAT,                  -- max % loss within 20 days
    outcome VARCHAR(20),                 -- 'success', 'failure', 'neutral'
    -- User feedback
    user_feedback VARCHAR(20),           -- 'valid', 'invalid', 'unsure'
    user_notes TEXT,
    -- Metadata
    backtest_run_id UUID,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(pattern_id, symbol, timeframe, detected_at)
);

-- Backtest run records
CREATE TABLE IF NOT EXISTS backtest_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pattern_id UUID NOT NULL REFERENCES patterns(id) ON DELETE CASCADE,
    version_num INTEGER DEFAULT 1,
    symbols_scanned INTEGER DEFAULT 0,
    events_found INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    neutral_count INTEGER DEFAULT 0,
    success_rate FLOAT,
    avg_ret_5d FLOAT,
    avg_ret_10d FLOAT,
    avg_ret_20d FLOAT,
    status VARCHAR(20) DEFAULT 'running',  -- 'running', 'complete', 'failed'
    error_message TEXT,
    started_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ
);

-- Pattern study (LLM-generated analysis)
CREATE TABLE IF NOT EXISTS pattern_studies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pattern_id UUID NOT NULL REFERENCES patterns(id) ON DELETE CASCADE,
    backtest_run_id UUID REFERENCES backtest_runs(id),
    llm_analysis TEXT NOT NULL,          -- full LLM narrative analysis
    success_factors JSONB,               -- list of factors that correlated with success
    failure_factors JSONB,               -- list of factors that correlated with failure
    rulebook_suggestions JSONB,          -- proposed rulebook modifications
    confidence_improvements JSONB,       -- suggested confidence score adjustments
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pattern_events_pattern_id ON pattern_events(pattern_id);
CREATE INDEX IF NOT EXISTS idx_pattern_events_symbol ON pattern_events(symbol);
CREATE INDEX IF NOT EXISTS idx_backtest_runs_pattern_id ON backtest_runs(pattern_id);
