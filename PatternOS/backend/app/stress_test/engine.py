"""Stress test scenario engine.

Fetches historical prices for portfolio symbols and computes portfolio-level
drawdown, VaR, and beta metrics over a historical crisis window.
"""

from datetime import datetime, date
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session
import pandas as pd
import numpy as np

from app.db.models import PortfolioSnapshot, StressTestRun

# Predefined crisis scenarios
SCENARIOS = {
    "2008_crisis": {
        "start": "2008-09-01",
        "end": "2009-03-01",
        "name": "Global Financial Crisis",
    },
    "2020_covid": {
        "start": "2020-02-15",
        "end": "2020-04-30",
        "name": "COVID-19 Market Crash",
    },
    "2022_inflation": {
        "start": "2022-01-01",
        "end": "2022-06-30",
        "name": "Rate Hike Cycle",
    },
    "2023_bank_crisis": {
        "start": "2023-03-01",
        "end": "2023-05-01",
        "name": "US Regional Bank Crisis",
    },
    "nifty_2022": {
        "start": "2022-01-01",
        "end": "2022-12-31",
        "name": "Nifty 2022 Bear Market",
    },
}


def _get_scenario_dates(scenario_key: str) -> Tuple[date, date]:
    if scenario_key not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario_key}")
    s = SCENARIOS[scenario_key]
    return (
        datetime.strptime(s["start"], "%Y-%m-%d").date(),
        datetime.strptime(s["end"], "%Y-%m-%d").date(),
    )


def _fetch_portfolio_prices(
    positions_json: list,
    start: date,
    end: date,
) -> pd.DataFrame:
    """
    Fetch daily close prices for all symbols in the portfolio.
    Returns a DataFrame indexed by date with one column per symbol.
    Missing data filled with NaN.
    """
    from app.data.yfinance_client import (
        fetch_stock_prices,
    )  # imported here to avoid circular dependency

    price_dfs = {}
    for pos in positions_json:
        symbol = pos["symbol"]
        # Detect exchange from symbol suffix
        if symbol.endswith(".NS"):
            exchange = "NSE"
        elif symbol.endswith(".BO"):
            exchange = "BSE"
        else:
            # Default to NSE for Indian stocks without suffix
            exchange = "NSE"
        
        try:
            df = fetch_stock_prices(
                symbol, "1d", days=(end - start).days, exchange=exchange, use_cache=True
            )
            if not df.empty:
                # Reindex to include all trading days in range
                all_dates = pd.date_range(start, end, freq="B")
                df = df.reindex(all_dates, method="ffill")
                price_dfs[symbol] = df["Close"]
        except Exception:
            continue

    if not price_dfs:
        raise ValueError("No price data available for any symbol")

    combined = pd.DataFrame(price_dfs)
    return combined


def _compute_portfolio_value(
    prices: pd.DataFrame,
    positions_json: list,
    initial_value: Optional[float] = None,
) -> Tuple[pd.Series, float]:
    """
    Returns:
        portfolio_daily_value: Series indexed by date
        initial_value: total value at start date
    """
    qty_by_sym = {p["symbol"]: p["qty"] for p in positions_json}

    # Only include symbols we have prices for
    valid_symbols = [s for s in qty_by_sym if s in prices.columns]
    if not valid_symbols:
        raise ValueError("No valid symbols with price data")

    total_start = sum(qty_by_sym[s] * prices[s].iloc[0] for s in valid_symbols)
    initial = initial_value or total_start

    # Weighted daily portfolio value
    daily_value = pd.Series(index=prices.index, dtype=float)
    for dt in prices.index:
        day_total = sum(
            qty_by_sym[s] * prices[s].loc[dt]
            for s in valid_symbols
            if pd.notna(prices[s].loc[dt])
        )
        daily_value.loc[dt] = (day_total / total_start) * initial

    return daily_value, initial


def _compute_max_drawdown(series: pd.Series) -> float:
    """Maximum peak-to-trough drawdown as a positive percentage."""
    running_max = series.expanding().max()
    drawdown = (series - running_max) / running_max
    return abs(drawdown.min()) * 100


def _compute_var(returns: pd.Series, pct: float = 0.05) -> float:
    """Value at Risk: percentile of returns distribution."""
    return np.percentile(returns, pct * 100) * 100


