"""Watchlist sync helper — mocked DB (no Postgres required)."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.mf.pipelines import sync_priority_amc_equity_direct_growth_monitored


def test_sync_priority_amc_equity_direct_growth_monitored_returns_counts():
    db = MagicMock()
    q = MagicMock()
    q.filter.return_value = q
    q.update.side_effect = [3, 7]
    db.query.return_value = q

    out = sync_priority_amc_equity_direct_growth_monitored(db)

    assert out == {"demoted": 3, "promoted": 7}
    assert db.query.call_count == 2
    db.commit.assert_called_once()
