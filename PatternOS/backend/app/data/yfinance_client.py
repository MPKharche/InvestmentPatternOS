"""
yfinance data provider with 24h PostgreSQL caching.

Functions:
- fetch_stock_prices(symbol, timeframe, days) → pd.DataFrame
- fetch_stock_info(symbol) → dict
- get_stock_fundamentals(symbol) → dict (cached)
- fetch_index_prices(index_name, timeframe, days) → pd.DataFrame
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
import pandas as pd
import yfinance as yf

from sqlalchemy.orm import Session
from app.db.models import StockPrice, StockFundamental
from app.db.session import SessionLocal

# Cache TTL: 24 hours
CACHE_TTL_HOURS = 24

# NSE symbol mapping
NSE_SUFFIX = ".NS"
BSE_SUFFIX = ".BO"


def _normalize_symbol(symbol: str, exchange: str = "NSE") -> str:
    """Add exchange suffix if missing."""
    sym = symbol.upper()
    if exchange == "NSE" and not sym.endswith(".NS"):
        return sym + ".NS"
    if exchange == "BSE" and not sym.endswith(".BO"):
        return sym + ".BO"
    return sym


def _is_cache_valid(fetched_at: Optional[datetime]) -> bool:
    """Check if cached data is within 24h TTL."""
    if fetched_at is None:
        return False
    now = datetime.now(timezone.utc)
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    return (now - fetched_at) < timedelta(hours=CACHE_TTL_HOURS)


def fetch_stock_prices(
    symbol: str,
    timeframe: str = "1d",
    days: int = 120,
    exchange: str = "NSE",
    use_cache: bool = True,
) -> pd.DataFrame:
    """
    Fetch OHLCV data for a stock from yfinance with 24h PostgreSQL cache.

    Args:
        symbol: Stock symbol (e.g., "RELIANCE")
        timeframe: "1d", "1h", "1wk", "1mo"
        days: Number of lookback days
        exchange: "NSE" or "BSE"
        use_cache: Enable/disable cache lookup

    Returns:
        DataFrame with columns: Open, High, Low, Close, Volume (title-case)
    """
    normalized = _normalize_symbol(symbol, exchange)
    db: Session = SessionLocal()

    try:
        # Check cache if enabled
        if use_cache:
            recent_prices = (
                db.query(StockPrice)
                .filter_by(symbol=normalized, timeframe=timeframe)
                .order_by(StockPrice.trade_date.desc())
                .limit(days)
                .all()
            )
            if recent_prices and _is_cache_valid(recent_prices[0].fetched_at):
                # Build DataFrame from cache
                data = {
                    "Open": [p.open for p in reversed(recent_prices)],
                    "High": [p.high for p in reversed(recent_prices)],
                    "Low": [p.low for p in reversed(recent_prices)],
                    "Close": [p.close for p in reversed(recent_prices)],
                    "Volume": [p.volume for p in reversed(recent_prices)],
                }
                idx = [pd.Timestamp(p.trade_date) for p in reversed(recent_prices)]
                df = pd.DataFrame(data, index=idx)
                df.dropna(inplace=True)
                if len(df) >= 10:
                    return df

        # Fetch from yfinance
        ticker = yf.Ticker(normalized)
        end = datetime.utcnow()
        start = end - timedelta(days=days)

        # Map timeframe to yfinance interval
        interval_map = {
            "1d": "1d",
            "1h": "1h",
            "1wk": "1wk",
            "1w": "1wk",
            "1mo": "1mo",
            "1m": "1mo",
        }
        interval = interval_map.get(timeframe, "1d")
        df = ticker.history(start=start, end=end, interval=interval, auto_adjust=True)

        if df.empty or len(df) < 10:
            return pd.DataFrame()

        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.dropna(inplace=True)

        # Cache the fresh data
        _cache_stock_prices(db, normalized, timeframe, df)

        return df
    finally:
        db.close()


def _cache_stock_prices(
    db: Session, symbol: str, timeframe: str, df: pd.DataFrame
) -> None:
    """Store price data in PostgreSQL cache, replacing old entries."""
    # Delete existing entries for this symbol+timeframe
    db.query(StockPrice).filter_by(symbol=symbol, timeframe=timeframe).delete()

    # Insert new rows
    records = []
    for date_idx, row in df.iterrows():
        date_val = date_idx.date() if hasattr(date_idx, "date") else date_idx
        records.append(
            StockPrice(
                symbol=symbol,
                timeframe=timeframe,
                trade_date=date_val,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row["Volume"]),
                fetched_at=datetime.now(timezone.utc),
            )
        )

    db.add_all(records)
    db.commit()


def fetch_stock_info(
    symbol: str, exchange: str = "NSE", use_cache: bool = True
) -> dict:
    """
    Fetch company fundamentals from yfinance with caching.

    Returns:
        Dict with keys: pe_ratio, pb_ratio, debt_to_equity, roe,
        dividend_yield, beta, market_cap, etc.
    """
    normalized = _normalize_symbol(symbol, exchange)
    db: Session = SessionLocal()

    try:
        # Check cache
        if use_cache:
            cached = db.query(StockFundamental).filter_by(symbol=normalized).first()
            if cached and _is_cache_valid(cached.fetched_at):
                return {
                    "pe_ratio": cached.pe_ratio,
                    "pb_ratio": cached.pb_ratio,
                    "debt_to_equity": cached.debt_to_equity,
                    "roe": cached.roe,
                    "dividend_yield": cached.dividend_yield,
                    "beta": cached.beta,
                    "market_cap": cached.market_cap,
                    "enterprise_value": cached.enterprise_value,
                    "forward_pe": cached.forward_pe,
                    "trailing_pe": cached.trailing_pe,
                    "eps": cached.eps,
                    "revenue_per_share": cached.revenue_per_share,
                }

        # Fetch from yfinance
        ticker = yf.Ticker(normalized)
        info = ticker.info or {}

        def safe_float(val) -> Optional[float]:
            try:
                return float(val) if val is not None else None
            except (ValueError, TypeError):
                return None

        fundamentals = {
            "pe_ratio": safe_float(info.get("trailingPE") or info.get("forwardPE")),
            "pb_ratio": safe_float(info.get("priceToBook")),
            "debt_to_equity": safe_float(info.get("debtToEquity")),
            "roe": safe_float(info.get("returnOnEquity")),
            "dividend_yield": safe_float(info.get("dividendYield")),
            "beta": safe_float(info.get("beta")),
            "market_cap": safe_float(info.get("marketCap")),
            "enterprise_value": safe_float(info.get("enterpriseValue")),
            "forward_pe": safe_float(info.get("forwardPE")),
            "trailing_pe": safe_float(info.get("trailingPE")),
            "eps": safe_float(info.get("trailingEPS")),
            "revenue_per_share": safe_float(info.get("revenuePerShare")),
        }

        # Cache it
        _cache_fundamentals(db, normalized, fundamentals)

        return fundamentals
    finally:
        db.close()


def _cache_fundamentals(db: Session, symbol: str, data: dict) -> None:
    """Store fundamentals in cache."""
    existing = db.query(StockFundamental).filter_by(symbol=symbol).first()
    if existing:
        for key, val in data.items():
            setattr(existing, key, val)
        existing.fetched_at = datetime.now(timezone.utc)
    else:
        record = StockFundamental(
            symbol=symbol, fetched_at=datetime.now(timezone.utc), **data
        )
        db.add(record)
    db.commit()


def get_stock_fundamentals(symbol: str, exchange: str = "NSE") -> dict:
    """Convenience wrapper for fetch_stock_info."""
    return fetch_stock_info(symbol, exchange)


def fetch_index_prices(
    index_name: str,
    timeframe: str = "1d",
    days: int = 365,
) -> pd.DataFrame:
    """
    Fetch index data from yfinance.
    index_name examples: "^NSEI" (Nifty 50), "^BSESN" (Sensex), "^NSEBANK" (Bank Nifty)
    """
    # Map common index names to tickers
    index_tickers = {
        "NIFTY": "^NSEI",
        "NIFTY 50": "^NSEI",
        "SENSEX": "^BSESN",
        "BANKNIFTY": "^NSEBANK",
        "NIFTY BANK": "^NSEBANK",
        "NIFTY IT": "^CNXIT",
    }
    ticker_sym = index_tickers.get(index_name.upper(), index_name)
    return fetch_stock_prices(ticker_sym, timeframe, days, exchange="NSE")


def purge_expired_price_cache(db: Session) -> int:
    """Remove expired entries from stock_prices and stock_fundamentals (older than 24h)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=CACHE_TTL_HOURS)
    count1 = db.query(StockPrice).filter(StockPrice.fetched_at < cutoff).delete()
    count2 = (
        db.query(StockFundamental).filter(StockFundamental.fetched_at < cutoff).delete()
    )
    db.commit()
    return count1 + count2
