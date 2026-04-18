from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


SUPPORTED_SIGNAL_TYPES_V1: set[str] = {
    # NAV-based
    "nav_52w_breakout",
    "nav_momentum",
    "peer_underperformance",
    "nav_return_momentum",
    "nav_rsi_extreme",
    "nav_macd_cross",
    "nav_ema_cross",
    # Holdings-based
    "concentration_risk",
    "sector_rotation",
    "portfolio_drift",
    "holdings_changes",
    "overlap_alert",
    # (More v1 types can be added without breaking schema)
}


def validate_rulebook_v1(rulebook: dict[str, Any]) -> None:
    if not isinstance(rulebook, dict):
        raise ValueError("rulebook_json must be an object")
    if rulebook.get("rulebook_type") != "mf":
        raise ValueError("rulebook_type must be 'mf'")
    defs = rulebook.get("signal_definitions")
    if not isinstance(defs, list) or len(defs) == 0:
        raise ValueError("signal_definitions must be a non-empty array")

    for idx, d in enumerate(defs):
        if not isinstance(d, dict):
            raise ValueError(f"signal_definitions[{idx}] must be an object")
        st = d.get("signal_type")
        if not isinstance(st, str) or not st.strip():
            raise ValueError(f"signal_definitions[{idx}].signal_type is required")
        if st not in SUPPORTED_SIGNAL_TYPES_V1:
            raise ValueError(f"Unsupported signal_type '{st}' (v1)")
        if "enabled" in d and not isinstance(d.get("enabled"), bool):
            raise ValueError(f"signal_definitions[{idx}].enabled must be boolean")
        if "thresholds" in d and not isinstance(d.get("thresholds"), dict):
            raise ValueError(f"signal_definitions[{idx}].thresholds must be an object")
        if "cooldown_days" in d:
            cd = d.get("cooldown_days")
            if not isinstance(cd, int) or cd < 0 or cd > 3650:
                raise ValueError(f"signal_definitions[{idx}].cooldown_days must be an int between 0 and 3650")


@dataclass(frozen=True)
class MFSignalCandidate:
    scheme_code: int
    family_id: int | None
    signal_type: str
    nav_date: date | None
    base_score: float
    confidence_score: float
    context: dict[str, Any]


def default_rulebook() -> dict[str, Any]:
    """
    v1 MF rulebook format.
    Keep it minimal and deterministic; LLM can enrich confidence later.
    """
    return {
        "rulebook_type": "mf",
        "signal_definitions": [
            {
                "signal_type": "nav_52w_breakout",
                "enabled": True,
                "thresholds": {"min_ret_30d_pct": 4.0},
                "cooldown_days": 7,
            },
            {
                "signal_type": "nav_momentum",
                "enabled": True,
                "thresholds": {"min_ret_90d_pct": 8.0},
                "cooldown_days": 7,
            },
            {
                "signal_type": "peer_underperformance",
                "enabled": True,
                "thresholds": {"lag_by_pct": 4.0},
                "cooldown_days": 14,
            },
            {
                "signal_type": "nav_return_momentum",
                "enabled": True,
                "thresholds": {"min_ret_7d_pct": 1.5, "min_ret_30d_pct": 3.0},
                "cooldown_days": 7,
            },
            {
                "signal_type": "nav_rsi_extreme",
                "enabled": True,
                "thresholds": {"rsi_oversold": 35.0, "rsi_overbought": 70.0},
                "cooldown_days": 7,
            },
            {
                "signal_type": "nav_macd_cross",
                "enabled": True,
                "thresholds": {},
                "cooldown_days": 7,
            },
            {
                "signal_type": "nav_ema_cross",
                "enabled": True,
                "thresholds": {"fast": 20, "slow": 50},
                "cooldown_days": 14,
            },
            {
                "signal_type": "concentration_risk",
                "enabled": True,
                "thresholds": {"top5_pct": 55.0, "single_pct": 12.0},
                "cooldown_days": 30,
            },
            {
                "signal_type": "sector_rotation",
                "enabled": True,
                "thresholds": {"min_sector_shift_pct": 5.0},
                "cooldown_days": 30,
            },
            {
                "signal_type": "portfolio_drift",
                "enabled": True,
                "thresholds": {"min_drift_pct": 8.0},
                "cooldown_days": 30,
            },
            {
                "signal_type": "holdings_changes",
                "enabled": True,
                "thresholds": {"min_added": 2, "min_removed": 2},
                "cooldown_days": 30,
            },
            {
                "signal_type": "overlap_alert",
                "enabled": True,
                "thresholds": {"min_overlap_pct": 60.0},
                "cooldown_days": 30,
            },
        ],
    }


