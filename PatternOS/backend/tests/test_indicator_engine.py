import pandas as pd

from app.scanner.indicators import compute_indicators


def test_compute_indicators_auto_fallback_no_crash():
    df = pd.DataFrame(
        {
            "Open": [1, 2, 3, 4, 5],
            "High": [1, 2, 3, 4, 5],
            "Low": [1, 2, 3, 4, 5],
            "Close": [1, 2, 3, 4, 5],
            "Volume": [100, 110, 120, 130, 140],
        }
    )
    out = compute_indicators(df)
    # Minimal sanity: expected columns exist regardless of engine.
    assert "rsi" in out.columns
    assert "macd" in out.columns
    assert "ema_20" in out.columns

