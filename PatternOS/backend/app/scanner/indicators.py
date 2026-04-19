"""
Technical indicator engine using the `ta` library.
Adds EMA, SMA, Bollinger Bands, RSI, MACD, ATR, Stochastic, ADX, OBV to a OHLCV DataFrame.
Returns serialisable dicts suitable for the frontend chart overlay.
"""

from __future__ import annotations

import math
import pandas as pd
from typing import Any

from app.config import get_settings

from ta.trend import (
    EMAIndicator,
    SMAIndicator,
    MACD as MACDIndicator,
    ADXIndicator,
)
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.volume import OnBalanceVolumeIndicator

settings = get_settings()


def _resolve_engine(engine: str | None) -> str:
    e = (engine or settings.INDICATOR_ENGINE or "auto").strip().lower()
    if e not in ("auto", "ta", "talib"):
        return "auto"
    if e == "auto":
        try:
            import talib  # noqa: F401

            return "talib"
        except Exception:
            return "ta"
    return e


# ── Core computation ──────────────────────────────────────────────────────────


def _compute_indicators_ta(
    df: pd.DataFrame,
    *,
    rsi_period: int = 14,
    sma_periods: tuple[int, ...] = (20, 50, 200),
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    bb_window: int = 20,
    bb_std: float = 2.0,
    atr_period: int = 14,
) -> pd.DataFrame:
    """
    Appends indicator columns to a copy of *df*.
    Expects columns: Open, High, Low, Close, Volume (title-case).
    """
    df = df.copy()
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    vol = df["Volume"]

    # Trend — SMAs
    for p in sma_periods:
        df[f"sma_{p}"] = SMAIndicator(close, window=p, fillna=False).sma_indicator()
    df["ema_20"] = EMAIndicator(close, window=20, fillna=False).ema_indicator()
    df["ema_50"] = EMAIndicator(close, window=50, fillna=False).ema_indicator()
    df["ema_200"] = EMAIndicator(close, window=200, fillna=False).ema_indicator()

    # Bollinger Bands
    bb = BollingerBands(close, window=bb_window, window_dev=bb_std, fillna=False)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_mid"] = bb.bollinger_mavg()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_width"] = bb.bollinger_wband()

    # RSI
    try:
        df["rsi"] = RSIIndicator(close, window=rsi_period, fillna=False).rsi()
    except Exception:
        df["rsi"] = pd.NA

    # MACD
    try:
        macd_obj = MACDIndicator(
            close,
            window_fast=macd_fast,
            window_slow=macd_slow,
            window_sign=macd_signal,
            fillna=False,
        )
        df["macd"] = macd_obj.macd()
        df["macd_signal"] = macd_obj.macd_signal()
        df["macd_hist"] = macd_obj.macd_diff()
    except Exception:
        df["macd"] = pd.NA
        df["macd_signal"] = pd.NA
        df["macd_hist"] = pd.NA

    # ATR
    try:
        df["atr"] = AverageTrueRange(
            high, low, close, window=atr_period, fillna=False
        ).average_true_range()
    except Exception:
        df["atr"] = pd.NA

    # Stochastic (14, 3)
    try:
        stoch = StochasticOscillator(
            high, low, close, window=14, smooth_window=3, fillna=False
        )
        df["stoch_k"] = stoch.stoch()
        df["stoch_d"] = stoch.stoch_signal()
    except Exception:
        df["stoch_k"] = pd.NA
        df["stoch_d"] = pd.NA

    # ADX-14
    try:
        adx = ADXIndicator(high, low, close, window=14, fillna=False)
        df["adx"] = adx.adx()
        df["adx_di_pos"] = adx.adx_pos()
        df["adx_di_neg"] = adx.adx_neg()
    except Exception:
        df["adx"] = pd.NA
        df["adx_di_pos"] = pd.NA
        df["adx_di_neg"] = pd.NA

    # OBV
    try:
        df["obv"] = OnBalanceVolumeIndicator(
            close, vol, fillna=False
        ).on_balance_volume()
    except Exception:
        df["obv"] = pd.NA

    return df


# ── Serialise for API ─────────────────────────────────────────────────────────


def _compute_indicators_talib(df: pd.DataFrame) -> pd.DataFrame:
    """
    TA-Lib powered indicator computation.
    Falls back to `ta` if TA-Lib isn't available.
    """
    try:
        import numpy as np
        import talib
    except Exception:
        return _compute_indicators_ta(df)

    df = df.copy()
    close = df["Close"].astype(float).to_numpy()
    high = df["High"].astype(float).to_numpy()
    low = df["Low"].astype(float).to_numpy()
    vol = (
        df["Volume"].astype(float).to_numpy()
        if "Volume" in df.columns
        else np.zeros_like(close)
    )

    df["ema_20"] = talib.EMA(close, timeperiod=20)
    df["ema_50"] = talib.EMA(close, timeperiod=50)
    df["ema_200"] = talib.EMA(close, timeperiod=200)
    df["sma_20"] = talib.SMA(close, timeperiod=20)

    upper, mid, lower = talib.BBANDS(
        close, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0
    )
    df["bb_upper"] = upper
    df["bb_mid"] = mid
    df["bb_lower"] = lower
    df["bb_width"] = (upper - lower) / mid * 100.0

    df["rsi"] = talib.RSI(close, timeperiod=14)

    macd, macdsignal, macdhist = talib.MACD(
        close, fastperiod=12, slowperiod=26, signalperiod=9
    )
    df["macd"] = macd
    df["macd_signal"] = macdsignal
    df["macd_hist"] = macdhist

    df["atr"] = talib.ATR(high, low, close, timeperiod=14)

    slowk, slowd = talib.STOCH(
        high,
        low,
        close,
        fastk_period=14,
        slowk_period=3,
        slowk_matype=0,
        slowd_period=3,
        slowd_matype=0,
    )
    df["stoch_k"] = slowk
    df["stoch_d"] = slowd

    df["adx"] = talib.ADX(high, low, close, timeperiod=14)
    df["adx_di_pos"] = talib.PLUS_DI(high, low, close, timeperiod=14)
    df["adx_di_neg"] = talib.MINUS_DI(high, low, close, timeperiod=14)

    df["obv"] = talib.OBV(close, vol)

    return df


def compute_indicators(
    df: pd.DataFrame,
    *,
    engine: str | None = None,
    rsi_period: int = 14,
    sma_periods: tuple[int, ...] = (20, 50, 200),
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    bb_window: int = 20,
    bb_std: float = 2.0,
    atr_period: int = 14,
) -> pd.DataFrame:
    """
    Appends indicator columns to a copy of *df*.
    Expects columns: Open, High, Low, Close, Volume (title-case).

    All parameters are optional with sensible defaults. Use them to customise
    indicator calculations (e.g. playground or screener variations).
    """
    resolved = _resolve_engine(engine)
    if resolved == "talib":
        # TODO: extend _compute_indicators_talib similarly
        return _compute_indicators_talib(df)
    return _compute_indicators_ta(
        df,
        rsi_period=rsi_period,
        sma_periods=sma_periods,
        macd_fast=macd_fast,
        macd_slow=macd_slow,
        macd_signal=macd_signal,
        bb_window=bb_window,
        bb_std=bb_std,
        atr_period=atr_period,
    )


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
        "ema_20",
        "ema_50",
        "ema_200",
        "sma_20",
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
        "ema_20",
        "ema_50",
        "ema_200",
        "sma_20",
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
    ]
    return {k: _v(last.get(k)) for k in keys}
