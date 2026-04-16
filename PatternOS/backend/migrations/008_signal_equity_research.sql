-- Pre-inbox AI equity desk note (JSON): opinion, stance, sources, crawl snippets, etc.
ALTER TABLE signal_context
  ADD COLUMN IF NOT EXISTS equity_research_note JSONB;
