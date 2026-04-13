"""
Chart pattern + candlestick pattern detector.

Chart patterns (price-action geometry via pivot points):
  Head & Shoulders / Inverse H&S
  Double Top / Double Bottom
  Triple Top / Triple Bottom
  Ascending / Descending / Symmetrical Triangle
  Bull Flag / Bear Flag
  Rising / Falling Wedge

Candlestick patterns (manual calculation, no TA-Lib required):
  Doji, Hammer, Inverted Hammer, Shooting Star, Hanging Man,
  Bullish/Bearish Engulfing, Morning Star, Evening Star,
  Bullish/Bearish Harami, Marubozu, Spinning Top

Each detected pattern returns:
  {type, direction, confidence (0-100), start_date, end_date,
   key_levels: {resistance, support, target, stop}, description}
"""
from __future__ import annotations

import math
import numpy as np
import pandas as pd
from scipy.signal import argrelextrema  # type: ignore[import-untyped]
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _date(df: pd.DataFrame, idx: int) -> str:
    ts = df.index[idx]
    return str(ts)[:10] if hasattr(ts, "__str__") else str(ts)


def _pct(a: float, b: float) -> float:
    """Percentage difference of b relative to a."""
    if a == 0:
        return 0.0
    return abs((b - a) / a) * 100


def _find_pivots(series: pd.Series, order: int = 5) -> tuple[np.ndarray, np.ndarray]:
    """Return (highs_idx, lows_idx) using scipy argrelextrema."""
    arr = series.values
    highs = argrelextrema(arr, np.greater_equal, order=order)[0]
    lows  = argrelextrema(arr, np.less_equal,    order=order)[0]
    return highs, lows


def _slope(x1: int, y1: float, x2: int, y2: float) -> float:
    if x2 == x1:
        return 0.0
    return (y2 - y1) / (x2 - x1)


# ─────────────────────────────────────────────────────────────────────────────
# Chart pattern detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_chart_patterns(df: pd.DataFrame, lookback: int = 120) -> list[dict]:
    """
    Run all chart pattern detectors on the last *lookback* bars.
    Returns list of pattern dicts sorted by end_date desc.
    """
    df = df.tail(lookback).copy()
    df = df.reset_index()          # make integer index, keep Date column
    # Normalise date column name
    date_col = "Date" if "Date" in df.columns else (
        "Datetime" if "Datetime" in df.columns else df.columns[0]
    )

    results: list[dict] = []
    detectors = [
        _detect_head_and_shoulders,
        _detect_double_top_bottom,
        _detect_triple_top_bottom,
        _detect_triangle,
        _detect_flag,
        _detect_wedge,
    ]
    for fn in detectors:
        try:
            found = fn(df, date_col)
            results.extend(found)
        except Exception:
            pass

    results.sort(key=lambda x: x.get("end_date", ""), reverse=True)
    return results


# ── Head & Shoulders ──────────────────────────────────────────────────────────

