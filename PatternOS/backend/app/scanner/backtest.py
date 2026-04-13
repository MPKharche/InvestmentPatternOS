"""Pattern backtest engine."""
from __future__ import annotations
import uuid
from datetime import datetime
import pandas as pd
import numpy as np
from scipy.signal import argrelextrema
from sqlalchemy.orm import Session

from app.db.models import PatternEvent, BacktestRun, Universe, PatternVersion
from app.scanner.data import fetch_ohlcv
from app.scanner.indicators import compute_indicators


def _detect_macd_divergence_bearish(df: pd.DataFrame, i: int, window: int = 20) -> bool:
    """True if bar i shows bearish MACD divergence (price higher high, MACD lower high)."""
    if i < window or "macd" not in df.columns:
        return False
    seg = df.iloc[i - window: i + 1]
    prices = seg["Close"].values
    macds = seg["macd"].fillna(0).values
    # Find peaks in price
    price_peaks = argrelextrema(prices, np.greater, order=3)[0]
    macd_peaks = argrelextrema(macds, np.greater, order=3)[0]
    if len(price_peaks) < 2 or len(macd_peaks) < 2:
        return False
    p1, p2 = price_peaks[-2], price_peaks[-1]
    m1, m2 = macd_peaks[-2], macd_peaks[-1]
    # Price made higher high, MACD made lower high
    price_higher = prices[p2] > prices[p1] * 1.005
    macd_lower = macds[m2] < macds[m1] * 0.97
    return bool(price_higher and macd_lower)


def _detect_macd_divergence_bullish(df: pd.DataFrame, i: int, window: int = 20) -> bool:
    if i < window or "macd" not in df.columns:
        return False
    seg = df.iloc[i - window: i + 1]
    prices = seg["Close"].values
    macds = seg["macd"].fillna(0).values
    price_troughs = argrelextrema(prices, np.less, order=3)[0]
    macd_troughs = argrelextrema(macds, np.less, order=3)[0]
    if len(price_troughs) < 2 or len(macd_troughs) < 2:
        return False
    p1, p2 = price_troughs[-2], price_troughs[-1]
    m1, m2 = macd_troughs[-2], macd_troughs[-1]
    price_lower = prices[p2] < prices[p1] * 0.995
    macd_higher = macds[m2] > macds[m1] * 1.03
    return bool(price_lower and macd_higher)


def _detect_rsi_divergence_bearish(df: pd.DataFrame, i: int, window: int = 20) -> bool:
    if i < window or "rsi" not in df.columns:
        return False
    seg = df.iloc[i - window: i + 1]
    prices = seg["Close"].values
    rsis = seg["rsi"].fillna(50).values
    price_peaks = argrelextrema(prices, np.greater, order=3)[0]
    rsi_peaks = argrelextrema(rsis, np.greater, order=3)[0]
    if len(price_peaks) < 2 or len(rsi_peaks) < 2:
        return False
    p1, p2 = price_peaks[-2], price_peaks[-1]
    r1, r2 = rsi_peaks[-2], rsi_peaks[-1]
    return bool(prices[p2] > prices[p1] * 1.005 and rsis[r2] < rsis[r1] * 0.97)


def _detect_rsi_divergence_bullish(df: pd.DataFrame, i: int, window: int = 20) -> bool:
    if i < window or "rsi" not in df.columns:
        return False
    seg = df.iloc[i - window: i + 1]
    prices = seg["Close"].values
    rsis = seg["rsi"].fillna(50).values
    price_tr = argrelextrema(prices, np.less, order=3)[0]
    rsi_tr = argrelextrema(rsis, np.less, order=3)[0]
    if len(price_tr) < 2 or len(rsi_tr) < 2:
        return False
    p1, p2 = price_tr[-2], price_tr[-1]
    r1, r2 = rsi_tr[-2], rsi_tr[-1]
    return bool(prices[p2] < prices[p1] * 0.995 and rsis[r2] > rsis[r1] * 1.03)


CONDITION_CHECKS = {
    "macd_divergence_bearish": _detect_macd_divergence_bearish,
    "macd_divergence_bullish": _detect_macd_divergence_bullish,
    "rsi_divergence_bearish": _detect_rsi_divergence_bearish,
    "rsi_divergence_bullish": _detect_rsi_divergence_bullish,
}