def eval_nav_signals(
    *,
    scheme_code: int,
    family_id: int | None,
    nav_date: date,
    metrics: dict[str, Any],
    rulebook: dict[str, Any],
) -> list[MFSignalCandidate]:
    out: list[MFSignalCandidate] = []
    defs = rulebook.get("signal_definitions") or []
    for d in defs:
        if not isinstance(d, dict) or not d.get("enabled"):
            continue
        st = str(d.get("signal_type") or "")
        th = d.get("thresholds") or {}
        if st == "nav_52w_breakout":
            is_52w = bool(metrics.get("is_52w_high"))
            ret_30d = metrics.get("ret_30d")
            min_ret = float(th.get("min_ret_30d_pct", 0.0))
            if is_52w and isinstance(ret_30d, (int, float)) and ret_30d >= min_ret:
                out.append(
                    MFSignalCandidate(
                        scheme_code=scheme_code,
                        family_id=family_id,
                        signal_type=st,
                        nav_date=nav_date,
                        base_score=100.0,
                        confidence_score=85.0,
                        context={"metrics": metrics, "thresholds": th},
                    )
                )
        elif st == "nav_momentum":
            ret_90d = metrics.get("ret_90d")
            min_ret = float(th.get("min_ret_90d_pct", 0.0))
            if isinstance(ret_90d, (int, float)) and ret_90d >= min_ret:
                out.append(
                    MFSignalCandidate(
                        scheme_code=scheme_code,
                        family_id=family_id,
                        signal_type=st,
                        nav_date=nav_date,
                        base_score=90.0,
                        confidence_score=80.0,
                        context={"metrics": metrics, "thresholds": th},
                    )
                )
        elif st == "peer_underperformance":
            ret_90d = metrics.get("ret_90d")
            med = metrics.get("peer_ret_90d_median")
            lag_by = float(th.get("lag_by_pct", 0.0))
            if isinstance(ret_90d, (int, float)) and isinstance(med, (int, float)):
                if ret_90d <= float(med) - lag_by:
                    out.append(
                        MFSignalCandidate(
                            scheme_code=scheme_code,
                            family_id=family_id,
                            signal_type=st,
                            nav_date=nav_date,
                            base_score=85.0,
                            confidence_score=75.0,
                            context={
                                "metrics": metrics,
                                "thresholds": th,
                                "peer_category": metrics.get("peer_category"),
                                "peer_ret_90d_median": med,
                            },
                        )
                    )
        elif st == "nav_return_momentum":
            ret_7d = metrics.get("ret_7d")
            ret_30d = metrics.get("ret_30d")
            min_7d = float(th.get("min_ret_7d_pct", 0.0))
            min_30d = float(th.get("min_ret_30d_pct", 0.0))
            if isinstance(ret_7d, (int, float)) and isinstance(ret_30d, (int, float)):
                if ret_7d >= min_7d and ret_30d >= min_30d:
                    out.append(
                        MFSignalCandidate(
                            scheme_code=scheme_code,
                            family_id=family_id,
                            signal_type=st,
                            nav_date=nav_date,
                            base_score=78.0,
                            confidence_score=70.0,
                            context={"metrics": metrics, "thresholds": th},
                        )
                    )
        elif st == "nav_rsi_extreme":
            rv = metrics.get("rsi")
            if isinstance(rv, (int, float)):
                os_ = float(th.get("rsi_oversold", 35.0))
                ob_ = float(th.get("rsi_overbought", 70.0))
                if rv <= os_:
                    out.append(
                        MFSignalCandidate(
                            scheme_code=scheme_code,
                            family_id=family_id,
                            signal_type=st,
                            nav_date=nav_date,
                            base_score=82.0,
                            confidence_score=74.0,
                            context={"direction": "bullish", "rsi": rv, "thresholds": th, "metrics": metrics},
                        )
                    )
                elif rv >= ob_:
                    out.append(
                        MFSignalCandidate(
                            scheme_code=scheme_code,
                            family_id=family_id,
                            signal_type=st,
                            nav_date=nav_date,
                            base_score=82.0,
                            confidence_score=74.0,
                            context={"direction": "bearish", "rsi": rv, "thresholds": th, "metrics": metrics},
                        )
                    )
        elif st == "nav_macd_cross":
            cross = metrics.get("macd_cross")
            if isinstance(cross, str) and cross in {"bullish", "bearish"}:
                out.append(
                    MFSignalCandidate(
                        scheme_code=scheme_code,
                        family_id=family_id,
                        signal_type=st,
                        nav_date=nav_date,
                        base_score=80.0,
                        confidence_score=72.0,
                        context={"direction": cross, "macd": metrics.get("macd"), "macd_signal": metrics.get("macd_signal"), "metrics": metrics},
                    )
                )
        elif st == "nav_ema_cross":
            cross = metrics.get("ema_cross")
            if isinstance(cross, str) and cross in {"bullish", "bearish"}:
                out.append(
                    MFSignalCandidate(
                        scheme_code=scheme_code,
                        family_id=family_id,
                        signal_type=st,
                        nav_date=nav_date,
                        base_score=78.0,
                        confidence_score=70.0,
                        context={"direction": cross, "ema_fast": metrics.get("ema_fast"), "ema_slow": metrics.get("ema_slow"), "metrics": metrics},
                    )
                )
    return out