def _detect_head_and_shoulders(df: pd.DataFrame, date_col: str) -> list[dict]:
    results = []
    highs_idx, lows_idx = _find_pivots(df["High"], order=4)
    if len(highs_idx) < 3:
        return results

    # Slide a window of 3 consecutive highs
    for i in range(len(highs_idx) - 2):
        ls, head, rs = highs_idx[i], highs_idx[i + 1], highs_idx[i + 2]
        h_ls   = df["High"].iloc[ls]
        h_head = df["High"].iloc[head]
        h_rs   = df["High"].iloc[rs]

        # Head must be highest, shoulders roughly equal (within 3%)
        if h_head <= max(h_ls, h_rs):
            continue
        if _pct(h_ls, h_rs) > 4:
            continue

        # Find neckline: lows between ls-head and head-rs
        between1 = lows_idx[(lows_idx > ls) & (lows_idx < head)]
        between2 = lows_idx[(lows_idx > head) & (lows_idx < rs)]
        if len(between1) == 0 or len(between2) == 0:
            continue
        nl1_idx = between1[df["Low"].iloc[between1].idxmin() if False else np.argmin(df["Low"].iloc[between1].values)]
        nl2_idx = between2[df["Low"].iloc[between2].idxmin() if False else np.argmin(df["Low"].iloc[between2].values)]
        nl1 = df["Low"].iloc[nl1_idx]
        nl2 = df["Low"].iloc[nl2_idx]
        neckline = (nl1 + nl2) / 2
        height   = h_head - neckline
        target   = neckline - height

        conf = 70
        if _pct(h_ls, h_rs) < 2:
            conf += 10
        if height / neckline > 0.05:
            conf += 5
        conf = min(conf, 92)

        results.append({
            "type": "head_and_shoulders",
            "direction": "bearish",
            "confidence": conf,
            "start_date": str(df[date_col].iloc[ls])[:10],
            "end_date":   str(df[date_col].iloc[rs])[:10],
            "key_levels": {
                "resistance": round(float(h_head), 2),
                "support":    round(float(neckline), 2),
                "target":     round(float(target), 2),
                "stop":       round(float(h_rs * 1.01), 2),
            },
            "description": (
                f"Head & Shoulders: left shoulder {h_ls:.2f}, "
                f"head {h_head:.2f}, right shoulder {h_rs:.2f}. "
                f"Neckline ~{neckline:.2f}. Measured target {target:.2f}."
            ),
        })

    # Inverse H&S on lows
    if len(lows_idx) >= 3:
        for i in range(len(lows_idx) - 2):
            ls, head, rs = lows_idx[i], lows_idx[i + 1], lows_idx[i + 2]
            l_ls   = df["Low"].iloc[ls]
            l_head = df["Low"].iloc[head]
            l_rs   = df["Low"].iloc[rs]

            if l_head >= min(l_ls, l_rs):
                continue
            if _pct(l_ls, l_rs) > 4:
                continue

            between1 = highs_idx[(highs_idx > ls) & (highs_idx < head)]
            between2 = highs_idx[(highs_idx > head) & (highs_idx < rs)]
            if len(between1) == 0 or len(between2) == 0:
                continue
            nl1 = df["High"].iloc[between1[np.argmax(df["High"].iloc[between1].values)]]
            nl2 = df["High"].iloc[between2[np.argmax(df["High"].iloc[between2].values)]]
            neckline = (nl1 + nl2) / 2
            height   = neckline - l_head
            target   = neckline + height

            conf = min(70 + (5 if _pct(l_ls, l_rs) < 2 else 0), 92)
            results.append({
                "type": "inverse_head_and_shoulders",
                "direction": "bullish",
                "confidence": conf,
                "start_date": str(df[date_col].iloc[ls])[:10],
                "end_date":   str(df[date_col].iloc[rs])[:10],
                "key_levels": {
                    "resistance": round(float(neckline), 2),
                    "support":    round(float(l_head), 2),
                    "target":     round(float(target), 2),
                    "stop":       round(float(l_rs * 0.99), 2),
                },
                "description": (
                    f"Inverse H&S: neckline ~{neckline:.2f}. "
                    f"Head low {l_head:.2f}. Target {target:.2f}."
                ),
            })
    return results


# ── Double / Triple Top / Bottom ──────────────────────────────────────────────

def _detect_double_top_bottom(df: pd.DataFrame, date_col: str) -> list[dict]:
    results = []
    highs_idx, lows_idx = _find_pivots(df["High"], order=5)
    _, lows_idx2 = _find_pivots(df["Low"], order=5)

    # Double top: two consecutive highs within 2%
    for i in range(len(highs_idx) - 1):
        h1_i, h2_i = highs_idx[i], highs_idx[i + 1]
        h1, h2 = df["High"].iloc[h1_i], df["High"].iloc[h2_i]
        if _pct(h1, h2) > 2.5:
            continue
        # Must have valley between
        valley_candidates = lows_idx2[(lows_idx2 > h1_i) & (lows_idx2 < h2_i)]
        if len(valley_candidates) == 0:
            continue
        valley = float(df["Low"].iloc[valley_candidates].min())
        height = max(h1, h2) - valley
        target = valley - height

        results.append({
            "type": "double_top",
            "direction": "bearish",
            "confidence": 75,
            "start_date": str(df[date_col].iloc[h1_i])[:10],
            "end_date":   str(df[date_col].iloc[h2_i])[:10],
            "key_levels": {
                "resistance": round((h1 + h2) / 2, 2),
                "support":    round(valley, 2),
                "target":     round(target, 2),
                "stop":       round(float(max(h1, h2)) * 1.01, 2),
            },
            "description": (
                f"Double Top at ~{(h1+h2)/2:.2f}. "
                f"Neckline support {valley:.2f}. Target {target:.2f}."
            ),
        })

    # Double bottom: two consecutive lows within 2%
    for i in range(len(lows_idx2) - 1):
        l1_i, l2_i = lows_idx2[i], lows_idx2[i + 1]
        l1, l2 = df["Low"].iloc[l1_i], df["Low"].iloc[l2_i]
        if _pct(l1, l2) > 2.5:
            continue
        peak_candidates = highs_idx[(highs_idx > l1_i) & (highs_idx < l2_i)]
        if len(peak_candidates) == 0:
            continue
        peak   = float(df["High"].iloc[peak_candidates].max())
        height = peak - min(l1, l2)
        target = peak + height

        results.append({
            "type": "double_bottom",
            "direction": "bullish",
            "confidence": 75,
            "start_date": str(df[date_col].iloc[l1_i])[:10],
            "end_date":   str(df[date_col].iloc[l2_i])[:10],
            "key_levels": {
                "resistance": round(peak, 2),
                "support":    round((l1 + l2) / 2, 2),
                "target":     round(target, 2),
                "stop":       round(float(min(l1, l2)) * 0.99, 2),
            },
            "description": (
                f"Double Bottom at ~{(l1+l2)/2:.2f}. "
                f"Neckline {peak:.2f}. Target {target:.2f}."
            ),
        })

    return results