def _portfolio_beta(
    prices: pd.DataFrame, positions_json: list, benchmark_symbol: str = "^NSEI"
) -> float:
    """
    Compute portfolio beta vs benchmark (NIFTY 50).
    Uses daily returns over the test period.
    """
    from app.data.yfinance_client import fetch_stock_prices  # avoid circular import

    try:
        # For benchmark symbols like ^NSEI, don't use exchange parameter
        # as they're Yahoo Finance symbols, not exchange-specific
        if benchmark_symbol.startswith("^"):
            # Yahoo Finance index symbol
            bm = fetch_stock_prices(
                benchmark_symbol,
                "1d",
                days=len(prices) + 10,
                exchange="",  # Empty exchange for Yahoo Finance symbols
                use_cache=True,
            )
        else:
            # Regular stock symbol
            bm = fetch_stock_prices(
                benchmark_symbol,
                "1d",
                days=len(prices) + 10,
                exchange="NSE",
                use_cache=True,
            )
        bm = bm.reindex(prices.index, method="ffill")
        bm_rets = bm["Close"].pct_change().dropna()
    except Exception:
        return np.nan

    # Portfolio daily return (value-weighted approximation)
    qty_by_sym = {p["symbol"]: p["qty"] for p in positions_json}
    valid_symbols = [s for s in qty_by_sym if s in prices.columns]
    port_vals = pd.DataFrame({s: prices[s] * qty_by_sym[s] for s in valid_symbols})
    port_total = port_vals.sum(axis=1)
    port_rets = port_total.pct_change().dropna()

    # Align
    aligned = pd.concat([port_rets, bm_rets], axis=1, join="inner").dropna()
    if aligned.empty:
        return np.nan

    cov = np.cov(aligned.iloc[:, 0], aligned.iloc[:, 1])[0, 1]
    var = np.var(aligned.iloc[:, 1])
    beta = cov / var if var != 0 else np.nan
    return beta


def run_stress_test_scenario(
    portfolio: PortfolioSnapshot,
    scenario_key: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = None,
) -> StressTestRun:
    """
    Main entry: run stress test given a scenario.

    Args:
        portfolio: PortfolioSnapshot ORM object
        scenario_key: one of SCENARIOS keys
        start_date / end_date: override scenario dates for custom runs
        db: SQLAlchemy session (for storing run)

    Returns:
        StressTestRun ORM object (unsaved — caller must commit)
    """
    # 1. Resolve date window
    if start_date and end_date:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    else:
        start, end = _get_scenario_dates(scenario_key)

    # 2. Fetch prices
    positions = portfolio.positions_json
    prices = _fetch_portfolio_prices(positions, start, end)

    # 3. Compute daily portfolio value
    daily_value, initial_val = _compute_portfolio_value(prices, positions)

    # 4. Final value
    final_val = float(daily_value.iloc[-1])

    # 5. Max drawdown
    mdd = _compute_max_drawdown(daily_value)

    # 6. VaR 95%
    daily_rets = daily_value.pct_change().dropna()
    var = _compute_var(daily_rets, 0.05)

    # 7. Beta vs NIFTY
    beta = _portfolio_beta(prices, positions)

    # 8. Per-symbol P&L breakdown
    breakdown = {}
    qty_by_sym = {p["symbol"]: p["qty"] for p in positions}
    for sym in qty_by_sym:
        if sym in prices.columns:
            start_p = prices[sym].iloc[0]
            end_p = prices[sym].iloc[-1]
            qty = qty_by_sym[sym]
            pnl = (end_p - start_p) * qty
            ret_pct = ((end_p - start_p) / start_p) * 100 if start_p else 0
            breakdown[sym] = {
                "qty": qty,
                "start_price": round(float(start_p), 2),
                "end_price": round(float(end_p), 2),
                "pnl": round(pnl, 2),
                "return_pct": round(ret_pct, 2),
            }

    # 9. Build ORM object
    run = StressTestRun(
        portfolio_id=UUID(portfolio.id)
        if isinstance(portfolio.id, str)
        else portfolio.id,
        scenario=scenario_key,
        start_date=start,
        end_date=end,
        initial_value=initial_val,
        final_value=final_val,
        max_drawdown_pct=mdd,
        var_95=var,
        beta_weighted=beta,
        results_json=breakdown,
        completed_at=datetime.utcnow(),
    )
    return run
