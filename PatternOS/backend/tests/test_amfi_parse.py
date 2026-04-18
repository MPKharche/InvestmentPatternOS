from __future__ import annotations

from app.mf.amfi import parse_navall


def test_parse_navall_skips_headers_and_parses_rows():
    lines = [
        "Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date",
        "",
        "Axis Mutual Fund",
        "120438;INF846K01CR6;-;Axis Banking & PSU Debt Fund - Direct Plan - Growth Option;2833.4699;16-Apr-2026",
        "not-a-row;with;semicolons;but;bad;date",
    ]
    rows = parse_navall(lines)
    assert len(rows) == 1
    r = rows[0]
    assert r.scheme_code == 120438
    assert r.isin_growth == "INF846K01CR6"
    assert r.isin_reinvest is None
    assert "Axis Banking" in r.scheme_name
    assert abs(r.nav - 2833.4699) < 1e-6
    assert str(r.nav_date) == "2026-04-16"


def test_parse_navall_accepts_8_column_variant():
    lines = [
        "120438;INF846K01CR6;-;Axis Fund;2833.4699;2833.4;2834.0;16-Apr-2026",
    ]
    rows = parse_navall(lines)
    assert len(rows) == 1
    assert rows[0].scheme_code == 120438

