"""
Data fetcher — wraps yfinance.
Handles NSE (.NS suffix), US, and other exchanges.
"""
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta


TIMEFRAME_MAP = {
    "1d": ("1d", 120),   # interval, lookback_days  (for OHLCV display)
    "1h": ("1h", 30),
    "1w": ("1wk", 365),
    "1M": ("1mo", 1825),
}

# Extended lookback for indicator warmup (EMA200 needs 200+ bars)
INDICATOR_LOOKBACK_MAP = {
    "1d": ("1d", 900),   # ~3.5y trading days → EMA200 + 6m forward from historical bars
    "1h": ("1h", 120),
    "1w": ("1wk", 730),
    "1M": ("1mo", 3650),
}


def fetch_ohlcv(symbol: str, timeframe: str = "1d", extended: bool = False) -> pd.DataFrame | None:
    """
    Fetch OHLCV for a symbol.
    Returns DataFrame with columns: Open, High, Low, Close, Volume (title-case).
    Returns None if data unavailable.

    When extended=True uses INDICATOR_LOOKBACK_MAP (more history for indicator warmup).
    When extended=False (default) uses TIMEFRAME_MAP (shorter window for chart display).
    """
    source_map = INDICATOR_LOOKBACK_MAP if extended else TIMEFRAME_MAP
    interval, lookback_days = source_map.get(timeframe, ("1d", 500 if extended else 120))
    end = datetime.utcnow()
    start = end - timedelta(days=lookback_days)

    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start, end=end, interval=interval, auto_adjust=True)
        if df.empty or len(df) < 10:
            return None
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.dropna(inplace=True)
        return df
    except Exception:
        return None


def build_chart_summary(df: pd.DataFrame, symbol: str) -> str:
    """Compact text summary of recent price action for LLM context."""
    if df is None or df.empty:
        return f"{symbol}: No data available."

    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    high_20 = df["High"].tail(20).max()
    low_20 = df["Low"].tail(20).min()
    avg_vol_20 = df["Volume"].tail(20).mean()
    vol_ratio = last["Volume"] / avg_vol_20 if avg_vol_20 > 0 else 1.0
    change_pct = ((last["Close"] - prev["Close"]) / prev["Close"]) * 100

    return (
        f"{symbol}: Close={last['Close']:.2f} ({change_pct:+.1f}%), "
        f"Vol={last['Volume']:,.0f} ({vol_ratio:.1f}x avg), "
        f"20-bar range={low_20:.2f}-{high_20:.2f}, "
        f"Bars={len(df)}"
    )
