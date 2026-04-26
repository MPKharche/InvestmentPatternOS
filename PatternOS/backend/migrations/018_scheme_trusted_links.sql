-- Trusted third-party deep-link keys (Yahoo Finance quote symbol, Value Research fund id).
-- URLs are derived in app code from these + scheme name / ISIN fallbacks.

ALTER TABLE mf_schemes ADD COLUMN IF NOT EXISTS yahoo_finance_symbol VARCHAR(32);
ALTER TABLE mf_schemes ADD COLUMN IF NOT EXISTS value_research_fund_id INTEGER;
ALTER TABLE mf_schemes ADD COLUMN IF NOT EXISTS yahoo_finance_url TEXT;
ALTER TABLE mf_schemes ADD COLUMN IF NOT EXISTS yahoo_link_status VARCHAR(20);

COMMENT ON COLUMN mf_schemes.yahoo_finance_symbol IS 'Yahoo Finance ticker e.g. 0P0000XWAB.BO';
COMMENT ON COLUMN mf_schemes.value_research_fund_id IS 'Value Research Online numeric fund id (URL /funds/{id}/...)';
COMMENT ON COLUMN mf_schemes.yahoo_finance_url IS 'Resolved Yahoo quote or lookup URL (denormalized for list views)';
COMMENT ON COLUMN mf_schemes.yahoo_link_status IS 'quote | lookup_isin | search_google';
