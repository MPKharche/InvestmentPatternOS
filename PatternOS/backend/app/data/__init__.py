"""Data providers — yfinance, NSEpy, AMFI."""

from .yfinance_client import (
    fetch_stock_prices,
    fetch_stock_info,
    fetch_index_prices,
    get_stock_fundamentals,
)
from .nsepy_client import (
    fetch_nifty_50_oi,
    fetch_pcr_data,
    fetch_fno_contracts,
)

__all__ = [
    "fetch_stock_prices",
    "fetch_stock_info",
    "fetch_index_prices",
    "get_stock_fundamentals",
    "fetch_nifty_50_oi",
    "fetch_pcr_data",
    "fetch_fno_contracts",
]
