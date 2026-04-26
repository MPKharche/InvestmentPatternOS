from __future__ import annotations

from typing import Any, Iterable

import pandas as pd


def nav_rows_to_daily_ohlc_df(rows: Iterable[Any]) -> pd.DataFrame:
    """
    Build a daily OHLC frame from MF NAV closes (single price per day).
    Open = previous close; High/Low straddle Open/Close (wicks zero when unchanged).
    """
    dates: list[pd.Timestamp] = []
    closes: list[float] = []
    for r in rows:
        d = getattr(r, "nav_date", None)
        v = getattr(r, "nav", None)
        if d is None or v is None:
            continue
        dates.append(pd.Timestamp(d).normalize())
        closes.append(float(v))
    if not dates:
        return pd.DataFrame()
    s_close = pd.Series(closes, index=pd.DatetimeIndex(dates)).sort_index()
    s_close = s_close[~s_close.index.duplicated(keep="last")]
    c = s_close.astype(float)
    o = c.shift(1)
    o.iloc[0] = c.iloc[0]
    h = pd.concat([o, c], axis=1).max(axis=1)
    l = pd.concat([o, c], axis=1).min(axis=1)
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": 0.0})


def resample_nav_ohlc(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    tf = (tf or "1d").strip()
    if tf == "1d":
        return df
    rule = "W-FRI" if tf == "1w" else "ME"
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    out = df.resample(rule).agg(agg)
    return out.dropna(subset=["Open", "High", "Low", "Close"])


def heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    o = df["Open"].astype(float).values
    h = df["High"].astype(float).values
    l = df["Low"].astype(float).values
    c = df["Close"].astype(float).values
    n = len(df)
    ha_close = (o + h + l + c) / 4.0
    ha_open = [0.0] * n
    ha_open[0] = (o[0] + c[0]) / 2.0
    for i in range(1, n):
        ha_open[i] = (ha_open[i - 1] + ha_close[i - 1]) / 2.0
    ha_open_s = pd.Series(ha_open, index=df.index)
    ha_close_s = pd.Series(ha_close, index=df.index)
    ha_high = pd.concat([pd.Series(h, index=df.index), ha_open_s, ha_close_s], axis=1).max(axis=1)
    ha_low = pd.concat([pd.Series(l, index=df.index), ha_open_s, ha_close_s], axis=1).min(axis=1)
    vol = df["Volume"] if "Volume" in df.columns else pd.Series(0.0, index=df.index)
    return pd.DataFrame({"Open": ha_open_s, "High": ha_high, "Low": ha_low, "Close": ha_close_s, "Volume": vol})


def line_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    c = df["Close"].astype(float)
    vol = df["Volume"] if "Volume" in df.columns else pd.Series(0.0, index=df.index)
    return pd.DataFrame({"Open": c, "High": c, "Low": c, "Close": c, "Volume": vol})


def ohlc_to_series_payload(df: pd.DataFrame) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ts, row in df.iterrows():
        t = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
        out.append(
            {
                "time": t,
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
            }
        )
    return out
