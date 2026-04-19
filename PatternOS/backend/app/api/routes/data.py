"""Data provider routes — stock prices, fundamentals, indices."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.data.yfinance_client import (
    fetch_stock_prices,
    fetch_stock_info,
    fetch_index_prices,
    get_stock_fundamentals,
)
from app.data.nsepy_client import (
    fetch_pcr_data,
    fetch_nifty_50_oi,
    fetch_fno_contracts,
    get_quote,
)
from app.scanner.indicators import compute_indicators
import pandas as pd
import math

router = APIRouter(prefix="/data", tags=["data"])


@router.get("/stock/{symbol}")
def get_stock_data(
    symbol: str,
    timeframe: str = Query("1d", regex="^(1d|1h|1wk|1mo|1w|1m)$"),
    days: int = Query(120, ge=10, le=2000),
    exchange: str = Query("NSE", regex="^(NSE|BSE|NASDAQ|NYSE)$"),
    include_fundamentals: bool = Query(True),
):
    """
    Fetch price history and fundamentals for a stock.

    Returns OHLCV DataFrame (as list of dicts) + fundamentals dict.
    Cached for 24 hours.
    """
    df = fetch_stock_prices(symbol, timeframe, days, exchange, use_cache=True)
    if df.empty:
        raise HTTPException(404, f"No price data found for {symbol}")

    # Convert DataFrame to list of dicts for JSON response
    price_data = []
    for date_idx, row in df.iterrows():
        price_data.append(
            {
                "date": date_idx.strftime("%Y-%m-%d")
                if hasattr(date_idx, "strftime")
                else str(date_idx),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            }
        )

    result = {
        "symbol": symbol.upper(),
        "exchange": exchange,
        "timeframe": timeframe,
        "prices": price_data,
        "fundamentals": None,
    }

    if include_fundamentals:
        try:
            fundamentals = get_stock_fundamentals(symbol, exchange)
            result["fundamentals"] = fundamentals
        except Exception as e:
            result["fundamentals"] = {"error": str(e)}

    return result


@router.get("/index/{index_name}")
def get_index_data(
    index_name: str,
    timeframe: str = Query("1d", regex="^(1d|1h|1wk|1mo)$"),
    days: int = Query(365, ge=10, le=2000),
):
    """
    Fetch index price history (Nifty 50, Bank Nifty, etc.).

    Supported index names: NIFTY, SENSEX, BANKNIFTY, NIFTY IT, etc.
    Returns OHLCV data as list of dicts.
    """
    df = fetch_index_prices(index_name, timeframe, days)
    if df.empty:
        raise HTTPException(404, f"No index data found for {index_name}")

    price_data = []
    for date_idx, row in df.iterrows():
        price_data.append(
            {
                "date": date_idx.strftime("%Y-%m-%d")
                if hasattr(date_idx, "strftime")
                else str(date_idx),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            }
        )

    return {
        "index": index_name,
        "timeframe": timeframe,
        "prices": price_data,
    }


@router.get("/fno/pcr")
def get_pcr(
    symbol: str = Query(
        None, description="Stock symbol, e.g., RELIANCE. omit for Nifty PCR"
    ),
):
    """
    Get Put-Call Ratio for Nifty or a specific stock.
    PCR > 1 indicates bullish sentiment (more puts than calls).
    PCR < 1 indicates bearish sentiment.
    """
    try:
        data = fetch_pcr_data(symbol)
        return {
            "symbol": symbol.upper() if symbol else "NIFTY",
            "pcr": data.get("pcr"),
            "total_ce_oi": data.get("total_ce_oi", 0),
            "total_pe_oi": data.get("total_pe_oi", 0),
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch PCR: {str(e)}")


@router.get("/fno/quote")
def get_live_quote(
    symbol: str = Query(..., description="NSE stock symbol, e.g., RELIANCE"),
):
    """Get live quote from NSE (delayed by few minutes)."""
    try:
        quote = get_quote(symbol)
        return quote
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch quote: {str(e)}")


@router.get("/fno/option-chain")
def get_option_chain(
    symbol: str = Query(..., description="Stock or index symbol"),
    expiry: str = Query(None, description="Expiry date in YYYY-MM-DD format"),
):
    """
    Fetch option chain for a stock/index.
    Returns strike-wise call and put open interest, last prices.
    """
    import pandas as pd

    try:
        df = fetch_fno_contracts(symbol, pd.to_datetime(expiry) if expiry else None)
        if df.empty:
            return {"symbol": symbol, "contracts": []}
        # Convert to dict
        contracts = df.to_dict(orient="records")
        return {"symbol": symbol, "contracts": contracts}
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch option chain: {str(e)}")


@router.get("/stock/{symbol}/indicators")
def get_stock_indicators(
    symbol: str,
    timeframe: str = Query("1d", regex="^(1d|1h|1wk|1mo|1w|1m)$"),
    days: int = Query(120, ge=10, le=2000),
    exchange: str = Query("NSE", regex="^(NSE|BSE|NASDAQ|NYSE)$"),
    indicators: str = Query(
        "all", description="comma-separated: sma,ema,rsi,macd,bb,atr,stoch,adx,obv"
    ),
    rsi_period: int = Query(14, ge=2, le=50),
    sma_periods: str = Query("20,50,200", description="comma-separated SMA periods"),
    macd_fast: int = Query(12, ge=2, le=50),
    macd_slow: int = Query(26, ge=2, le=50),
    macd_signal: int = Query(9, ge=2, le=50),
    bb_window: int = Query(20, ge=2, le=50),
    bb_std: float = Query(2.0, ge=0.1, le=5.0),
    atr_period: int = Query(14, ge=2, le=50),
):
    """
    Fetch price history + technical indicators with custom parameters.
    Returns price bars and separate indicator series aligned to dates.
    """
    # Fetch price data
    df = fetch_stock_prices(symbol, timeframe, days, exchange, use_cache=True)
    if df.empty:
        raise HTTPException(404, f"No price data found for {symbol}")

    # Parse SMA periods
    sma_list = tuple(
        int(p.strip()) for p in sma_periods.split(",") if p.strip().isdigit()
    )

    # Compute indicators with custom params
    idf = compute_indicators(
        df,
        rsi_period=rsi_period,
        sma_periods=sma_list if sma_list else (20, 50, 200),
        macd_fast=macd_fast,
        macd_slow=macd_slow,
        macd_signal=macd_signal,
        bb_window=bb_window,
        bb_std=bb_std,
        atr_period=atr_period,
    )

    # Build price data
    price_data = []
    for date_idx, row in idf.iterrows():
        price_data.append(
            {
                "date": date_idx.strftime("%Y-%m-%d")
                if hasattr(date_idx, "strftime")
                else str(date_idx),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            }
        )

    # Helper: convert to JSON-safe float
    def _to_float(x):
        try:
            f = float(x)
            if math.isnan(f) or math.isinf(f):
                return None
            return round(f, 4)
        except:
            return None

    # Determine which indicator columns to include
    indicator_columns = [
        "ema_20",
        "ema_50",
        "ema_200",
        "sma_20",
        "sma_50",
        "sma_200",
        "bb_upper",
        "bb_mid",
        "bb_lower",
        "bb_width",
        "rsi",
        "macd",
        "macd_signal",
        "macd_hist",
        "atr",
        "stoch_k",
        "stoch_d",
        "adx",
        "adx_di_pos",
        "adx_di_neg",
        "obv",
    ]
    # Filter based on `indicators` param unless "all"
    requested = set()
    if indicators == "all":
        requested = set(indicator_columns)
    else:
        tokens = {t.strip().lower() for t in indicators.split(",") if t.strip()}
        if "sma" in tokens:
            requested.update(f"sma_{p}" for p in sma_list)
        if "ema" in tokens:
            requested.update(["ema_20", "ema_50", "ema_200"])
        if "bb" in tokens:
            requested.update(["bb_upper", "bb_mid", "bb_lower", "bb_width"])
        if "macd" in tokens:
            requested.update(["macd", "macd_signal", "macd_hist"])
        if "stoch" in tokens:
            requested.update(["stoch_k", "stoch_d"])
        if "adx" in tokens:
            requested.update(["adx", "adx_di_pos", "adx_di_neg"])
        # direct passes
        direct = {"rsi", "atr", "obv"}.intersection(tokens)
        requested.update(direct)
        # Also handle individual names like "rsi", "atr"
        for t in tokens:
            if t in {"rsi", "atr", "obv"}:
                requested.add(t)

    # Build indicators dict
    indicators_dict: dict[str, list[float | None]] = {}
    for col in indicator_columns:
        if col in requested and col in idf.columns:
            indicators_dict[col] = [
                _to_float(idf[col].iloc[i]) for i in range(len(idf))
            ]

    return {
        "symbol": symbol.upper(),
        "exchange": exchange,
        "timeframe": timeframe,
        "prices": price_data,
        "indicators": indicators_dict,
    }
