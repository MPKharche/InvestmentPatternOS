from __future__ import annotations

from datetime import date
from typing import Any


def collapse_by_bar_index_gap(
    rows: list[dict[str, Any]],
    *,
    bar_field: str = "_bar_index",
    identity_fields: tuple[str, ...],
    cooldown_bars: int = 14,
) -> list[dict[str, Any]]:
    """
    Keep the first event per identity; drop later events whose bar index is within
    `cooldown_bars` of the last accepted event for the same identity.
    """
    if not rows:
        return []
    rows_sorted = sorted(rows, key=lambda r: int(r.get(bar_field, 0)))
    last_bar: dict[tuple[Any, ...], int] = {}
    out: list[dict[str, Any]] = []
    for r in rows_sorted:
        bi = int(r.get(bar_field, 0))
        ident = tuple(r.get(f) for f in identity_fields)
        lb = last_bar.get(ident)
        if lb is not None and (bi - lb) < int(cooldown_bars):
            continue
        last_bar[ident] = bi
        out.append({k: v for k, v in r.items() if k != bar_field})
    return out


def collapse_chart_patterns_by_end_date_gap(
    rows: list[dict[str, Any]],
    *,
    cooldown_days: int = 14,
) -> list[dict[str, Any]]:
    def _ord(d: Any) -> int:
        s = str(d or "")[:10]
        try:
            return date.fromisoformat(s).toordinal()
        except Exception:
            return 0

    rows_sorted = sorted(rows, key=lambda r: str(r.get("end_date", "")))
    last_day: dict[tuple[Any, ...], int] = {}
    out: list[dict[str, Any]] = []
    for r in rows_sorted:
        ident = (r.get("type"), r.get("direction"))
        od = _ord(r.get("end_date"))
        if od == 0:
            out.append(r)
            continue
        ld = last_day.get(ident)
        if ld is not None and (od - ld) < int(cooldown_days):
            continue
        last_day[ident] = od
        out.append(r)
    return out


def collapse_events_by_sorted_index(
    rows: list[dict[str, Any]],
    *,
    time_key: str,
    kind_key: str,
    direction_key: str = "direction",
    cooldown_bars: int = 14,
) -> list[dict[str, Any]]:
    """
    Fallback: treat sorted row order as bar index (valid when rows are one-per-bar).
    """
    if not rows:
        return []
    rows_sorted = sorted(rows, key=lambda r: str(r.get(time_key, "")))
    last_i: dict[tuple[Any, ...], int] = {}
    out: list[dict[str, Any]] = []
    for i, r in enumerate(rows_sorted):
        ident = (r.get(kind_key), r.get(direction_key))
        li = last_i.get(ident)
        if li is not None and (i - li) < int(cooldown_bars):
            continue
        last_i[ident] = i
        out.append(r)
    return out
