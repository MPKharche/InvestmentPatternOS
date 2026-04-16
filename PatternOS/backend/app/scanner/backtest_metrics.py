"""Forward returns and outcome labels for backtests (multi-horizon)."""
from __future__ import annotations

from typing import Any

import pandas as pd


def forward_horizon_returns_pct(df: pd.DataFrame, i: int) -> dict[str, float | None]:
    """Returns % change from entry close at bar i to close at i+h for standard horizons."""
    n = len(df)
    entry = float(df["Close"].iloc[i])

    def pct(j: int) -> float | None:
        if i + j < n:
            return round((float(df["Close"].iloc[i + j]) / entry - 1) * 100, 4)
        return None

    return {
        "ret_5d": pct(5),
        "ret_10d": pct(10),
        "ret_20d": pct(20),
        "ret_21d": pct(21),
        "ret_63d": pct(63),
        "ret_126d": pct(126),
    }


def max_gain_loss_20d(df: pd.DataFrame, i: int) -> tuple[float | None, float | None]:
    n = len(df)
    entry = float(df["Close"].iloc[i])
    if i + 1 >= n:
        return None, None
    window = df["Close"].iloc[i + 1 : min(n, i + 21)]
    if window.empty:
        return None, None
    max_g = round((float(window.max()) / entry - 1) * 100, 2)
    max_l = round((float(window.min()) / entry - 1) * 100, 2)
    return max_g, max_l


def outcome_from_rulebook(direction: str, rets: dict[str, float | None], rulebook: dict[str, Any]) -> str:
    """
    Classify backtest outcome using configurable horizon (default 21d) and thresholds.
    Bearish pattern: success if return at horizon is sufficiently negative.
    """
    bc = rulebook.get("backtest") or {}
    horizon = int(bc.get("outcome_horizon_days", 21))
    key = {5: "ret_5d", 10: "ret_10d", 20: "ret_20d", 21: "ret_21d", 63: "ret_63d", 126: "ret_126d"}.get(
        horizon, "ret_21d"
    )
    ret = rets.get(key)
    if ret is None:
        ret = rets.get("ret_10d")
    if ret is None:
        return "pending"

    if direction == "bearish":
        success_below = float(bc.get("bearish_success_if_ret_below_pct", -2.0))
        fail_above = float(bc.get("bearish_failure_if_ret_above_pct", 2.5))
        if ret <= success_below:
            return "success"
        if ret >= fail_above:
            return "failure"
        return "neutral"

    success_above = float(bc.get("bullish_success_if_ret_above_pct", 2.0))
    fail_below = float(bc.get("bullish_failure_if_ret_below_pct", -2.5))
    if ret >= success_above:
        return "success"
    if ret <= fail_below:
        return "failure"
    return "neutral"


def forward_returns_for_live_bar(df: pd.DataFrame, i: int) -> dict[str, Any]:
    """Same horizons as backtest; nulls when not enough future bars (typical on latest bar)."""
    r = forward_horizon_returns_pct(df, i)
    idx = df.index[i]
    bar_date = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
    return {
        "entry_bar_date": bar_date,
        "entry_close": round(float(df["Close"].iloc[i]), 4),
        "horizons_trading_days": {"1w": 5, "1m": 21, "3m": 63, "6m": 126},
        "pct": {
            "1w_5d": r.get("ret_5d"),
            "1m_21d": r.get("ret_21d"),
            "3m_63d": r.get("ret_63d"),
            "6m_126d": r.get("ret_126d"),
        },
    }
