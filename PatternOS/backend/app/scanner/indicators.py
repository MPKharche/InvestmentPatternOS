"""
Technical indicator engine using the `ta` library.
Adds EMA, SMA, Bollinger Bands, RSI, MACD, ATR, Stochastic, ADX, OBV to a OHLCV DataFrame.
Returns serialisable dicts suitable for the frontend chart overlay.
"""
from __future__ import annotations

import math
import pandas as pd
from typing import Any

from ta.trend import (
    EMAIndicator,
    SMAIndicator,
    MACD as MACDIndicator,
    ADXIndicator,
)
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.volume import OnBalanceVolumeIndicator


# ── Core computation ──────────────────────────────────────────────────────────

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Appends indicator columns to a copy of *df*.
    Expects columns: Open, High, Low, Close, Volume (title-case).
    """
    df = df.copy()
    close = df["Close"]
    high  = df["High"]
    low   = df["Low"]
    vol   = df["Volume"]

    # Trend
    df["ema_20"]  = EMAIndicator(close, window=20,  fillna=False).ema_indicator()
    df["ema_50"]  = EMAIndicator(close, window=50,  fillna=False).ema_indicator()
    df["ema_200"] = EMAIndicator(close, window=200, fillna=False).ema_indicator()
    df["sma_20"]  = SMAIndicator(close, window=20,  fillna=False).sma_indicator()

    # Bollinger Bands (20, 2σ)
    bb = BollingerBands(close, window=20, window_dev=2, fillna=False)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_mid"]   = bb.bollinger_mavg()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_width"] = bb.bollinger_wband()   # (upper-lower)/mid * 100

    # RSI-14
    df["rsi"] = RSIIndicator(close, window=14, fillna=False).rsi()

    # MACD (12, 26, 9)
    macd_obj = MACDIndicator(close, window_fast=12, window_slow=26, window_sign=9, fillna=False)
    df["macd"]        = macd_obj.macd()
    df["macd_signal"] = macd_obj.macd_signal()
    df["macd_hist"]   = macd_obj.macd_diff()

    # ATR-14
    df["atr"] = AverageTrueRange(high, low, close, window=14, fillna=False).average_true_range()

    # Stochastic (14, 3)
    stoch = StochasticOscillator(high, low, close, window=14, smooth_window=3, fillna=False)
    df["stoch_k"] = stoch.stoch()
    df["stoch_d"] = stoch.stoch_signal()

    # ADX-14
    adx = ADXIndicator(high, low, close, window=14, fillna=False)
    df["adx"]    = adx.adx()
    df["adx_di_pos"] = adx.adx_pos()
    df["adx_di_neg"] = adx.adx_neg()

    # OBV
    df["obv"] = OnBalanceVolumeIndicator(close, vol, fillna=False).on_balance_volume()

    return df


# ── Serialise for API ─────────────────────────────────────────────────────────

def _v(x: Any) -> float | None:
    """Return a JSON-safe float or None."""
    if x is None:
        return None
    try:
        f = float(x)
        return None if math.isnan(f) or math.isinf(f) else round(f, 4)
    except (TypeError, ValueError):
        return None


def indicators_to_records(df: pd.DataFrame) -> list[dict]:
    """
    Convert indicator DataFrame to a list of per-bar dicts.
    Only includes the columns added by compute_indicators().
    """
    ind_cols = [
        "ema_20", "ema_50", "ema_200", "sma_20",
        "bb_upper", "bb_mid", "bb_lower", "bb_width",
        "rsi", "macd", "macd_signal", "macd_hist",
        "atr", "stoch_k", "stoch_d",
        "adx", "adx_di_pos", "adx_di_neg",
        "obv",
    ]
    cols = [c for c in ind_cols if c in df.columns]

    # Build date index
    if hasattr(df.index, "strftime"):
        dates = df.index.strftime("%Y-%m-%d").tolist()
    else:
        dates = [str(i)[:10] for i in df.index]

    records: list[dict] = []
    for i, date in enumerate(dates):
        rec: dict = {"time": date}
        for c in cols:
            rec[c] = _v(df[c].iloc[i])
        records.append(rec)
    return records


# ── Latest snapshot (for evaluator) ──────────────────────────────────────────

def latest_indicators(df: pd.DataFrame) -> dict:
    """
    Returns a flat dict of the most-recent bar's indicator values.
    Useful for the evaluator to make quick decisions.
    """
    idf = compute_indicators(df)
    last = idf.iloc[-1]
    keys = [
        "ema_20", "ema_50", "ema_200", "sma_20",
        "bb_upper", "bb_mid", "bb_lower", "bb_width",
        "rsi", "macd", "macd_signal", "macd_hist",
        "atr", "stoch_k", "stoch_d",
        "adx", "adx_di_pos", "adx_di_neg",
    ]
    return {k: _v(last.get(k)) for k in keys}
