"""Normalize Pattern Studio rulebooks into executable criteria + direction."""
from __future__ import annotations


def extract_criteria_and_direction(
    rulebook: dict,
    *,
    implicit_macd_default: bool = False,
) -> tuple[list, str]:
    """
    Normalises multiple rulebook formats into a (criteria_list, direction) tuple.
    Supports:
    - New format:  {"criteria": ["macd_divergence_bearish", ...], "direction": "bearish"}
    - Old format:  {"pattern_type": "macd_divergence", "conditions": {...}}
    - LLM format:  {"conditions": {"divergence_types": {"bearish": {...}}}, ...}
    """
    if rulebook.get("criteria"):
        return rulebook["criteria"], rulebook.get("direction", "bearish")

    criteria: list = []
    direction = "bearish"

    pattern_type = rulebook.get("pattern_type", "")
    conditions = rulebook.get("conditions", {})
    div_types = conditions.get("divergence_types", {})

    if "bearish" in div_types and "bullish" not in div_types:
        direction = "bearish"
    elif "bullish" in div_types and "bearish" not in div_types:
        direction = "bullish"
    elif rulebook.get("direction"):
        direction = str(rulebook["direction"])

    if "macd_divergence" in pattern_type or div_types:
        if direction == "bearish" or "bearish" in div_types:
            criteria.append("macd_divergence_bearish")
        else:
            criteria.append("macd_divergence_bullish")

    if "rsi_divergence" in pattern_type:
        if direction == "bearish":
            criteria.append("rsi_divergence_bearish")
        else:
            criteria.append("rsi_divergence_bullish")

    hist_cross = conditions.get("histogram_crossover", {})
    if hist_cross.get("required"):
        if direction == "bearish":
            criteria.append("macd_negative")
        else:
            criteria.append("macd_positive")

    if "ema_crossover" in pattern_type:
        if direction == "bearish":
            criteria.append("ema_crossover_bearish")
        else:
            criteria.append("ema_crossover_bullish")

    if not criteria and implicit_macd_default:
        # Legacy backtests: empty extraction defaulted to bearish MACD divergence
        criteria = ["macd_divergence_bearish"]

    return criteria, direction


def is_criteria_only_scan(rulebook: dict) -> bool:
    """True when all extracted checks are MACD/RSI divergence or simple indicator gates."""
    from app.scanner.criteria_checks import CONDITION_CHECK_KEYS, SIMPLE_CHECK_KEYS

    criteria, _ = extract_criteria_and_direction(rulebook, implicit_macd_default=False)
    if not criteria:
        return False
    allowed = CONDITION_CHECK_KEYS | SIMPLE_CHECK_KEYS
    for c in criteria:
        ctype = c if isinstance(c, str) else c.get("type", "")
        if ctype not in allowed:
            return False
    return True
