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
import pandas as pd

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
