from __future__ import annotations

import os
from io import BytesIO
from typing import Iterable

import pandas as pd
import numpy as np

from app.scanner.data import fetch_ohlcv
from app.scanner.indicators import compute_indicators


def _parse_indicators(ind: str | None) -> set[str]:
    if not ind:
        return set()
    return {p.strip().lower() for p in ind.split(",") if p.strip()}


def _df_time_index(df: pd.DataFrame) -> pd.DataFrame:
    if "Date" in df.columns:
        df = df.set_index("Date")
    elif "Datetime" in df.columns:
        df = df.set_index("Datetime")
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    return df


def render_equity_chart_png(
    symbol: str,
    timeframe: str = "1d",
    *,
    indicators: str | None = None,
    max_bars: int = 260,
    dpi: int = 120,
) -> bytes:
    """
    Render an equity chart image suitable for Telegram.
    Uses mplfinance; returns PNG bytes.
    """
    import mplfinance as mpf

    fallback_used = False
    df = fetch_ohlcv(symbol, timeframe, extended=True)
    if df is None or df.empty:
        # In dev/test, prefer returning a valid PNG with a "NO DATA" plot rather than a hard error.
        # This keeps Telegram/chart endpoints and E2E tests stable even when yfinance is unavailable.
        if os.environ.get("APP_ENV") in {"test", "development"}:
            fallback_used = True
            end = pd.Timestamp.utcnow().normalize()
            idx = pd.bdate_range(end=end, periods=max_bars)
            close = np.linspace(100.0, 110.0, len(idx))
            open_ = np.r_[close[0], close[:-1]]
            high = np.maximum(open_, close) * 1.01
            low = np.minimum(open_, close) * 0.99
            vol = np.full(len(idx), 0.0)
            df = pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol}, index=idx)
        else:
            raise ValueError("No data")

    df = df.tail(max_bars).copy()
    df = _df_time_index(df)

    ind_set = _parse_indicators(indicators)
    idf = compute_indicators(df) if ind_set else df

    addplots = []
    panel = 0
    if "ema" in ind_set:
        for c, color in (("ema_20", "dodgerblue"), ("ema_50", "orange"), ("ema_200", "magenta")):
            if c in idf.columns:
                addplots.append(mpf.make_addplot(idf[c], color=color, width=1.0, panel=0))
    if "rsi" in ind_set and "rsi" in idf.columns:
        panel = max(panel, 1)
        addplots.append(mpf.make_addplot(idf["rsi"], panel=1, color="purple", ylabel="RSI"))
    if "macd" in ind_set and all(c in idf.columns for c in ("macd", "macd_signal", "macd_hist")):
        macd_panel = 2 if panel >= 1 else 1
        panel = max(panel, macd_panel)
        addplots.append(mpf.make_addplot(idf["macd"], panel=macd_panel, color="teal", ylabel="MACD"))
        addplots.append(mpf.make_addplot(idf["macd_signal"], panel=macd_panel, color="gold"))
        addplots.append(
            mpf.make_addplot(
                idf["macd_hist"],
                panel=macd_panel,
                type="bar",
                color=["#16a34a" if v >= 0 else "#dc2626" for v in idf["macd_hist"].fillna(0.0)],
                alpha=0.6,
            )
        )

    buf = BytesIO()
    fig, _axes = mpf.plot(
        idf,
        type="candle",
        style="yahoo",
        addplot=addplots if addplots else None,
        # Keep rendering robust across data sources and environments; volume panels can be flaky
        # depending on column dtype / provider quirks and aren't essential for Telegram charts.
        volume=False,
        title=(f"{symbol} ({timeframe}) - NO DATA" if fallback_used else f"{symbol} ({timeframe})"),
        returnfig=True,
        figscale=1.1,
        panel_ratios=(6, 2, 2) if panel >= 2 else (6, 2) if panel == 1 else (6,),
    )
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    fig.clf()
    return buf.getvalue()


def render_mf_nav_chart_png(
    nav_points: Iterable[tuple[str, float]],
    scheme_label: str,
    *,
    indicators: str | None = None,
    max_points: int = 520,
    dpi: int = 120,
) -> bytes:
    """
    Render a mutual-fund NAV line chart image suitable for Telegram.
    `nav_points`: iterable of (YYYY-MM-DD, nav).
    Returns PNG bytes.
    """
    import mplfinance as mpf

    rows = list(nav_points)[-max_points:]
    if not rows:
        raise ValueError("No NAV data")

    df = pd.DataFrame(rows, columns=["Date", "NAV"])
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date")
    # Create OHLCV-like frame so we can reuse the indicator stack.
    df["Open"] = df["NAV"]
    df["High"] = df["NAV"]
    df["Low"] = df["NAV"]
    df["Close"] = df["NAV"]
    df["Volume"] = 0
    df = df[["Open", "High", "Low", "Close", "Volume"]]

    ind_set = _parse_indicators(indicators)
    idf = compute_indicators(df) if ind_set else df

    addplots = []
    panel = 0
    if "ema" in ind_set:
        for c, color in (("ema_20", "dodgerblue"), ("ema_50", "orange"), ("ema_200", "magenta")):
            if c in idf.columns:
                addplots.append(mpf.make_addplot(idf[c], color=color, width=1.0, panel=0))
    if "rsi" in ind_set and "rsi" in idf.columns:
        panel = max(panel, 1)
        addplots.append(mpf.make_addplot(idf["rsi"], panel=1, color="purple", ylabel="RSI"))
    if "macd" in ind_set and all(c in idf.columns for c in ("macd", "macd_signal", "macd_hist")):
        macd_panel = 2 if panel >= 1 else 1
        panel = max(panel, macd_panel)
        addplots.append(mpf.make_addplot(idf["macd"], panel=macd_panel, color="teal", ylabel="MACD"))
        addplots.append(mpf.make_addplot(idf["macd_signal"], panel=macd_panel, color="gold"))
        addplots.append(
            mpf.make_addplot(
                idf["macd_hist"],
                panel=macd_panel,
                type="bar",
                color=["#16a34a" if v >= 0 else "#dc2626" for v in idf["macd_hist"].fillna(0.0)],
                alpha=0.6,
            )
        )

    buf = BytesIO()
    fig, _axes = mpf.plot(
        idf,
        type="line",
        style="yahoo",
        addplot=addplots if addplots else None,
        title=f"{scheme_label} NAV",
        returnfig=True,
        figscale=1.1,
        panel_ratios=(6, 2, 2) if panel >= 2 else (6, 2) if panel == 1 else (6,),
    )
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    fig.clf()
    return buf.getvalue()