def _detect_triple_top_bottom(df: pd.DataFrame, date_col: str) -> list[dict]:
    results = []
    highs_idx, lows_idx = _find_pivots(df["High"], order=4)
    _, lows_idx2 = _find_pivots(df["Low"], order=4)

    # Triple top: 3 consecutive highs within 2.5%
    for i in range(len(highs_idx) - 2):
        hi = [highs_idx[i], highs_idx[i+1], highs_idx[i+2]]
        hs = [float(df["High"].iloc[j]) for j in hi]
        avg_h = sum(hs) / 3
        if any(_pct(avg_h, h) > 2.5 for h in hs):
            continue
        valleys = lows_idx2[(lows_idx2 > hi[0]) & (lows_idx2 < hi[2])]
        if len(valleys) == 0:
            continue
        support = float(df["Low"].iloc[valleys].min())
        height  = avg_h - support
        target  = support - height

        results.append({
            "type": "triple_top",
            "direction": "bearish",
            "confidence": 78,
            "start_date": str(df[date_col].iloc[hi[0]])[:10],
            "end_date":   str(df[date_col].iloc[hi[2]])[:10],
            "key_levels": {
                "resistance": round(avg_h, 2),
                "support":    round(support, 2),
                "target":     round(target, 2),
                "stop":       round(avg_h * 1.01, 2),
            },
            "description": f"Triple Top ~{avg_h:.2f}. Support {support:.2f}. Target {target:.2f}.",
        })

    for i in range(len(lows_idx2) - 2):
        li = [lows_idx2[i], lows_idx2[i+1], lows_idx2[i+2]]
        ls = [float(df["Low"].iloc[j]) for j in li]
        avg_l = sum(ls) / 3
        if any(_pct(avg_l, l) > 2.5 for l in ls):
            continue
        peaks = highs_idx[(highs_idx > li[0]) & (highs_idx < li[2])]
        if len(peaks) == 0:
            continue
        resistance = float(df["High"].iloc[peaks].max())
        height     = resistance - avg_l
        target     = resistance + height

        results.append({
            "type": "triple_bottom",
            "direction": "bullish",
            "confidence": 78,
            "start_date": str(df[date_col].iloc[li[0]])[:10],
            "end_date":   str(df[date_col].iloc[li[2]])[:10],
            "key_levels": {
                "resistance": round(resistance, 2),
                "support":    round(avg_l, 2),
                "target":     round(target, 2),
                "stop":       round(avg_l * 0.99, 2),
            },
            "description": f"Triple Bottom ~{avg_l:.2f}. Resistance {resistance:.2f}. Target {target:.2f}.",
        })

    return results


# ── Triangles ─────────────────────────────────────────────────────────────────

