from __future__ import annotations

from typing import Any


_DEFAULT_PATTERNS: list[str] = [
    "CDLDOJI",
    "CDLHAMMER",
    "CDLINVERTEDHAMMER",
    "CDLSHOOTINGSTAR",
    "CDLENGULFING",
    "CDLHARAMI",
    "CDLHARAMICROSS",
    "CDLMORNINGSTAR",
    "CDLEVENINGSTAR",
    "CDLPIERCING",
    "CDLDARKCLOUDCOVER",
    "CDL3WHITESOLDIERS",
    "CDL3BLACKCROWS",
    "CDLSPINNINGTOP",
    "CDLMARUBOZU",
    "CDLDRAGONFLYDOJI",
    "CDLGRAVESTONEDOJI",
    "CDLHIGHWAVE",
    "CDLRISEFALL3METHODS",
    "CDL3INSIDE",
    "CDL3OUTSIDE",
    "CDLIDENTICAL3CROWS",
    "CDLSEPARATINGLINES",
    "CDLGAPSIDESIDEWHITE",
]


def detect_talib_candlestick_patterns(
    df,
    *,
    lookback: int = 60,
    patterns: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Optional TA-Lib candlestick pattern scan.

    Returns list of occurrences in the last `lookback` bars:
      { time, name, direction, value }

    `value` is the raw TA-Lib integer (positive = bullish, negative = bearish).
    """
    try:
        import talib
    except Exception:
        return []

    if df is None or len(df) == 0:
        return []

    pats = patterns or _DEFAULT_PATTERNS
    open_ = df["Open"].astype(float).to_numpy()
    high = df["High"].astype(float).to_numpy()
    low = df["Low"].astype(float).to_numpy()
    close = df["Close"].astype(float).to_numpy()

    if hasattr(df.index, "strftime"):
        times = df.index.strftime("%Y-%m-%d").tolist()
    else:
        times = [str(i)[:10] for i in df.index]

    start = max(0, len(times) - int(lookback))
    out: list[dict[str, Any]] = []

    for pname in pats:
        fn = getattr(talib, pname, None)
        if not fn:
            continue
        try:
            series = fn(open_, high, low, close)
        except Exception:
            continue
        for i in range(start, len(series)):
            v = int(series[i]) if series[i] is not None else 0
            if v == 0:
                continue
            out.append(
                {
                    "time": times[i],
                    "name": pname.replace("CDL", "").title().replace("_", " "),
                    "direction": "bullish" if v > 0 else "bearish",
                    "value": v,
                    "source": "talib",
                }
            )

    out.sort(key=lambda r: (r["time"], r["name"]))
    return out

