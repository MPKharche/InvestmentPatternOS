"""
Rule evaluator — interprets a pattern's rulebook_json against OHLCV data.

Scoring layers (total = 100 pts):
  1. Trend alignment        — EMA stack + prior-move direction       (20 pts)
  2. Momentum               — RSI zone + MACD crossover              (20 pts)
  3. Pattern tightness      — consolidation range vs rulebook        (20 pts)
  4. Volume confirmation    — dry-up in body + surge on breakout     (20 pts)
  5. Breakout quality       — close vs resistance + ATR filter       (20 pts)

Rulebook conditions that are not present default to "any" / pass-through.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Any

from app.scanner.indicators import latest_indicators, compute_indicators
from app.scanner.rulebook_criteria import extract_criteria_and_direction, is_criteria_only_scan
from app.scanner.criteria_checks import run_criteria_at_index


def evaluate_pattern(df: pd.DataFrame, rulebook: dict[str, Any]) -> tuple[float, dict]:
    """
    Returns (base_score 0-100, breakdown dict).
    breakdown: {check_name: {"passed": bool, "weight": int, "detail": str}}

    When the rulebook is a pure indicator/divergence criteria set (MACD/RSI divergence, etc.),
    scoring uses the same AND-of-criteria logic as backtests — not the generic consolidation
    rubric — so divergence patterns can reach production scans.
    """
    if is_criteria_only_scan(rulebook):
        try:
            idf = compute_indicators(df)
        except Exception as exc:
            return 0.0, {
                "criteria_scan": {
                    "passed": False,
                    "weight": 100,
                    "detail": f"Indicator compute failed: {exc!s}"[:200],
                }
            }
        i = len(idf) - 1
        criteria, direction = extract_criteria_and_direction(
            rulebook, implicit_macd_default=False
        )
        dparams = rulebook.get("divergence") or {}
        need = int(dparams.get("lookback_bars", 65)) + 5
        if i < need:
            return 5.0, {
                "criteria_scan": {
                    "passed": False,
                    "weight": 100,
                    "detail": f"Need at least ~{need} bars; have {i + 1}",
                }
            }
        ok = run_criteria_at_index(idf, i, criteria, rulebook)
        detail = (
            f"{'PASS' if ok else 'NO MATCH'}: {criteria} ({direction}) on latest bar — "
            "aligned swing divergence vs MACD/RSI (see criteria_checks)."
        )
        if ok:
            return 88.0, {"criteria_scan": {"passed": True, "weight": 100, "detail": detail}}
        return 18.0, {"criteria_scan": {"passed": False, "weight": 100, "detail": detail}}

    conditions = rulebook.get("conditions", {})
    weights = rulebook.get("confidence_weights", {
        "trend_alignment":    20,
        "momentum":           20,
        "pattern_tightness":  20,
        "volume_confirmation":20,
        "breakout_quality":   20,
    })
    # Back-compat: old rulebooks may use old key names
    if "trend_strength" in weights and "trend_alignment" not in weights:
        weights["trend_alignment"] = weights.pop("trend_strength")

    breakdown: dict = {}
    earned = 0.0
    total_weight = sum(weights.values()) or 100

    # ── Pre-compute indicators ─────────────────────────────────────────────────
    ind: dict[str, Any] = {}
    try:
        ind = latest_indicators(df)
    except Exception:
        ind = {}

    close_now = float(df["Close"].iloc[-1])
    open_now  = float(df["Open"].iloc[-1])

    # ── 1. Trend alignment ────────────────────────────────────────────────────
    trend_cfg  = conditions.get("trend", {})
    prior_trend = trend_cfg.get("prior_trend", "any")
    lookback   = trend_cfg.get("lookback_bars", 20)
    min_move   = trend_cfg.get("min_move_pct", 10)
    w          = weights.get("trend_alignment", 20)

    if prior_trend == "any":
        passed_trend = True
        detail = "No trend filter"
    else:
        if len(df) >= lookback:
            start_price = float(df["Close"].iloc[-lookback])
            move_pct    = ((close_now - start_price) / start_price) * 100
            if prior_trend == "bullish":
                passed_trend = move_pct >= min_move
            else:
                passed_trend = move_pct <= -min_move
            detail = f"Price move {move_pct:+.1f}% over {lookback} bars (need {'+' if prior_trend == 'bullish' else '-'}{min_move}%)"
        else:
            passed_trend = False
            detail = "Insufficient data"

    # Bonus: EMA stack confirms direction
    e20  = ind.get("ema_20")
    e50  = ind.get("ema_50")
    e200 = ind.get("ema_200")
    if passed_trend and e20 and e50 and e200:
        if prior_trend == "bullish" and e20 > e50 > e200:
            detail += " | EMA stack bullish ✓"
        elif prior_trend == "bearish" and e20 < e50 < e200:
            detail += " | EMA stack bearish ✓"

    if passed_trend:
        earned += w
    breakdown["trend_alignment"] = {"passed": passed_trend, "weight": w, "detail": detail}

    # ── 2. Momentum (RSI + MACD) ──────────────────────────────────────────────
    mom_cfg  = conditions.get("momentum", {})
    rsi_min  = mom_cfg.get("rsi_min", 0)
    rsi_max  = mom_cfg.get("rsi_max", 100)
    macd_pos = mom_cfg.get("macd_positive", None)   # True/False/None
    w        = weights.get("momentum", 20)

    rsi_val  = ind.get("rsi")
    macd_val = ind.get("macd")
    mhist    = ind.get("macd_hist")

    passed_mom   = True
    mom_details  = []

    if rsi_val is not None:
        rsi_in_zone = rsi_min <= rsi_val <= rsi_max
        if not rsi_in_zone:
            passed_mom = False
        mom_details.append(f"RSI {rsi_val:.1f} (zone {rsi_min}-{rsi_max})")
    else:
        mom_details.append("RSI N/A")

    if macd_pos is not None and macd_val is not None:
        macd_ok = (macd_val > 0) if macd_pos else (macd_val < 0)
        if not macd_ok:
            passed_mom = False
        mom_details.append(f"MACD {macd_val:.3f} ({'pos ✓' if macd_val > 0 else 'neg'})")

    if mhist is not None:
        mom_details.append(f"Hist {mhist:+.3f}")

    if passed_mom:
        earned += w
    breakdown["momentum"] = {"passed": passed_mom, "weight": w, "detail": " | ".join(mom_details)}

    # ── 3. Pattern tightness (consolidation) ──────────────────────────────────
    body_cfg    = conditions.get("pattern_body", {})
    consol_min  = body_cfg.get("consolidation_bars_min", 5)
    consol_max  = body_cfg.get("consolidation_bars_max", 30)
    range_max   = body_cfg.get("price_range_pct_max", 10)
    w           = weights.get("pattern_tightness", 20)

    window_size = min(consol_max, max(consol_min, 10))
    window = df.iloc[-(window_size + 1):-1]

    if len(window) >= consol_min:
        hi     = float(window["High"].max())
        lo     = float(window["Low"].min())
        rng    = ((hi - lo) / lo * 100) if lo > 0 else 999
        # Tighten check using ATR: good consolidation has shrinking ATR
        atr    = ind.get("atr")
        atr_ok = (atr is not None and atr < (rng / 100 * close_now * 0.8)) if atr else True
        passed_body = rng <= range_max
        detail = f"Range {rng:.1f}% (max {range_max}%)"
        if atr:
            detail += f" | ATR {atr:.2f}"
    else:
        passed_body = False
        detail = "Insufficient bars for consolidation check"

    if passed_body:
        earned += w
    breakdown["pattern_tightness"] = {"passed": passed_body, "weight": w, "detail": detail}

    # ── 4. Volume confirmation ────────────────────────────────────────────────
    vol_cfg      = conditions.get("volume", {})
    dry_up_req   = vol_cfg.get("volume_dry_up", True)
    dry_up_pct   = vol_cfg.get("volume_dry_up_pct", 40)
    breakout_mult = vol_cfg.get("breakout_volume_multiplier", 1.5)
    w             = weights.get("volume_confirmation", 20)

    avg_vol    = float(df["Volume"].tail(20).mean()) if "Volume" in df.columns else 0
    last_vol   = float(df["Volume"].iloc[-1]) if "Volume" in df.columns else 0
    consol_vol = float(df["Volume"].iloc[-(window_size + 1):-1].mean()) if len(df) > window_size else avg_vol
    vol_ratio  = last_vol / avg_vol if avg_vol > 0 else 1.0

    passed_vol = True
    vol_details: list[str] = []

    if dry_up_req and avg_vol > 0:
        dry_pct = (consol_vol / avg_vol) * 100
        if dry_pct > (100 - dry_up_pct + 20):
            passed_vol = False
        vol_details.append(f"Consol vol {dry_pct:.0f}% of avg")

    if vol_ratio < breakout_mult:
        passed_vol = False
    vol_details.append(f"Breakout vol {vol_ratio:.1f}x (need {breakout_mult}x)")

    # OBV trend
    obv = ind.get("obv") if ind else None
    if obv is not None and len(df) > 5:
        obv_series = df["Close"].tail(5)  # simple proxy; real OBV in indicators module
        vol_details.append("OBV computed")

    if passed_vol:
        earned += w
    breakdown["volume_confirmation"] = {"passed": passed_vol, "weight": w, "detail": " | ".join(vol_details)}

    # ── 5. Breakout quality ───────────────────────────────────────────────────
    bo_cfg       = conditions.get("breakout", {})
    res_lookback = bo_cfg.get("resistance_lookback_bars", 20)
    close_above  = bo_cfg.get("close_above", True)
    w            = weights.get("breakout_quality", 20)

    if len(df) >= res_lookback:
        resistance = float(df["High"].iloc[-res_lookback:-1].max())
        last_high  = float(df["High"].iloc[-1])
        atr        = ind.get("atr") or 0

        if close_above:
            passed_bo = close_now > resistance
            detail    = f"Close {close_now:.2f} vs resistance {resistance:.2f}"
        else:
            passed_bo = last_high > resistance
            detail    = f"High {last_high:.2f} vs resistance {resistance:.2f}"

        # ATR filter: breakout bar's range should be >= 1x ATR (genuine move)
        bar_range = last_high - float(df["Low"].iloc[-1])
        if atr > 0:
            detail += f" | Bar range {bar_range:.2f} vs ATR {atr:.2f}"
            if bar_range < atr * 0.5:
                passed_bo = False
                detail += " (weak bar)"
    else:
        passed_bo = False
        detail = "Insufficient data for breakout check"

    if passed_bo:
        earned += w
    breakdown["breakout_quality"] = {"passed": passed_bo, "weight": w, "detail": detail}

    # ── Final score ───────────────────────────────────────────────────────────
    base_score = round((earned / total_weight) * 100, 1) if total_weight > 0 else 0.0
    return base_score, breakdown