SIMPLE_CHECKS = {
    "rsi_overbought":    lambda df, i: df["rsi"].iloc[i] > 70 if "rsi" in df.columns else False,
    "rsi_oversold":      lambda df, i: df["rsi"].iloc[i] < 30 if "rsi" in df.columns else False,
    "price_above_ema200": lambda df, i: df["Close"].iloc[i] > df["ema_200"].iloc[i] if "ema_200" in df.columns and not pd.isna(df["ema_200"].iloc[i]) else False,
    "price_below_ema200": lambda df, i: df["Close"].iloc[i] < df["ema_200"].iloc[i] if "ema_200" in df.columns and not pd.isna(df["ema_200"].iloc[i]) else False,
    "macd_negative":     lambda df, i: df["macd"].iloc[i] < 0 if "macd" in df.columns else False,
    "macd_positive":     lambda df, i: df["macd"].iloc[i] > 0 if "macd" in df.columns else False,
    "adx_trending":      lambda df, i: df["adx"].iloc[i] > 25 if "adx" in df.columns and not pd.isna(df["adx"].iloc[i]) else False,
    "ema_crossover_bearish": lambda df, i: (
        i > 0 and "ema_20" in df.columns and "ema_50" in df.columns
        and df["ema_20"].iloc[i] < df["ema_50"].iloc[i]
        and df["ema_20"].iloc[i-1] >= df["ema_50"].iloc[i-1]
    ),
    "ema_crossover_bullish": lambda df, i: (
        i > 0 and "ema_20" in df.columns and "ema_50" in df.columns
        and df["ema_20"].iloc[i] > df["ema_50"].iloc[i]
        and df["ema_20"].iloc[i-1] <= df["ema_50"].iloc[i-1]
    ),
}


def _forward_returns(df: pd.DataFrame, i: int):
    n = len(df)
    entry = df["Close"].iloc[i]
    def pct(j):
        if i + j < n:
            return round((df["Close"].iloc[i + j] / entry - 1) * 100, 2)
        return None
    r5, r10, r20 = pct(5), pct(10), pct(20)
    # max gain/loss over 20d
    if i + 1 < n:
        window = df["Close"].iloc[i+1 : min(n, i+21)]
        max_g = round((window.max() / entry - 1) * 100, 2) if len(window) else None
        max_l = round((window.min() / entry - 1) * 100, 2) if len(window) else None
    else:
        max_g = max_l = None
    return r5, r10, r20, max_g, max_l


def _outcome(direction: str, ret_10d):
    if ret_10d is None:
        return "pending"
    if direction == "bearish":
        if ret_10d < -3: return "success"
        if ret_10d > 3:  return "failure"
    else:
        if ret_10d > 3:  return "success"
        if ret_10d < -3: return "failure"
    return "neutral"


def _extract_criteria_and_direction(rulebook: dict) -> tuple[list, str]:
    """
    Normalises multiple rulebook formats into a (criteria_list, direction) tuple.
    Supports:
    - New format:  {"criteria": ["macd_divergence_bearish", ...], "direction": "bearish"}
    - Old format:  {"pattern_type": "macd_divergence", "conditions": {...}}
    - LLM format:  {"conditions": {"divergence_types": {"bearish": {...}}}, ...}
    """
    # New explicit format
    if rulebook.get("criteria"):
        return rulebook["criteria"], rulebook.get("direction", "bearish")

    criteria: list = []
    direction = "bearish"

    pattern_type = rulebook.get("pattern_type", "")
    conditions   = rulebook.get("conditions", {})
    div_types    = conditions.get("divergence_types", {})

    # Determine direction from rulebook
    if "bearish" in div_types and "bullish" not in div_types:
        direction = "bearish"
    elif "bullish" in div_types and "bearish" not in div_types:
        direction = "bullish"
    elif rulebook.get("direction"):
        direction = rulebook["direction"]

    # Map pattern_type to conditions
    if "macd_divergence" in pattern_type or div_types:
        if direction == "bearish" or "bearish" in div_types:
            criteria.append("macd_divergence_bearish")
        else:
            criteria.append("macd_divergence_bullish")

    if "rsi_divergence" in pattern_type:
        if direction == "bearish":
            criteria.append("rsi_divergence_bearish")
        else:
            criteria.append("rsi_divergence_bullish")

    # Histogram crossover → MACD direction filter
    hist_cross = conditions.get("histogram_crossover", {})
    if hist_cross.get("required"):
        if direction == "bearish":
            criteria.append("macd_negative")
        else:
            criteria.append("macd_positive")

    # EMA crossover patterns
    if "ema_crossover" in pattern_type:
        if direction == "bearish":
            criteria.append("ema_crossover_bearish")
        else:
            criteria.append("ema_crossover_bullish")

    # Fallback: if still empty, use MACD divergence bearish as default
    if not criteria:
        criteria = ["macd_divergence_bearish"]

    return criteria, direction