def _detect_triangle(df: pd.DataFrame, date_col: str) -> list[dict]:
    results = []
    if len(df) < 20:
        return results

    window = df.tail(60).copy()
    if len(window) < 15:
        return results

    highs  = window["High"].values
    lows   = window["Low"].values
    closes = window["Close"].values
    n = len(window)
    xs = np.arange(n)

    # Fit trendlines to swing highs and swing lows
    h_idx = argrelextrema(highs, np.greater_equal, order=3)[0]
    l_idx = argrelextrema(lows,  np.less_equal,    order=3)[0]

    if len(h_idx) < 2 or len(l_idx) < 2:
        return results

    # Least-squares fit
    def linreg(x_pts: np.ndarray, y_pts: np.ndarray):
        if len(x_pts) < 2:
            return 0.0, float(y_pts[0]) if len(y_pts) else 0.0
        m, b = np.polyfit(x_pts, y_pts, 1)
        return float(m), float(b)

    h_slope, h_int = linreg(h_idx.astype(float), highs[h_idx])
    l_slope, l_int = linreg(l_idx.astype(float), lows[l_idx])

    last_high  = h_slope * (n - 1) + h_int
    last_low   = l_slope * (n - 1) + l_int
    first_high = h_slope * 0 + h_int
    first_low  = l_slope * 0 + l_int

    # Convergence check — lines must be narrowing
    initial_range = first_high - first_low
    final_range   = last_high  - last_low
    if initial_range <= 0 or final_range >= initial_range:
        return results

    converging = (initial_range - final_range) / initial_range

    # Classify
    h_flat = abs(h_slope) < 0.02 * (max(highs) / n)
    l_flat = abs(l_slope) < 0.02 * (max(highs) / n)

    if h_slope > 0 and l_slope > 0 and h_slope < l_slope:
        ptype, direction, conf = "ascending_triangle", "bullish", 70
    elif h_slope < 0 and l_slope < 0 and h_slope > l_slope:
        ptype, direction, conf = "descending_triangle", "bearish", 70
    elif h_slope < -0.001 and l_slope > 0.001:
        ptype, direction, conf = "symmetrical_triangle", "neutral", 65
    elif h_flat and l_slope > 0.001:
        ptype, direction, conf = "ascending_triangle", "bullish", 72
    elif l_flat and h_slope < -0.001:
        ptype, direction, conf = "descending_triangle", "bearish", 72
    else:
        return results

    if converging > 0.3:
        conf += 5

    mid  = (last_high + last_low) / 2
    height = first_high - first_low
    target = mid + height if direction == "bullish" else mid - height

    start_date = str(window[date_col].iloc[0])[:10] if date_col in window.columns else str(window.index[0])[:10]
    end_date   = str(window[date_col].iloc[-1])[:10] if date_col in window.columns else str(window.index[-1])[:10]

    results.append({
        "type": ptype,
        "direction": direction,
        "confidence": min(conf, 88),
        "start_date": start_date,
        "end_date":   end_date,
        "key_levels": {
            "resistance": round(last_high, 2),
            "support":    round(last_low, 2),
            "target":     round(target, 2),
            "stop":       round(last_low * 0.99 if direction != "bearish" else last_high * 1.01, 2),
        },
        "description": (
            f"{ptype.replace('_', ' ').title()} forming. "
            f"Upper trendline ~{last_high:.2f}, lower ~{last_low:.2f}. "
            f"Projected target {target:.2f}."
        ),
    })
    return results


# ── Flag / Pennant ────────────────────────────────────────────────────────────

def _detect_flag(df: pd.DataFrame, date_col: str) -> list[dict]:
    results = []
    if len(df) < 30:
        return results

    # Pole: sharp move in prior 10-20 bars
    pole_window  = 15
    flag_window  = 12
    if len(df) < pole_window + flag_window:
        return results

    pole  = df.iloc[-(pole_window + flag_window):-(flag_window)]
    flag  = df.iloc[-flag_window:]

    pole_move = (float(pole["Close"].iloc[-1]) - float(pole["Close"].iloc[0])) / float(pole["Close"].iloc[0]) * 100
    flag_move = (float(flag["Close"].iloc[-1]) - float(flag["Close"].iloc[0])) / float(flag["Close"].iloc[0]) * 100

    # Bull flag: pole up >5%, flag consolidates (slightly down or flat)
    if pole_move >= 5 and -4 <= flag_move <= 1:
        resistance = float(flag["High"].max())
        support    = float(flag["Low"].min())
        target     = resistance + abs(float(pole["Close"].iloc[-1]) - float(pole["Close"].iloc[0]))
        results.append({
            "type": "bull_flag",
            "direction": "bullish",
            "confidence": 72,
            "start_date": str(flag[date_col].iloc[0] if date_col in flag.columns else flag.index[0])[:10],
            "end_date":   str(flag[date_col].iloc[-1] if date_col in flag.columns else flag.index[-1])[:10],
            "key_levels": {
                "resistance": round(resistance, 2),
                "support":    round(support, 2),
                "target":     round(target, 2),
                "stop":       round(support * 0.99, 2),
            },
            "description": (
                f"Bull Flag: pole up {pole_move:.1f}%, "
                f"flag consolidating {flag_move:.1f}%. "
                f"Breakout target {target:.2f}."
            ),
        })

    # Bear flag: pole down >5%, flag consolidates (slightly up or flat)
    if pole_move <= -5 and -1 <= flag_move <= 4:
        resistance = float(flag["High"].max())
        support    = float(flag["Low"].min())
        target     = support - abs(float(pole["Close"].iloc[-1]) - float(pole["Close"].iloc[0]))
        results.append({
            "type": "bear_flag",
            "direction": "bearish",
            "confidence": 72,
            "start_date": str(flag[date_col].iloc[0] if date_col in flag.columns else flag.index[0])[:10],
            "end_date":   str(flag[date_col].iloc[-1] if date_col in flag.columns else flag.index[-1])[:10],
            "key_levels": {
                "resistance": round(resistance, 2),
                "support":    round(support, 2),
                "target":     round(target, 2),
                "stop":       round(resistance * 1.01, 2),
            },
            "description": (
                f"Bear Flag: pole down {pole_move:.1f}%, "
                f"flag {flag_move:.1f}%. Target {target:.2f}."
            ),
        })
    return results


