import pytest
import pandas as pd


def test_vectorbt_portfolio_stats_optional():
    vbt = pytest.importorskip("vectorbt")
    close = pd.Series([100, 101, 102, 101, 103, 104], name="Close")
    entries = pd.Series([False, True, False, False, False, False], index=close.index)
    exits = entries.shift(2).fillna(False)
    pf = vbt.Portfolio.from_signals(close, entries=entries, exits=exits, freq="1D")
    st = pf.stats()
    assert "Total Return [%]" in st

