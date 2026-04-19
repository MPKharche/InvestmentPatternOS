"""
Condition evaluator for screener rules.

Supports operators: >, <, >=, <=, ==, !=, between, contains
Supported fields:
  - Technical: rsi, macd, macd_hist, sma_20, sma_50, sma_200, ema_20, close, volume, close_vs_sma, bb_upper, bb_lower, bb_width, atr
  - Pattern flags: macd_divergence_bullish, macd_divergence_bearish, rsi_divergence_bullish, rsi_divergence_bearish, ema_crossover_bullish, ema_crossover_bearish
  - Fundamental: pe, pb, roe, debt_to_equity, dividend_yield, beta, market_cap, eps, forward_pe, trailing_pe
  - Universe meta: sector, exchange, asset_class
"""

from __future__ import annotations

from typing import Any, Callable
import pandas as pd
import numpy as np


# Field mapping to extract from data dict or DataFrame
FIELD_EXTRACTORS: dict[str, Callable[[dict | pd.DataFrame, int], Any]] = {}


def register_field(name: str):
    """Decorator to register a field extractor."""

    def decorator(func):
        FIELD_EXTRACTORS[name] = func
        return func

    return decorator


@register_field("rsi")
def _extract_rsi(data, i):
    if isinstance(data, dict):
        return data.get("rsi")
    return data["rsi"].iloc[i] if "rsi" in data.columns else None


@register_field("macd")
def _extract_macd(data, i):
    if isinstance(data, dict):
        return data.get("macd")
    return float(data["macd"].iloc[i]) if "macd" in data.columns else None


@register_field("macd_hist")
def _extract_macd_hist(data, i):
    if isinstance(data, dict):
        return data.get("macd_hist")
    return float(data["macd_hist"].iloc[i]) if "macd_hist" in data.columns else None


@register_field("macd_signal")
def _extract_macd_signal(data, i):
    if isinstance(data, dict):
        return data.get("macd_signal")
    return float(data["macd_signal"].iloc[i]) if "macd_signal" in data.columns else None


@register_field("sma_20")
def _extract_sma20(data, i):
    if isinstance(data, dict):
        return data.get("sma_20")
    return float(data["sma_20"].iloc[i]) if "sma_20" in data.columns else None


@register_field("sma_50")
def _extract_sma50(data, i):
    if isinstance(data, dict):
        return data.get("sma_50")
    return float(data["sma_50"].iloc[i]) if "sma_50" in data.columns else None


@register_field("sma_200")
def _extract_sma200(data, i):
    if isinstance(data, dict):
        return data.get("sma_200")
    return float(data["sma_200"].iloc[i]) if "sma_200" in data.columns else None


@register_field("ema_20")
def _extract_ema20(data, i):
    if isinstance(data, dict):
        return data.get("ema_20")
    return float(data["ema_20"].iloc[i]) if "ema_20" in data.columns else None


@register_field("ema_50")
def _extract_ema50(data, i):
    if isinstance(data, dict):
        return data.get("ema_50")
    return float(data["ema_50"].iloc[i]) if "ema_50" in data.columns else None


@register_field("close")
def _extract_close(data, i):
    if isinstance(data, dict):
        return data.get("close")
    return float(data["Close"].iloc[i]) if "Close" in data.columns else None


@register_field("volume")
def _extract_volume(data, i):
    if isinstance(data, dict):
        return data.get("volume")
    return float(data["Volume"].iloc[i]) if "Volume" in data.columns else None


@register_field("pe")
def _extract_pe(data, i):
    return data.get("pe_ratio") if isinstance(data, dict) else None


@register_field("pb")
def _extract_pb(data, i):
    return data.get("pb_ratio") if isinstance(data, dict) else None


@register_field("roe")
def _extract_roe(data, i):
    return data.get("roe") if isinstance(data, dict) else None


@register_field("debt_to_equity")
def _extract_debt_to_equity(data, i):
    return data.get("debt_to_equity") if isinstance(data, dict) else None


@register_field("dividend_yield")
def _extract_dividend_yield(data, i):
    return data.get("dividend_yield") if isinstance(data, dict) else None


@register_field("beta")
def _extract_beta(data, i):
    return data.get("beta") if isinstance(data, dict) else None


@register_field("market_cap")
def _extract_market_cap(data, i):
    return data.get("market_cap") if isinstance(data, dict) else None


@register_field("sector")
def _extract_sector(data, i):
    return data.get("sector") if isinstance(data, dict) else None