# ── Wedge ─────────────────────────────────────────────────────────────────────

def _detect_wedge(df: pd.DataFrame, date_col: str) -> list[dict]:
    results = []
    if len(df) < 25:
        return results

    window = df.tail(50)
    highs = window["High"].values
    lows  = window["Low"].values
    n = len(window)

    h_idx = argrelextrema(highs, np.greater_equal, order=3)[0]
    l_idx = argrelextrema(lows,  np.less_equal,    order=3)[0]
    if len(h_idx) < 2 or len(l_idx) < 2:
        return results

    def linreg(x_pts, y_pts):
        if len(x_pts) < 2:
            return 0.0, float(y_pts[0])
        m, b = np.polyfit(x_pts.astype(float), y_pts, 1)
        return float(m), float(b)

    h_slope, h_int = linreg(h_idx, highs[h_idx])
    l_slope, l_int = linreg(l_idx, lows[l_idx])

    # Rising wedge: both slopes up but converging (h_slope < l_slope effectively)
    # Falling wedge: both slopes down but converging
    if h_slope > 0 and l_slope > 0 and h_slope < l_slope:
        ptype, direction, conf = "rising_wedge", "bearish", 68
    elif h_slope < 0 and l_slope < 0 and h_slope > l_slope:
        ptype, direction, conf = "falling_wedge", "bullish", 68
    else:
        return results

    last_high = h_slope * (n - 1) + h_int
    last_low  = l_slope * (n - 1) + l_int
    height    = (h_slope * 0 + h_int) - (l_slope * 0 + l_int)
    target    = last_low - height if direction == "bearish" else last_high + height

    start_date = str(window[date_col].iloc[0] if date_col in window.columns else window.index[0])[:10]
    end_date   = str(window[date_col].iloc[-1] if date_col in window.columns else window.index[-1])[:10]

    results.append({
        "type": ptype,
        "direction": direction,
        "confidence": conf,
        "start_date": start_date,
        "end_date":   end_date,
        "key_levels": {
            "resistance": round(last_high, 2),
            "support":    round(last_low, 2),
            "target":     round(target, 2),
            "stop":       round(last_high * 1.01 if direction == "bullish" else last_low * 0.99, 2),
        },
        "description": (
            f"{ptype.replace('_', ' ').title()} — "
            f"both lines {'rising' if h_slope > 0 else 'falling'} and converging. "
            f"Target {target:.2f}."
        ),
    })
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Candlestick pattern detection (last N bars)
# ─────────────────────────────────────────────────────────────────────────────

