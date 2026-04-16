"""Pattern backtest engine."""
from __future__ import annotations
from datetime import datetime
import pandas as pd
from sqlalchemy.orm import Session

from app.db.models import PatternEvent, BacktestRun, Universe, PatternVersion
from app.scanner.data import fetch_ohlcv
from app.scanner.indicators import compute_indicators
from app.scanner.rulebook_criteria import extract_criteria_and_direction
from app.scanner.criteria_checks import run_criteria_at_index
from app.scanner.backtest_metrics import (
    forward_horizon_returns_pct,
    max_gain_loss_20d,
    outcome_from_rulebook,
)


def run_backtest(pattern_id: str, db: Session, scope: str = "full", symbols: list[str] | None = None) -> str:
    """
    Runs a backtest for a pattern against specified universe.
    """
    pv = db.query(PatternVersion).filter_by(pattern_id=pattern_id).order_by(PatternVersion.version.desc()).first()
    if not pv:
        raise ValueError("No rulebook found for pattern")
    rulebook = pv.rulebook_json
    criteria, direction = extract_criteria_and_direction(rulebook, implicit_macd_default=True)
    timeframes = rulebook.get("timeframes", ["1d"])
    bc = rulebook.get("backtest") or {}
    min_gap = int(bc.get("min_bars_between_events", 15))

    run = BacktestRun(pattern_id=pattern_id, version_num=pv.version, status="running")
    db.add(run)
    db.commit()
    db.refresh(run)
    run_id = run.id

    query = db.query(Universe).filter_by(active=True)
    if scope == "nifty50":
        query = query.filter(Universe.index_name == "Nifty 50")
    elif symbols:
        query = query.filter(Universe.symbol.in_(symbols))

    symbols = query.all()

    events_found = 0
    symbols_scanned = 0
    last_event_index: dict[str, int] = {}

    try:
        for sym in symbols:
            for tf in timeframes:
                try:
                    df = fetch_ohlcv(sym.symbol, tf, extended=True)
                    if df is None or len(df) < 50:
                        continue
                    idf = compute_indicators(df)
                    symbols_scanned += 1

                    if hasattr(idf.index, "strftime"):
                        dates = idf.index.strftime("%Y-%m-%d").tolist()
                    else:
                        dates = [str(d)[:10] for d in idf.index]

                    dparams = rulebook.get("divergence") or {}
                    start_i = int(dparams.get("lookback_bars", 65)) + 5
                    key = f"{sym.symbol}:{tf}"

                    for i in range(max(30, start_i), len(idf)):
                        if i + 126 >= len(idf):
                            break
                        prev = last_event_index.get(key)
                        if prev is not None and (i - prev) < min_gap:
                            continue
                        if not run_criteria_at_index(idf, i, criteria, rulebook):
                            continue

                        date_str = dates[i]
                        entry_price = float(idf["Close"].iloc[i])
                        rets = forward_horizon_returns_pct(idf, i)
                        max_g, max_l = max_gain_loss_20d(idf, i)
                        outcome = outcome_from_rulebook(direction, rets, rulebook)

                        ind_snap = {}
                        for col in ["ema_20", "ema_50", "ema_200", "rsi", "macd", "macd_signal", "adx", "macd_hist"]:
                            if col in idf.columns:
                                v = idf[col].iloc[i]
                                if not pd.isna(v):
                                    ind_snap[col] = round(float(v), 3)

                        evt = PatternEvent(
                            pattern_id=pattern_id,
                            symbol=sym.symbol,
                            exchange=sym.exchange,
                            timeframe=tf,
                            detected_at=date_str,
                            entry_price=entry_price,
                            indicator_snapshot=ind_snap,
                            ret_5d=rets.get("ret_5d"),
                            ret_10d=rets.get("ret_10d"),
                            ret_20d=rets.get("ret_20d"),
                            ret_21d=rets.get("ret_21d"),
                            ret_63d=rets.get("ret_63d"),
                            ret_126d=rets.get("ret_126d"),
                            max_gain_20d=max_g,
                            max_loss_20d=max_l,
                            outcome=outcome,
                            backtest_run_id=run_id,
                        )
                        try:
                            db.add(evt)
                            db.flush()
                            events_found += 1
                            last_event_index[key] = i
                        except Exception:
                            db.rollback()
                except Exception:
                    db.rollback()
                    continue

        db.commit()
        events = db.query(PatternEvent).filter_by(backtest_run_id=run_id).all()
        success = sum(1 for e in events if e.outcome == "success")
        failure = sum(1 for e in events if e.outcome == "failure")
        neutral = sum(1 for e in events if e.outcome == "neutral")
        rets_10d = [e.ret_10d for e in events if e.ret_10d is not None]
        rets_5d = [e.ret_5d for e in events if e.ret_5d is not None]
        rets_20d = [e.ret_20d for e in events if e.ret_20d is not None]

        run = db.query(BacktestRun).filter_by(id=run_id).first()
        run.symbols_scanned = symbols_scanned
        run.events_found = events_found
        run.success_count = success
        run.failure_count = failure
        run.neutral_count = neutral
        run.success_rate = round(success / max(success + failure, 1) * 100, 1)
        run.avg_ret_5d = round(sum(rets_5d) / len(rets_5d), 2) if rets_5d else None
        run.avg_ret_10d = round(sum(rets_10d) / len(rets_10d), 2) if rets_10d else None
        run.avg_ret_20d = round(sum(rets_20d) / len(rets_20d), 2) if rets_20d else None
        run.status = "complete"
        run.completed_at = datetime.utcnow()
        db.commit()

    except Exception as e:
        run = db.query(BacktestRun).filter_by(id=run_id).first()
        if run:
            run.status = "failed"
            run.error_message = str(e)[:500]
            run.completed_at = datetime.utcnow()
            db.commit()
        raise

    return run_id