@register_field("atr")
def _extract_atr(data, i):
    if isinstance(data, dict):
        return data.get("atr")
    return float(data["atr"].iloc[i]) if "atr" in data.columns else None


@register_field("stoch_k")
def _extract_stoch_k(data, i):
    if isinstance(data, dict):
        return data.get("stoch_k")
    return float(data["stoch_k"].iloc[i]) if "stoch_k" in data.columns else None


@register_field("stoch_d")
def _extract_stoch_d(data, i):
    if isinstance(data, dict):
        return data.get("stoch_d")
    return float(data["stoch_d"].iloc[i]) if "stoch_d" in data.columns else None


@register_field("adx")
def _extract_adx(data, i):
    if isinstance(data, dict):
        return data.get("adx")
    return float(data["adx"].iloc[i]) if "adx" in data.columns else None


@register_field("obv")
def _extract_obv(data, i):
    if isinstance(data, dict):
        return data.get("obv")
    return float(data["obv"].iloc[i]) if "obv" in data.columns else None


@register_field("bb_upper")
def _extract_bb_upper(data, i):
    if isinstance(data, dict):
        return data.get("bb_upper")
    return float(data["bb_upper"].iloc[i]) if "bb_upper" in data.columns else None


@register_field("bb_lower")
def _extract_bb_lower(data, i):
    if isinstance(data, dict):
        return data.get("bb_lower")
    return float(data["bb_lower"].iloc[i]) if "bb_lower" in data.columns else None


@register_field("bb_width")
def _extract_bb_width(data, i):
    if isinstance(data, dict):
        return data.get("bb_width")
    return float(data["bb_width"].iloc[i]) if "bb_width" in data.columns else None


@register_field("close_vs_sma")
def _extract_close_vs_sma(data, i):
    """Calculate close vs SMA 20 percentage difference."""
    if isinstance(data, dict):
        close = data.get("close")
        sma_20 = data.get("sma_20")
    else:
        close = float(data["Close"].iloc[i]) if "Close" in data.columns else None
        sma_20 = float(data["sma_20"].iloc[i]) if "sma_20" in data.columns else None
    
    if close is not None and sma_20 is not None and sma_20 != 0:
        return ((close - sma_20) / sma_20) * 100
    return None


# Pattern flag extractors (require computed indicators DataFrame)
@register_field("macd_divergence_bullish")
def _extract_macd_divergence_bullish(data, i):
    if not isinstance(data, pd.DataFrame) or "macd" not in data.columns:
        return False
    from app.scanner.criteria_checks import detect_macd_divergence_bullish

    return detect_macd_divergence_bullish(data, i, rulebook={})


@register_field("macd_divergence_bearish")
def _extract_macd_divergence_bearish(data, i):
    if not isinstance(data, pd.DataFrame) or "macd" not in data.columns:
        return False
    from app.scanner.criteria_checks import detect_macd_divergence_bearish

    return detect_macd_divergence_bearish(data, i, rulebook={})


@register_field("rsi_divergence_bullish")
def _extract_rsi_divergence_bullish(data, i):
    if not isinstance(data, pd.DataFrame) or "rsi_14" not in data.columns:
        return False
    from app.scanner.criteria_checks import detect_rsi_divergence_bullish

    return detect_rsi_divergence_bullish(data, i, rulebook={})


@register_field("rsi_divergence_bearish")
def _extract_rsi_divergence_bearish(data, i):
    if not isinstance(data, pd.DataFrame) or "rsi_14" not in data.columns:
        return False
    from app.scanner.criteria_checks import detect_rsi_divergence_bearish

    return detect_rsi_divergence_bearish(data, i, rulebook={})


@register_field("ema_crossover_bullish")
def _extract_ema_crossover_bullish(data, i):
    if not isinstance(data, pd.DataFrame) or "ema_20" not in data.columns:
        return False
    from app.scanner.criteria_checks import detect_ema_crossover_bullish

    return detect_ema_crossover_bullish(data, i, rulebook={})


@register_field("ema_crossover_bearish")
def _extract_ema_crossover_bearish(data, i):
    if not isinstance(data, pd.DataFrame) or "ema_20" not in data.columns:
        return False
    from app.scanner.criteria_checks import detect_ema_crossover_bearish

    return detect_ema_crossover_bearish(data, i, rulebook={})


# ============================================================================
# Operators
# ============================================================================

OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "between": lambda a, bounds: (
        bounds[0] <= a <= bounds[1] if a is not None else False
    ),
    "contains": lambda a, substr: substr in str(a).lower() if a else False,
}


