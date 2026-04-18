"""F&O analysis routes — PCR, OI analysis."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.data.nsepy_client import (
    fetch_pcr_data,
    fetch_nifty_50_oi,
    fetch_fno_contracts,
    get_quote,
)
from app.data.yfinance_client import fetch_stock_prices
import pandas as pd

router = APIRouter(prefix="/fno", tags=["fno"])


@router.get("/pcr")
def pcr(
    symbol: str | None = Query(None, description="Stock symbol; omit for Nifty PCR"),
):
    """
    Put-Call Ratio for Nifty or a stock.

    PCR > 1: Bullish (more puts = hedging/ bearish bets? Actually >1 means more puts, typically bearish on index)
    PCR < 1: Bearish (more calls = bullish bets)
    For retail-heavy Indian market, interpretation differs.

    Also returns total CE and PE open interest.
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


@router.get("/oi-buildup")
def oi_buildup(
    symbol: str = Query(..., description="F&O stock symbol, e.g., RELIANCE"),
    days: int = Query(5, ge=1, le=30),
):
    """
    Identify stocks with significant Open Interest buildup.

    Returns top symbols with highest change in OI (both long & short side).
    """
    try:
        import yfinance as yf

        # Get list of F&O eligible stocks from NSE? Hard. Use yfinance to get historical OI
        ticker = yf.Ticker(symbol + ".NS")
        # Fetch options expiry dates
        expiry_dates = ticker.options
        if not expiry_dates:
            return {"symbol": symbol, "message": "No options data available"}

        # Get call and put chain for nearest expiry
        nearest = expiry_dates[0]
        chain = ticker.option_chain(nearest)
        calls = chain.calls
        puts = chain.puts

        # Aggregate by strike? Or just totals
        total_ce_oi = calls["openInterest"].sum()
        total_pe_oi = puts["openInterest"].sum()

        # Top strikes by OI
        top_calls = (
            calls[["strike", "openInterest", "lastPrice"]]
            .sort_values("openInterest", ascending=False)
            .head(10)
            .to_dict(orient="records")
        )
        top_puts = (
            puts[["strike", "openInterest", "lastPrice"]]
            .sort_values("openInterest", ascending=False)
            .head(10)
            .to_dict(orient="records")
        )

        return {
            "symbol": symbol,
            "expiry": str(nearest),
            "total_ce_oi": int(total_ce_oi),
            "total_pe_oi": int(total_pe_oi),
            "pcr": total_pe_oi / total_ce_oi if total_ce_oi > 0 else None,
            "top_call_strikes": top_calls,
            "top_put_strikes": top_puts,
        }
    except Exception as e:
        raise HTTPException(500, f"Failed OI buildup: {str(e)}")


@router.get("/nifty-oi-history")
def nifty_oi_history(days: int = Query(30, ge=1, le=90)):
    """
    Fetch Nifty futures open interest history.
    Useful for tracking institutional money flow.
    """
    try:
        df = fetch_nifty_50_oi(days=days)
        if df.empty:
            return {"error": "No OI data fetched"}

        # Select relevant columns
        df = df[
            ["Open", "High", "Low", "Close", "Volume", "OpenInterest", "ChangeinOI"]
        ].tail(days)
        records = []
        for date_idx, row in df.iterrows():
            records.append(
                {
                    "date": date_idx.strftime("%Y-%m-%d"),
                    "open": round(float(row["Open"]), 2),
                    "high": round(float(row["High"]), 2),
                    "low": round(float(row["Low"]), 2),
                    "close": round(float(row["Close"]), 2),
                    "volume": int(row["Volume"]),
                    "oi": int(row["OpenInterest"]),
                    "oi_change": int(row["ChangeinOI"]),
                }
            )
        return {"symbol": "NIFTY", "data": records}
    except Exception as e:
        raise HTTPException(500, f"Failed: {str(e)}")
