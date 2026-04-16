"""
Executable pattern criteria (MACD/RSI divergence, simple gates).

Used by backtests and — when `is_criteria_only_scan` — by the live scanner evaluator
so divergence patterns are not blocked by consolidation/volume/breakout rubrics.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from scipy.signal import argrelextrema


def _div_params(rulebook: dict | None) -> dict:
    rb = rulebook or {}
    d = rb.get("divergence") or rb.get("conditions", {}).get("divergence") or {}
    return {
        "lookback_bars": int(d.get("lookback_bars", d.get("window", 65))),
        "swing_order": int(d.get("swing_order", 5)),
        "min_swing_separation": int(d.get("min_swing_separation", 8)),
    }


def detect_macd_divergence_bearish(
    df: pd.DataFrame,
    i: int,
    rulebook: dict | None = None,
) -> bool:
    """
    Bearish: price makes a higher high on the last two swing peaks, MACD makes a lower high.
    Uses aligned swing highs on price (same bars for MACD comparison).
    """
    p = _div_params(rulebook)
    window = p["lookback_bars"]
    order = p["swing_order"]
    min_sep = p["min_swing_separation"]

    if i < window or "macd" not in df.columns:
        return False
    seg = df.iloc[i - window : i + 1]
    close = seg["Close"].values.astype(float)
    macd = seg["macd"].ffill().fillna(0).values.astype(float)

    peaks = argrelextrema(close, np.greater, order=order)[0]
    if len(peaks) < 2:
        return False
    p1, p2 = int(peaks[-2]), int(peaks[-1])
    if p2 - p1 < min_sep:
        return False

    price_hh = close[p2] > close[p1] * 1.001
    macd_lh = macd[p2] < macd[p1] * 0.999
    if not (price_hh and macd_lh):
        return False

    d = (rulebook or {}).get("divergence") or {}
    if d.get("require_close_above_ema50") and "ema_50" in df.columns:
        ema = df["ema_50"].iloc[i]
        if pd.isna(ema) or float(df["Close"].iloc[i]) <= float(ema):
            return False
    if d.get("require_macd_histogram_negative") and "macd_hist" in df.columns:
        if float(df["macd_hist"].iloc[i]) >= 0:
            return False
    if d.get("require_histogram_more_negative_than_3_bars_ago") and "macd_hist" in df.columns and i >= 3:
        if not (float(df["macd_hist"].iloc[i]) < float(df["macd_hist"].iloc[i - 3])):
            return False
    return True


def detect_macd_divergence_bullish(
    df: pd.DataFrame,
    i: int,
    rulebook: dict | None = None,
) -> bool:
    """Bullish: lower low in price, higher low in MACD at last two swing troughs."""
    p = _div_params(rulebook)
    window = p["lookback_bars"]
    order = p["swing_order"]
    min_sep = p["min_swing_separation"]

    if i < window or "macd" not in df.columns:
        return False
    seg = df.iloc[i - window : i + 1]
    close = seg["Close"].values.astype(float)
    macd = seg["macd"].ffill().fillna(0).values.astype(float)

    troughs = argrelextrema(close, np.less, order=order)[0]
    if len(troughs) < 2:
        return False
    t1, t2 = int(troughs[-2]), int(troughs[-1])
    if t2 - t1 < min_sep:
        return False

    price_ll = close[t2] < close[t1] * 0.999
    macd_hl = macd[t2] > macd[t1] * 1.001
    return bool(price_ll and macd_hl)


def detect_rsi_divergence_bearish(df: pd.DataFrame, i: int, rulebook: dict | None = None) -> bool:
    p = _div_params(rulebook)
    window = p["lookback_bars"]
    order = p["swing_order"]
    min_sep = p["min_swing_separation"]
    if i < window or "rsi" not in df.columns:
        return False
    seg = df.iloc[i - window : i + 1]
    prices = seg["Close"].values.astype(float)
    rsis = seg["rsi"].ffill().fillna(50).values.astype(float)
    peaks = argrelextrema(prices, np.greater, order=order)[0]
    if len(peaks) < 2:
        return False
    p1, p2 = int(peaks[-2]), int(peaks[-1])
    if p2 - p1 < min_sep:
        return False
    return bool(prices[p2] > prices[p1] * 1.001 and rsis[p2] < rsis[p1] * 0.999)


def detect_rsi_divergence_bullish(df: pd.DataFrame, i: int, rulebook: dict | None = None) -> bool:
    p = _div_params(rulebook)
    window = p["lookback_bars"]
    order = p["swing_order"]
    min_sep = p["min_swing_separation"]
    if i < window or "rsi" not in df.columns:
        return False
    seg = df.iloc[i - window : i + 1]
    prices = seg["Close"].values.astype(float)
    rsis = seg["rsi"].ffill().fillna(50).values.astype(float)
    troughs = argrelextrema(prices, np.less, order=order)[0]
    if len(troughs) < 2:
        return False
    t1, t2 = int(troughs[-2]), int(troughs[-1])
    if t2 - t1 < min_sep:
        return False
    return bool(prices[t2] < prices[t1] * 0.999 and rsis[t2] > rsis[t1] * 1.001)


SIMPLE_CHECKS = {
    "rsi_overbought": lambda df, i: df["rsi"].iloc[i] > 70 if "rsi" in df.columns else False,
    "rsi_oversold": lambda df, i: df["rsi"].iloc[i] < 30 if "rsi" in df.columns else False,
    "price_above_ema200": lambda df, i: df["Close"].iloc[i] > df["ema_200"].iloc[i]
    if "ema_200" in df.columns and not pd.isna(df["ema_200"].iloc[i])
    else False,
    "price_below_ema200": lambda df, i: df["Close"].iloc[i] < df["ema_200"].iloc[i]
    if "ema_200" in df.columns and not pd.isna(df["ema_200"].iloc[i])
    else False,
    "macd_negative": lambda df, i: df["macd"].iloc[i] < 0 if "macd" in df.columns else False,
    "macd_positive": lambda df, i: df["macd"].iloc[i] > 0 if "macd" in df.columns else False,
    "adx_trending": lambda df, i: df["adx"].iloc[i] > 25
    if "adx" in df.columns and not pd.isna(df["adx"].iloc[i])
    else False,
    "ema_crossover_bearish": lambda df, i: (
        i > 0
        and "ema_20" in df.columns
        and "ema_50" in df.columns
        and df["ema_20"].iloc[i] < df["ema_50"].iloc[i]
        and df["ema_20"].iloc[i - 1] >= df["ema_50"].iloc[i - 1]
    ),
    "ema_crossover_bullish": lambda df, i: (
        i > 0
        and "ema_20" in df.columns
        and "ema_50" in df.columns
        and df["ema_20"].iloc[i] > df["ema_50"].iloc[i]
        and df["ema_20"].iloc[i - 1] <= df["ema_50"].iloc[i - 1]
    ),
}

CONDITION_CHECKS = {
    "macd_divergence_bearish": detect_macd_divergence_bearish,
    "macd_divergence_bullish": detect_macd_divergence_bullish,
    "rsi_divergence_bearish": detect_rsi_divergence_bearish,
    "rsi_divergence_bullish": detect_rsi_divergence_bullish,
}

CONDITION_CHECK_KEYS = frozenset(CONDITION_CHECKS.keys())
SIMPLE_CHECK_KEYS = frozenset(SIMPLE_CHECKS.keys())


def run_criteria_at_index(
    idf: pd.DataFrame,
    i: int,
    criteria: list,
    rulebook: dict | None = None,
) -> bool:
    """AND of all criteria at bar i (same semantics as backtest inner loop)."""
    if not criteria:
        return False
    for crit in criteria:
        ctype = crit if isinstance(crit, str) else crit.get("type", "")
        if ctype in CONDITION_CHECKS:
            if not CONDITION_CHECKS[ctype](idf, i, rulebook=rulebook):
                return False
        elif ctype in SIMPLE_CHECKS:
            try:
                if not SIMPLE_CHECKS[ctype](idf, i):
                    return False
            except Exception:
                return False
        else:
            return False
    return True