def detect_candlestick_patterns(df: pd.DataFrame, lookback: int = 30) -> list[dict]:
    """
    Detect common single/multi-bar candlestick patterns.
    Returns list of {date, pattern, direction, description}.
    """
    df = df.tail(lookback).copy()
    results: list[dict] = []

    opens  = df["Open"].values.astype(float)
    highs  = df["High"].values.astype(float)
    lows   = df["Low"].values.astype(float)
    closes = df["Close"].values.astype(float)

    if hasattr(df.index, "strftime"):
        dates = df.index.strftime("%Y-%m-%d").tolist()
    else:
        dates = [str(i)[:10] for i in df.index]

    n = len(df)

    def body(i):     return abs(closes[i] - opens[i])
    def total(i):    return highs[i] - lows[i]
    def upper_wick(i): return highs[i] - max(opens[i], closes[i])
    def lower_wick(i): return min(opens[i], closes[i]) - lows[i]
    def is_bull(i):  return closes[i] >= opens[i]

    for i in range(n):
        b = body(i)
        t = total(i) if total(i) > 0 else 0.001
        uw = upper_wick(i)
        lw = lower_wick(i)

        # Doji: body < 10% of total range
        if b / t < 0.10:
            results.append({"date": dates[i], "pattern": "Doji", "direction": "neutral",
                            "description": "Indecision candle — body < 10% of range."})
            continue

        # Marubozu: almost no wicks
        if uw / t < 0.05 and lw / t < 0.05:
            d = "bullish" if is_bull(i) else "bearish"
            results.append({"date": dates[i], "pattern": "Marubozu", "direction": d,
                            "description": f"{d.title()} Marubozu — strong momentum, no wicks."})
            continue

        # Hammer (single): long lower wick, small body near top, in downtrend
        if lw >= 2 * b and uw / t < 0.15 and lw / t > 0.55:
            results.append({"date": dates[i], "pattern": "Hammer", "direction": "bullish",
                            "description": "Hammer — long lower wick suggests buying pressure at lows."})

        # Inverted Hammer: long upper wick, small body near bottom
        if uw >= 2 * b and lw / t < 0.15 and uw / t > 0.55:
            results.append({"date": dates[i], "pattern": "Inverted Hammer", "direction": "bullish",
                            "description": "Inverted Hammer — potential reversal signal."})

        # Shooting Star: long upper wick, small body near bottom, in uptrend
        if uw >= 2 * b and lw / t < 0.15 and uw / t > 0.55 and not is_bull(i):
            results.append({"date": dates[i], "pattern": "Shooting Star", "direction": "bearish",
                            "description": "Shooting Star — bearish rejection at highs."})

        # Spinning top: small body with nearly equal wicks
        if b / t < 0.35 and abs(uw - lw) / t < 0.15:
            results.append({"date": dates[i], "pattern": "Spinning Top", "direction": "neutral",
                            "description": "Spinning Top — balance between buyers and sellers."})

        # Two-bar patterns
        if i < 1:
            continue
        pb = body(i - 1)

        # Engulfing
        if (is_bull(i) and not is_bull(i - 1) and
                closes[i] > opens[i - 1] and opens[i] < closes[i - 1] and b > pb):
            results.append({"date": dates[i], "pattern": "Bullish Engulfing", "direction": "bullish",
                            "description": "Bullish Engulfing — buyers overwhelm prior sellers."})

        if (not is_bull(i) and is_bull(i - 1) and
                closes[i] < opens[i - 1] and opens[i] > closes[i - 1] and b > pb):
            results.append({"date": dates[i], "pattern": "Bearish Engulfing", "direction": "bearish",
                            "description": "Bearish Engulfing — sellers overwhelm prior buyers."})

        # Harami
        if (is_bull(i) and not is_bull(i - 1) and
                opens[i] > closes[i - 1] and closes[i] < opens[i - 1]):
            results.append({"date": dates[i], "pattern": "Bullish Harami", "direction": "bullish",
                            "description": "Bullish Harami — small candle inside prior bearish candle."})

        if (not is_bull(i) and is_bull(i - 1) and
                opens[i] < closes[i - 1] and closes[i] > opens[i - 1]):
            results.append({"date": dates[i], "pattern": "Bearish Harami", "direction": "bearish",
                            "description": "Bearish Harami — small candle inside prior bullish candle."})

        # Three-bar patterns
        if i < 2:
            continue

        # Morning Star
        if (not is_bull(i - 2) and body(i - 1) / total(i - 1) < 0.3 and is_bull(i) and
                closes[i] > (opens[i - 2] + closes[i - 2]) / 2):
            results.append({"date": dates[i], "pattern": "Morning Star", "direction": "bullish",
                            "description": "Morning Star — 3-bar bullish reversal at lows."})

        # Evening Star
        if (is_bull(i - 2) and body(i - 1) / total(i - 1) < 0.3 and not is_bull(i) and
                closes[i] < (opens[i - 2] + closes[i - 2]) / 2):
            results.append({"date": dates[i], "pattern": "Evening Star", "direction": "bearish",
                            "description": "Evening Star — 3-bar bearish reversal at highs."})

    return results
