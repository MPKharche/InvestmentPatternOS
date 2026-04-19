"""
NSEpy F&O data provider.

Provides:
- PCR (Put-Call Ratio) for Nifty and stocks
- Open Interest data
- F&O contract details

Note: NSEpy scrapes NSE website which may be blocked or have SSL issues.
All functions return empty/None on failure.
"""

from __future__ import annotations

import os

# Disable SSL verification for nsepy (NSE website SSL issues)
os.environ["PYTHONHTTPSVERIFY"] = "0"

from datetime import datetime, timezone, timedelta
from typing import Optional
import pandas as pd

from sqlalchemy.orm import Session
from app.db.models import ScreeningCache  # reuse existing cache pattern
from app.data.yfinance_client import CACHE_TTL_HOURS

try:
    import warnings

    warnings.filterwarnings("ignore", category=UserWarning, module="urllib3")
    import urllib3

    urllib3.disable_warnings()

    from nsepy import get_history, get_quote
    from nsepy.live import get_option_chain

    NSEPY_AVAILABLE = True
except ImportError as e:
    NSEPY_AVAILABLE = False
    _IMPORT_ERROR = str(e)


def _check_nsepy() -> None:
    if not NSEPY_AVAILABLE:
        raise RuntimeError(
            f"nsepy is not installed or failed to import. Error: {_IMPORT_ERROR}. Run: pip install nsepy"
        )


def fetch_nifty_50_oi(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> pd.DataFrame:
    """
    Fetch Nifty 50 futures OI data.

    Returns DataFrame with columns: Date, Open, High, Low, Close, SettlePrice, Volume, OpenInterest, ChangeinOI
    """
    _check_nsepy()

    if start_date is None:
        start_date = datetime.now() - timedelta(days=30)
    if end_date is None:
        end_date = datetime.now()

    try:
        df = get_history(
            symbol="NIFTY",
            start=start_date,
            end=end_date,
            index=True,
            futures=True,
            expiry_date=None,
        )
        return df
    except Exception as e:
        print(f"[NSEpy] Error fetching Nifty OI: {e}")
        return pd.DataFrame()


def fetch_pcr_data(
    symbol: Optional[str] = None,
    days: int = 30,
) -> dict:
    """
    Calculate Put-Call Ratio for Nifty or a specific stock.

    Returns:
        {
            "pcr": float,          # overall PCR
            "pcr_series": {date: pcr},  # time series
            "total_ce_oi": int,
            "total_pe_oi": int,
        }
    """
    _check_nsepy()

    try:
        if symbol:
            # Stock-specific PCR from option chain
            oc = get_option_chain(symbol=symbol, expiry=None)
            # Aggregate by call/put
            total_ce = oc["CE"].sum()
            total_pe = oc["PE"].sum()
            pcr = total_pe / total_ce if total_ce > 0 else None
            return {
                "pcr": pcr,
                "total_ce_oi": int(total_ce),
                "total_pe_oi": int(total_pe),
            }
        else:
            # Nifty PCR from index options
            oc = get_option_chain(symbol="NIFTY", expiry=None)
            total_ce = oc["CE"].sum()
            total_pe = oc["PE"].sum()
            pcr = total_pe / total_ce if total_ce > 0 else None
            return {
                "pcr": pcr,
                "total_ce_oi": int(total_ce),
                "total_pe_oi": int(total_pe),
            }
    except Exception as e:
        print(f"[NSEpy] Error fetching PCR: {e}")
        # Fallback: try yfinance for basic option data? Not reliable for PCR.
        return {"pcr": None, "total_ce_oi": 0, "total_pe_oi": 0}


def fetch_fno_contracts(
    symbol: str,
    expiry: Optional[datetime] = None,
) -> pd.DataFrame:
    """
    Fetch option chain for a stock/index.

    Args:
        symbol: e.g., "RELIANCE", "NIFTY"
        expiry: Specific expiry date, or None for current expiry

    Returns:
        DataFrame with columns: Strike Price, CE_LastPrice, PE_LastPrice, CE_OI, PE_OI, etc.
    """
    _check_nsepy()

    try:
        oc = get_option_chain(symbol=symbol, expiry=expiry)
        return oc
    except Exception as e:
        print(f"[NSEpy] Error fetching option chain for {symbol}: {e}")
        return pd.DataFrame()


def get_quote(symbol: str) -> dict:
    """
    Get live quote for a stock from NSE.
    Returns dict with last price, volume, etc.
    """
    _check_nsepy()

    try:
        quote = get_quote(symbol)
        return quote
    except Exception as e:
        print(f"[NSEpy] Error fetching quote for {symbol}: {e}")
        return {}
