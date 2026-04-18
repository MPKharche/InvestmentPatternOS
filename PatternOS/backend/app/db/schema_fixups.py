"""
Lightweight, idempotent schema fixups for local/dev environments.

This is NOT a full migration system. It only adds columns that newer code expects
so the API doesn't crash against an older database schema.
"""

from __future__ import annotations

from sqlalchemy import inspect, text

from app.db.session import engine


def ensure_latest_schema() -> None:
    insp = inspect(engine)
    tables = set(insp.get_table_names())

    statements: list[str] = []

    # Added in migrations/007_pattern_horizons_signal_meta.sql
    if "signal_context" in tables:
        cols = {c["name"] for c in insp.get_columns("signal_context")}
        if "forward_horizon_returns" not in cols:
            statements.append(
                "ALTER TABLE signal_context "
                "ADD COLUMN IF NOT EXISTS forward_horizon_returns JSONB"
            )
        if "equity_research_note" not in cols:
            statements.append(
                "ALTER TABLE signal_context "
                "ADD COLUMN IF NOT EXISTS equity_research_note JSONB"
            )

    if "pattern_events" in tables:
        cols = {c["name"] for c in insp.get_columns("pattern_events")}
        if "ret_21d" not in cols:
            statements.append(
                "ALTER TABLE pattern_events ADD COLUMN IF NOT EXISTS ret_21d DOUBLE PRECISION"
            )
        if "ret_63d" not in cols:
            statements.append(
                "ALTER TABLE pattern_events ADD COLUMN IF NOT EXISTS ret_63d DOUBLE PRECISION"
            )
        if "ret_126d" not in cols:
            statements.append(
                "ALTER TABLE pattern_events ADD COLUMN IF NOT EXISTS ret_126d DOUBLE PRECISION"
            )

    if "signal_alert_journal" in tables:
        cols = {c["name"] for c in insp.get_columns("signal_alert_journal")}
        if "attempt_count" not in cols:
            statements.append(
                "ALTER TABLE signal_alert_journal ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0"
            )
        if "next_attempt_at" not in cols:
            statements.append(
                "ALTER TABLE signal_alert_journal ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ"
            )
        if "last_attempt_at" not in cols:
            statements.append(
                "ALTER TABLE signal_alert_journal ADD COLUMN IF NOT EXISTS last_attempt_at TIMESTAMPTZ"
            )
        if "last_error" not in cols:
            statements.append(
                "ALTER TABLE signal_alert_journal ADD COLUMN IF NOT EXISTS last_error TEXT"
            )
        if "last_http_status" not in cols:
            statements.append(
                "ALTER TABLE signal_alert_journal ADD COLUMN IF NOT EXISTS last_http_status INTEGER"
            )

    if "backtest_runs" in tables:
        cols = {c["name"] for c in insp.get_columns("backtest_runs")}
        if "engine" not in cols:
            statements.append(
                "ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS engine VARCHAR(20) DEFAULT 'internal'"
            )
        if "stats_json" not in cols:
            statements.append(
                "ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS stats_json JSONB"
            )

    if not statements:
        return

    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
