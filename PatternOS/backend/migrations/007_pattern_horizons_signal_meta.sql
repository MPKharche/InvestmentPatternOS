-- Pattern events: forward returns at 1w / ~1m / ~3m / ~6m (trading-day approximations on daily bars)
ALTER TABLE pattern_events ADD COLUMN IF NOT EXISTS ret_21d  DOUBLE PRECISION;
ALTER TABLE pattern_events ADD COLUMN IF NOT EXISTS ret_63d  DOUBLE PRECISION;
ALTER TABLE pattern_events ADD COLUMN IF NOT EXISTS ret_126d DOUBLE PRECISION;

-- Live signals: optional forward returns from entry bar when history allows (same bar offsets)
ALTER TABLE signal_context ADD COLUMN IF NOT EXISTS forward_horizon_returns JSONB;

-- Tag Nifty 50 constituents for strict index filtering (seed file did not set index_name)
UPDATE universe SET index_name = 'Nifty 50'
WHERE symbol IN (
  'RELIANCE.NS','TCS.NS','HDFCBANK.NS','BHARTIARTL.NS','ICICIBANK.NS','INFOSYS.NS','SBIN.NS','HINDUNILVR.NS','ITC.NS','LT.NS',
  'KOTAKBANK.NS','AXISBANK.NS','BAJFINANCE.NS','ASIANPAINT.NS','MARUTI.NS','TITAN.NS','SUNPHARMA.NS','WIPRO.NS','ULTRACEMCO.NS',
  'NESTLEIND.NS','POWERGRID.NS','NTPC.NS','ONGC.NS','M&M.NS','TATAMOTORS.NS','TATASTEEL.NS','HCLTECH.NS','ADANIENT.NS',
  'ADANIPORTS.NS','COALINDIA.NS','JSWSTEEL.NS','BAJAJFINSV.NS','TECHM.NS','HINDALCO.NS','DIVISLAB.NS','CIPLA.NS','DRREDDY.NS',
  'APOLLOHOSP.NS','BAJAJ-AUTO.NS','EICHERMOT.NS','HEROMOTOCO.NS','BRITANNIA.NS','GRASIM.NS','TATACONSUM.NS','SHRIRAMFIN.NS',
  'BEL.NS','INDUSINDBK.NS','BPCL.NS','SBILIFE.NS','HDFCLIFE.NS'
);
