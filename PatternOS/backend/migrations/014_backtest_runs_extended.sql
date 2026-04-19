-- Extend backtest_runs with params, notes, tags (Feature 2: Backtest Repository)
-- Migration: 014_backtest_runs_extended.sql

-- Add params_json (scan parameters: symbols, scope, date range, pattern_version)
ALTER TABLE backtest_runs
    ADD COLUMN IF NOT EXISTS params_json JSONB;

-- Add notes (user annotation)
ALTER TABLE backtest_runs
    ADD COLUMN IF NOT EXISTS notes TEXT;

-- Add tags (grouping labels)
ALTER TABLE backtest_runs
    ADD COLUMN IF NOT EXISTS tags JSONB;

-- Index on pattern_id already exists from migration 005; keep it

COMMENT ON COLUMN backtest_runs.params_json IS 'Full scan parameters (symbols, scope, start/end dates, pattern_version)';
COMMENT ON COLUMN backtest_runs.notes IS 'User annotation/notes about this run';
COMMENT ON COLUMN backtest_runs.tags IS 'Grouping labels e.g. ["production", "experiment", "macd-tuning"]';