def eval_holdings_signals(
    *,
    scheme_code: int,
    family_id: int | None,
    month: date,
    holdings_summary: dict[str, Any],
    rulebook: dict[str, Any],
) -> list[MFSignalCandidate]:
    out: list[MFSignalCandidate] = []
    defs = rulebook.get("signal_definitions") or []
    for d in defs:
        if not isinstance(d, dict) or not d.get("enabled"):
            continue
        st = str(d.get("signal_type") or "")
        th = d.get("thresholds") or {}
        if st == "concentration_risk":
            top5 = float(holdings_summary.get("top5_weight_pct") or 0.0)
            single = float(holdings_summary.get("max_single_weight_pct") or 0.0)
            if top5 >= float(th.get("top5_pct", 1000.0)) or single >= float(th.get("single_pct", 1000.0)):
                out.append(
                    MFSignalCandidate(
                        scheme_code=scheme_code,
                        family_id=family_id,
                        signal_type=st,
                        nav_date=month,
                        base_score=95.0,
                        confidence_score=82.0,
                        context={"month": str(month), "holdings": holdings_summary, "thresholds": th},
                    )
                )
        elif st == "sector_rotation":
            shift = float(holdings_summary.get("sector_shift_max_abs_pct") or 0.0)
            min_shift = float(th.get("min_sector_shift_pct", 1000.0))
            if shift >= min_shift:
                out.append(
                    MFSignalCandidate(
                        scheme_code=scheme_code,
                        family_id=family_id,
                        signal_type=st,
                        nav_date=month,
                        base_score=80.0,
                        confidence_score=75.0,
                        context={"month": str(month), "sector_shift_max_abs_pct": shift, "thresholds": th},
                    )
                )
        elif st == "portfolio_drift":
            drift = float(holdings_summary.get("drift_max_abs_pct") or holdings_summary.get("sector_shift_max_abs_pct") or 0.0)
            min_drift = float(th.get("min_drift_pct", 1000.0))
            if drift >= min_drift:
                out.append(
                    MFSignalCandidate(
                        scheme_code=scheme_code,
                        family_id=family_id,
                        signal_type=st,
                        nav_date=month,
                        base_score=78.0,
                        confidence_score=72.0,
                        context={"month": str(month), "drift_max_abs_pct": drift, "thresholds": th},
                    )
                )
        elif st == "holdings_changes":
            added = int(holdings_summary.get("holdings_added_count") or 0)
            removed = int(holdings_summary.get("holdings_removed_count") or 0)
            min_added = int(th.get("min_added", 1000000))
            min_removed = int(th.get("min_removed", 1000000))
            if added >= min_added or removed >= min_removed:
                out.append(
                    MFSignalCandidate(
                        scheme_code=scheme_code,
                        family_id=family_id,
                        signal_type=st,
                        nav_date=month,
                        base_score=70.0,
                        confidence_score=68.0,
                        context={"month": str(month), "added": added, "removed": removed, "thresholds": th},
                    )
                )
        elif st == "overlap_alert":
            max_ov = float(holdings_summary.get("overlap_max_pct") or 0.0)
            min_ov = float(th.get("min_overlap_pct", 1000.0))
            overlaps = holdings_summary.get("overlaps") or []
            if max_ov >= min_ov and isinstance(overlaps, list) and overlaps:
                out.append(
                    MFSignalCandidate(
                        scheme_code=scheme_code,
                        family_id=family_id,
                        signal_type=st,
                        nav_date=month,
                        base_score=88.0,
                        confidence_score=80.0,
                        context={"month": str(month), "overlap_max_pct": max_ov, "overlaps": overlaps, "thresholds": th},
                    )
                )
    return out
