"""Pattern cooldown collapse helpers (bar index + chart pattern end dates)."""

from __future__ import annotations

from app.scanner.pattern_cooldown import (
    collapse_by_bar_index_gap,
    collapse_chart_patterns_by_end_date_gap,
    collapse_events_by_sorted_index,
)


def test_collapse_by_bar_index_gap_keeps_first_within_cooldown():
    rows = [
        {"name": "HAMMER", "direction": "bullish", "_bar_index": 0},
        {"name": "HAMMER", "direction": "bullish", "_bar_index": 5},
        {"name": "HAMMER", "direction": "bullish", "_bar_index": 20},
    ]
    out = collapse_by_bar_index_gap(rows, identity_fields=("name", "direction"), cooldown_bars=14)
    assert len(out) == 2
    assert out[0]["name"] == "HAMMER"
    assert out[1]["name"] == "HAMMER"


def test_collapse_chart_patterns_by_end_date_gap():
    rows = [
        {"type": "HS", "direction": "bearish", "end_date": "2024-01-01"},
        {"type": "HS", "direction": "bearish", "end_date": "2024-01-05"},
        {"type": "HS", "direction": "bearish", "end_date": "2024-02-01"},
    ]
    out = collapse_chart_patterns_by_end_date_gap(rows, cooldown_days=14)
    assert len(out) == 2


def test_collapse_events_by_sorted_index_fallback():
    rows = [
        {"t": "2024-01-01", "kind": "A", "direction": "up"},
        {"t": "2024-01-02", "kind": "A", "direction": "up"},
        {"t": "2024-03-01", "kind": "A", "direction": "up"},
    ]
    out = collapse_events_by_sorted_index(rows, time_key="t", kind_key="kind", cooldown_bars=14)
    assert len(out) == 2
