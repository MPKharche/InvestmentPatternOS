-- PatternOS: Candidate lifecycle + alert journal + telegram feedback + review cycles

CREATE TABLE IF NOT EXISTS pattern_candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(160) NOT NULL,
    objective TEXT NOT NULL,
    source_type VARCHAR(20) NOT NULL DEFAULT 'studio',
    screenshot_refs JSONB,
    traits_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    draft_rules_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    conditions_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    universes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(30) NOT NULL DEFAULT 'draft',
    validation_summary JSONB,
    revision_notes TEXT,
    linked_pattern_id UUID REFERENCES patterns(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS signal_alert_journal (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id UUID NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
    channel VARCHAR(20) NOT NULL DEFAULT 'telegram',
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    telegram_chat_id VARCHAR(40),
    telegram_message_id VARCHAR(40),
    delivered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS telegram_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id UUID NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
    alert_id UUID REFERENCES signal_alert_journal(id) ON DELETE SET NULL,
    action VARCHAR(40) NOT NULL,
    username VARCHAR(120),
    chat_id VARCHAR(40),
    raw_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pattern_review_cycles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pattern_id UUID NOT NULL REFERENCES patterns(id) ON DELETE CASCADE,
    review_period_start TIMESTAMPTZ,
    review_period_end TIMESTAMPTZ,
    justified_analysis TEXT NOT NULL,
    suggested_changes JSONB,
    metrics_before_json JSONB,
    metrics_after_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS telegram_sync_state (
    id INTEGER PRIMARY KEY,
    last_update_id INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO telegram_sync_state (id, last_update_id)
VALUES (1, 0)
ON CONFLICT (id) DO NOTHING;
