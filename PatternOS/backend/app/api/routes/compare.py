"""Stock comparison tool — side-by-side fundamental & technical metrics."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.data.yfinance_client import (
    fetch_stock_prices,
    get_stock_fundamentals,
    fetch_index_prices,
)
import pandas as pd
import numpy as np

router = APIRouter(prefix="/compare", tags=["compare"])


def _calculate_technical_indicators(df: pd.DataFrame) -> dict:
    """Basic TA: SMA20, SMA50, RSI14, MACD."""
    close = df["Close"]
    sma20 = close.rolling(20).mean().iloc[-1] if len(close) >= 20 else None
    sma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else None

    # RSI (14-period)
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = (100 - (100 / (1 + rs))).iloc[-1] if not rs.empty else None

    # MACD (12, 26, 9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - signal_line
    macd = {
        "macd": macd_line.iloc[-1] if not macd_line.empty else None,
        "signal": signal_line.iloc[-1] if not signal_line.empty else None,
        "histogram": macd_hist.iloc[-1] if not macd_hist.empty else None,
    }

    price = close.iloc[-1] if not close.empty else None
    above_sma20 = price > sma20 if price and sma20 else None
    above_sma50 = price > sma50 if price and sma50 else None

    return {
        "sma20": round(sma20, 2) if sma20 else None,
        "sma50": round(sma50, 2) if sma50 else None,
        "rsi_14": round(rsi, 2) if rsi else None,
        "macd": {k: round(v, 4) if v is not None else None for k, v in macd.items()},
        "above_sma20": above_sma20,
        "above_sma50": above_sma50,
        "price": round(price, 2) if price else None,
    }


@router.get("/stocks")
def compare_stocks(
    symbols: str = Query(
        ..., description="Comma-separated symbols, e.g., RELIANCE,TCS,INFY"
    ),
    exchange: str = Query("NSE"),
):
    """
    Compare up to 5 stocks side-by-side.

    Returns fundamental metrics (P/E, P/B, Debt/Equity, ROE, Dividend Yield, Beta, Market Cap)
    and technical indicators (SMA20/50, RSI14, MACD status).
    """
    symbol_list = [s.strip().upper() for s in symbols.split(",")]
    if len(symbol_list) > 5:
        raise HTTPException(400, "Maximum 5 symbols allowed")

    results = []
    for sym in symbol_list:
        try:
            # Fundamentals
            fundamentals = get_stock_fundamentals(sym, exchange)

            # Technicals: need 50+ days of data
            df = fetch_stock_prices(sym, "1d", 60, exchange, use_cache=True)
            if df.empty:
                technicals = {"error": "No price data"}
            else:
                technicals = _calculate_technical_indicators(df)

            results.append(
                {
                    "symbol": sym,
                    "fundamentals": fundamentals,
                    "technicals": technicals,
                }
            )
        except Exception as e:
            results.append(
                {
                    "symbol": sym,
                    "error": str(e),
                }
            )

    return {"comparisons": results}


@router.get("/correlation")
def stock_correlation(
    symbols: str = Query(..., description="Comma-separated symbols (2-5)"),
    days: int = Query(90, ge=20, le=365),
    exchange: str = Query("NSE"),
):
    """
    Calculate correlation matrix between selected stocks based on daily returns.
    Returns correlation coefficients (0 to 1).
    """
    symbol_list = [s.strip().upper() for s in symbols.split(",")]
    if not (2 <= len(symbol_list) <= 5):
        raise HTTPException(400, "Provide 2-5 symbols")

    price_data = {}
    for sym in symbol_list:
        df = fetch_stock_prices(sym, "1d", days, exchange, use_cache=True)
        if df.empty:
            raise HTTPException(404, f"No data for {sym}")
        price_data[sym] = df["Close"].pct_change().dropna()

    # Build correlation matrix
    corr_matrix = {}
    for s1 in symbol_list:
        corr_matrix[s1] = {}
        for s2 in symbol_list:
            if s1 == s2:
                corr_matrix[s1][s2] = 1.0
            else:
                # Align series
                combined = pd.concat(
                    [price_data[s1], price_data[s2]], axis=1, join="inner"
                ).dropna()
                if len(combined) < 10:
                    corr_matrix[s1][s2] = None
                else:
                    corr = combined.iloc[:, 0].corr(combined.iloc[:, 1])
                    corr_matrix[s1][s2] = round(corr, 4) if pd.notna(corr) else None

    return {
        "symbols": symbol_list,
        "correlation": corr_matrix,
        "method": "pearson",
        "period_days": days,
    }
