-- ============================================================================
-- Data cache: stock prices and fundamentals (24h TTL)
-- Supports yfinance-based data provider for Indian equities
-- ============================================================================

CREATE TABLE IF NOT EXISTS stock_prices (
  symbol       VARCHAR(20) NOT NULL,
  timeframe    VARCHAR(10) NOT NULL DEFAULT '1d',
  trade_date   DATE NOT NULL,
  open         FLOAT,
  high         FLOAT,
  low          FLOAT,
  close        FLOAT,
  volume       FLOAT,
  fetched_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (symbol, timeframe, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_stock_prices_expire ON stock_prices (fetched_at);

CREATE TABLE IF NOT EXISTS stock_fundamentals (
  symbol                 VARCHAR(20) NOT NULL PRIMARY KEY,
  pe_ratio               FLOAT,
  pb_ratio               FLOAT,
  debt_to_equity         FLOAT,
  roe                    FLOAT,
  dividend_yield         FLOAT,
  beta                   FLOAT,
  market_cap             FLOAT,
  enterprise_value       FLOAT,
  forward_pe             FLOAT,
  trailing_pe            FLOAT,
  eps                    FLOAT,
  revenue_per_share      FLOAT,
  fetched_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stock_fundamentals_expire ON stock_fundamentals (fetched_at);
