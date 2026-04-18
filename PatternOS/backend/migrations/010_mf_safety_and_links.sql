-- ============================================================================
-- MF safety protocols: provider state, cursors, task audit + external links
-- ============================================================================

-- Provider circuit breaker state (pause/resume, failure counts)
CREATE TABLE IF NOT EXISTS mf_provider_state (
    provider             VARCHAR(40) PRIMARY KEY, -- mfdata|mfapi|amfi|valueresearch|morningstar
    paused_until         TIMESTAMPTZ,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    last_error           TEXT,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Resumable cursors for long-running backfills / enrichment
CREATE TABLE IF NOT EXISTS mf_ingestion_cursors (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider       VARCHAR(40) NOT NULL,
    endpoint_class VARCHAR(60) NOT NULL, -- nav_history|scheme_enrich|holdings|links
    scheme_code    INTEGER,
    family_id      INTEGER,
    cursor_json    JSONB NOT NULL,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider, endpoint_class, scheme_code, family_id)
);

-- Per-task audit under a run (request counts, retries, status histogram)
CREATE TABLE IF NOT EXISTS mf_ingestion_tasks (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id         UUID REFERENCES mf_ingestion_runs(id) ON DELETE CASCADE,
    provider       VARCHAR(40) NOT NULL,
    endpoint_class VARCHAR(60) NOT NULL,
    scheme_code    INTEGER,
    family_id      INTEGER,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at    TIMESTAMPTZ,
    status         VARCHAR(20) NOT NULL DEFAULT 'running', -- running|success|failed|skipped
    request_count  INTEGER NOT NULL DEFAULT 0,
    retry_count    INTEGER NOT NULL DEFAULT 0,
    backoff_seconds NUMERIC(12,2) NOT NULL DEFAULT 0,
    http_statuses  JSONB,
    error_text     TEXT
);

CREATE INDEX IF NOT EXISTS idx_mf_tasks_run_id ON mf_ingestion_tasks(run_id);
CREATE INDEX IF NOT EXISTS idx_mf_tasks_provider ON mf_ingestion_tasks(provider, endpoint_class);

-- External links + enrichment timestamps on schemes
ALTER TABLE mf_schemes
  ADD COLUMN IF NOT EXISTS morningstar_sec_id TEXT,
  ADD COLUMN IF NOT EXISTS valueresearch_url TEXT,
  ADD COLUMN IF NOT EXISTS morningstar_url TEXT,
  ADD COLUMN IF NOT EXISTS mfdata_fetched_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS links_last_checked_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS links_last_check_status INTEGER;

