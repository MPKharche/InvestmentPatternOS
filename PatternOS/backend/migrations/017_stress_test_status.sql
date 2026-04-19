-- Stress Test runs: add status tracking columns
-- Migration: 017_stress_test_status.sql

ALTER TABLE stress_test_runs
    ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'queued',
    ADD COLUMN IF NOT EXISTS error_message TEXT;

COMMENT ON COLUMN stress_test_runs.status IS 'queued|running|completed|failed';
COMMENT ON COLUMN stress_test_runs.error_message IS 'Error details if status=failed';
