"""NAV → OHLC helpers used by /mf/schemes/{code}/ohlc."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from app.mf.nav_ohlc import heikin_ashi, line_ohlc, nav_rows_to_daily_ohlc_df, ohlc_to_series_payload, resample_nav_ohlc


class _Nav:
    __slots__ = ("nav_date", "nav")

    def __init__(self, nav_date: date, nav: float) -> None:
        self.nav_date = nav_date
        self.nav = nav


def test_nav_rows_to_daily_ohlc_df_builds_ohlc_columns():
    base = date(2024, 1, 1)
    rows = [_Nav(base + timedelta(days=i), 100.0 + i) for i in range(5)]
    df = nav_rows_to_daily_ohlc_df(rows)
    assert not df.empty
    assert set(df.columns) >= {"Open", "High", "Low", "Close", "Volume"}
    assert len(df) == 5


def test_resample_nav_ohlc_weekly_reduces_rows():
    idx = pd.date_range("2024-01-01", periods=30, freq="D")
    df = pd.DataFrame(
        {
            "Open": range(30),
            "High": range(30),
            "Low": range(30),
            "Close": range(30),
            "Volume": [0.0] * 30,
        },
        index=idx,
    )
    w = resample_nav_ohlc(df, "1w")
    assert len(w) < len(df)


def test_heikin_ashi_and_line_ohlc_and_payload():
    idx = pd.date_range("2024-01-01", periods=4, freq="D")
    df = pd.DataFrame(
        {
            "Open": [1, 2, 3, 4],
            "High": [2, 3, 4, 5],
            "Low": [0.5, 1.5, 2.5, 3.5],
            "Close": [1.5, 2.5, 3.5, 4.5],
            "Volume": [1.0, 1.0, 1.0, 1.0],
        },
        index=idx,
    )
    ha = heikin_ashi(df)
    assert len(ha) == len(df)
    ln = line_ohlc(df)
    assert (ln["Open"] == ln["Close"]).all()
    payload = ohlc_to_series_payload(ln)
    assert payload[0]["time"][:4] == "2024"
    assert "open" in payload[0]