def run_backtest(pattern_id: str, db: Session, scope: str = "full", symbols: list[str] | None = None) -> str:
    """
    Runs a backtest for a pattern against specified universe.
    Args:
        pattern_id: Pattern to backtest
        db: Database session
        scope: "full" (all active), "nifty50" (only nifty 50 constituents), or "custom" (use symbols param)
        symbols: List of specific symbols to scan (if scope not "full" or "nifty50")
    Returns the backtest_run_id.
    Creates PatternEvent records for each detected instance.
    """
    # Get latest rulebook
    pv = db.query(PatternVersion).filter_by(pattern_id=pattern_id).order_by(PatternVersion.version.desc()).first()
    if not pv:
        raise ValueError("No rulebook found for pattern")
    rulebook = pv.rulebook_json
    criteria, direction = _extract_criteria_and_direction(rulebook)
    timeframes = rulebook.get("timeframes", ["1d"])

    # Create backtest run
    run = BacktestRun(pattern_id=pattern_id, version_num=pv.version, status="running")
    db.add(run)
    db.commit()
    db.refresh(run)
    run_id = run.id

    # Get universe based on scope
    query = db.query(Universe).filter_by(active=True)
    if scope == "nifty50":
        # Filter to only Nifty 50 constituents
        query = query.filter(Universe.index_name == "Nifty 50")
    elif symbols:
        # Filter to specific symbols
        query = query.filter(Universe.symbol.in_(symbols))

    symbols = query.all()

    events_found = 0
    symbols_scanned = 0

    try:
        for sym in symbols:
            for tf in timeframes:
                try:
                    df = fetch_ohlcv(sym.symbol, tf, extended=True)
                    if df is None or len(df) < 50:
                        continue
                    idf = compute_indicators(df)
                    symbols_scanned += 1

                    # Get dates
                    if hasattr(idf.index, "strftime"):
                        dates = idf.index.strftime("%Y-%m-%d").tolist()
                    else:
                        dates = [str(d)[:10] for d in idf.index]

                    # Scan each bar
                    for i in range(30, len(idf)):
                        # Check all criteria
                        all_met = True
                        for crit in criteria:
                            ctype = crit if isinstance(crit, str) else crit.get("type", "")
                            if ctype in CONDITION_CHECKS:
                                if not CONDITION_CHECKS[ctype](idf, i):
                                    all_met = False
                                    break
                            elif ctype in SIMPLE_CHECKS:
                                try:
                                    if not SIMPLE_CHECKS[ctype](idf, i):
                                        all_met = False
                                        break
                                except Exception:
                                    all_met = False
                                    break

                        if not all_met:
                            continue

                        date_str = dates[i]
                        entry_price = float(idf["Close"].iloc[i])
                        r5, r10, r20, max_g, max_l = _forward_returns(idf, i)

                        ind_snap = {}
                        for col in ["ema_20", "ema_50", "ema_200", "rsi", "macd", "macd_signal", "adx"]:
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
                            ret_5d=r5, ret_10d=r10, ret_20d=r20,
                            max_gain_20d=max_g, max_loss_20d=max_l,
                            outcome=_outcome(direction, r10),
                            backtest_run_id=run_id,
                        )
                        try:
                            db.add(evt)
                            db.flush()
                            events_found += 1
                        except Exception:
                            db.rollback()
                except Exception:
                    db.rollback()
                    continue

        # Update run stats
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
        run.avg_ret_5d = round(sum(rets_5d)/len(rets_5d), 2) if rets_5d else None
        run.avg_ret_10d = round(sum(rets_10d)/len(rets_10d), 2) if rets_10d else None
        run.avg_ret_20d = round(sum(rets_20d)/len(rets_20d), 2) if rets_20d else None
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
