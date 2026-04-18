-- ============================================================================
-- MF scheme enrichment: returns/ratios JSON + link status + manual overrides
-- ============================================================================

ALTER TABLE mf_schemes
  ADD COLUMN IF NOT EXISTS returns_json JSONB,
  ADD COLUMN IF NOT EXISTS ratios_json JSONB,
  ADD COLUMN IF NOT EXISTS valueresearch_link_status VARCHAR(20),
  ADD COLUMN IF NOT EXISTS morningstar_link_status VARCHAR(20);

