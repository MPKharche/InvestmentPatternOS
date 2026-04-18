from __future__ import annotations

from datetime import date

from app.mf.rules import default_rulebook, eval_holdings_signals, eval_nav_signals, validate_rulebook_v1


def test_default_rulebook_shape():
    rb = default_rulebook()
    assert rb["rulebook_type"] == "mf"
    assert isinstance(rb["signal_definitions"], list)


def test_nav_52w_breakout_rule_triggers():
    rb = default_rulebook()
    metrics = {"is_52w_high": True, "ret_30d": 6.0, "ret_90d": 2.0}
    out = eval_nav_signals(
        scheme_code=123,
        family_id=1,
        nav_date=date(2026, 4, 16),
        metrics=metrics,
        rulebook=rb,
    )
    assert any(c.signal_type == "nav_52w_breakout" for c in out)


def test_peer_underperformance_triggers():
    rb = default_rulebook()
    metrics = {"ret_90d": 2.0, "peer_ret_90d_median": 10.0, "peer_category": "Equity: Flexi Cap"}
    out = eval_nav_signals(
        scheme_code=123,
        family_id=1,
        nav_date=date(2026, 4, 16),
        metrics=metrics,
        rulebook=rb,
    )
    assert any(c.signal_type == "peer_underperformance" for c in out)


def test_concentration_rule_triggers():
    rb = default_rulebook()
    summary = {"top5_weight_pct": 60.0, "max_single_weight_pct": 8.0}
    out = eval_holdings_signals(
        scheme_code=123,
        family_id=1,
        month=date(2026, 4, 1),
        holdings_summary=summary,
        rulebook=rb,
    )
    c = next(c for c in out if c.signal_type == "concentration_risk")
    assert c.nav_date == date(2026, 4, 1)


def test_sector_rotation_triggers():
    rb = default_rulebook()
    summary = {"sector_shift_max_abs_pct": 6.0}
    out = eval_holdings_signals(
        scheme_code=123,
        family_id=1,
        month=date(2026, 4, 1),
        holdings_summary=summary,
        rulebook=rb,
    )
    assert any(c.signal_type == "sector_rotation" for c in out)


def test_holdings_changes_triggers():
    rb = default_rulebook()
    summary = {"holdings_added_count": 2, "holdings_removed_count": 0}
    out = eval_holdings_signals(
        scheme_code=123,
        family_id=1,
        month=date(2026, 4, 1),
        holdings_summary=summary,
        rulebook=rb,
    )
    assert any(c.signal_type == "holdings_changes" for c in out)


def test_overlap_alert_triggers():
    rb = default_rulebook()
    summary = {
        "overlap_max_pct": 61.0,
        "overlaps": [{"other_family_id": 2, "overlap_pct": 61.0, "scheme_code": 999, "scheme_name": "X"}],
    }
    out = eval_holdings_signals(
        scheme_code=123,
        family_id=1,
        month=date(2026, 4, 1),
        holdings_summary=summary,
        rulebook=rb,
    )
    assert any(c.signal_type == "overlap_alert" for c in out)


def test_validate_rulebook_rejects_unknown_signal_type():
    rb = default_rulebook()
    rb["signal_definitions"][0]["signal_type"] = "nope"
    try:
        validate_rulebook_v1(rb)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "Unsupported signal_type" in str(e)
