-- Create screener_templates table (Feature 1 enhancement: preset templates)
-- Migration: 015_screener_templates.sql

CREATE TABLE IF NOT EXISTS screener_templates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(100) NOT NULL UNIQUE,
    description     TEXT,
    category        VARCHAR(50) NOT NULL,  -- "technical", "fundamental", "momentum", "value", etc.
    asset_class     VARCHAR(30) DEFAULT 'equity',
    rules_json      JSONB NOT NULL,  -- { "logic": "AND", "conditions": [...] }
    tags            JSONB,            -- ["oscillator", "trend", "volatility"]
    is_active       BOOLEAN DEFAULT TRUE,
    usage_count     INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_screener_templates_category ON screener_templates(category);
CREATE INDEX IF NOT EXISTS idx_screener_templates_active ON screener_templates(is_active);

COMMENT ON COLUMN screener_templates.name IS 'Unique template name (e.g., "RSI Oversold")';
COMMENT ON COLUMN screener_templates.category IS 'Template category for grouping in gallery';
COMMENT ON COLUMN screener_templates.rules_json IS 'Full rulebook JSON (logic + conditions array)';
COMMENT ON COLUMN screener_templates.tags IS 'Searchable tags for discovery';
COMMENT ON COLUMN screener_templates.usage_count IS 'Incremented each time template is applied';