def evaluate_condition(
    data: dict | pd.DataFrame,
    condition: dict,
    index: int = -1,
) -> tuple[bool, Any]:
    """
    Evaluate a single condition against data.

    Supports:
      - Numeric comparison: {"field": "rsi", "operator": "<", "value": 30}
      - Between: {"field": "pe", "operator": "between", "min": 10, "max": 30}
      - Cross-field: {"field": "close", "operator": ">", "compare_field": "sma_20"}
      - Boolean flags: {"field": "macd_divergence_bullish", "operator": "==", "value": true}
    """
    field = condition["field"]
    op = condition["operator"]
    value = condition.get("value")
    compare_field = condition.get("compare_field")

    extractor = FIELD_EXTRACTORS.get(field)
    if not extractor:
        return False, f"unknown field: {field}"

    # Extract actual value from data
    actual = extractor(data, index)

    # Determine comparison target
    if compare_field:
        # Cross-field comparison
        other_extractor = FIELD_EXTRACTORS.get(compare_field)
        if not other_extractor:
            return False, f"unknown compare_field: {compare_field}"
        target = other_extractor(data, index)
    else:
        target = value

    # For boolean fields, identity comparison
    if isinstance(actual, (bool, np.bool_)):
        if op not in ("==", "!="):
            return False, "boolean fields only support == and !="
        passed = bool(actual) == (op == "==")
        return passed, bool(actual)

    # Handle between operator (target is ignored, use min/max)
    if op == "between":
        min_v = condition.get("min")
        max_v = condition.get("max")
        if min_v is None or max_v is None:
            return False, "missing min/max for between"
        passed = (actual is not None) and (min_v <= actual <= max_v)
        return passed, actual

    # Standard comparison
    try:
        comp_func = OPERATORS[op]
    except KeyError:
        return False, f"unknown operator: {op}"

    try:
        passed = comp_func(actual, target)
        return passed, actual
    except TypeError:
        return False, actual


def evaluate_all_conditions(
    data: dict | pd.DataFrame,
    conditions: list[dict],
    logic: str = "AND",
    index: int = -1,
) -> tuple[bool, dict]:
    """
    Evaluate list of conditions with AND/OR logic.

    Returns:
        (passed, {field: actual_value, ...})
    """
    results = {}
    all_passed = True if logic.upper() == "AND" else False

    for cond in conditions:
        field = cond["field"]
        passed, actual = evaluate_condition(data, cond, index)
        results[field] = actual

        if logic.upper() == "AND":
            all_passed = all_passed and passed
            if not all_passed:
                # Early exit on AND failure
                return False, results
        else:  # OR
            all_passed = all_passed or passed
            if all_passed:
                return True, results

    return all_passed, results


def compute_score(
    data: dict | pd.DataFrame, conditions: list[dict], logic: str, index: int = -1
) -> float:
    """
    Compute a 0-100 match score for a symbol.

    Simple scoring: each condition contributes equally.
    For AND: score = (passed_count / total) * 100
    For OR:  score = 100 if any passed else min(passed * penalty)
    """
    total = len(conditions)
    if total == 0:
        return 0.0

    passed_count = 0
    for cond in conditions:
        passed, _ = evaluate_condition(data, cond, index)
        if passed:
            passed_count += 1

    if logic.upper() == "AND":
        return round((passed_count / total) * 100, 2)
    else:  # OR
        return 100.0 if passed_count > 0 else 0.0


# ============================================================================
# Condition builders for common technical patterns
# ============================================================================


def condition_rsi_oversold(threshold: int = 30) -> dict:
    return {"field": "rsi", "operator": "<", "value": threshold}


def condition_rsi_overbought(threshold: int = 70) -> dict:
    return {"field": "rsi", "operator": ">", "value": threshold}


def condition_pe_between(min_pe: float, max_pe: float) -> dict:
    return {"field": "pe", "operator": "between", "min": min_pe, "max": max_pe}


def condition_macd_bullish_crossover() -> dict:
    return {"field": "macd_divergence_bullish", "operator": "==", "value": True}


def condition_macd_bearish_crossover() -> dict:
    return {"field": "macd_divergence_bearish", "operator": "==", "value": True}


def condition_price_above_sma(period: int = 20) -> dict:
    field = f"sma_{period}"
    return {
        "field": "close",
        "operator": ">",
        "value": field,
    }  # special: compare to another field


# Note: cross-field conditions handled in evaluate_all_conditions with special operator
