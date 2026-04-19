"""
Screener engine — evaluates saved criteria against symbol universe.

Process:
  1. Load ScreenerCriteria from DB
  2. Resolve symbol list from scope (nifty50, nifty500, custom)
  3. For each symbol:
       a. Fetch OHLCV data (from yfinance cache or live)
       b. Compute indicators (TA)
       c. Fetch fundamentals (if needed)
       d. Merge into unified data dict
       e. Evaluate all conditions
       f. Compute score
       g. Cache result (avoid re-scan within 24h unless forced)
  4. Audit log run stats
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
import logging

import pandas as pd
import numpy as np

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.session import SessionLocal
from app.db.models import Universe, ScreenerCriteria, ScreenerResult, ScreenerRun
from app.data.yfinance_client import fetch_stock_prices, get_stock_fundamentals
from app.scanner.indicators import compute_indicators
from app.screener.criteria import evaluate_all_conditions, compute_score

logger = logging.getLogger("patternos.screener")

# Cache TTL for screener results (24h)
CACHE_TTL_HOURS = 24


def _universe_symbols(
    scope: str, asset_class: str, custom_symbols: list | None = None
) -> list[str]:
    """Resolve symbol list based on scope."""
    db = SessionLocal()
    try:
        if scope == "custom" and custom_symbols:
            return [s.upper() for s in custom_symbols if s]

        query = db.query(Universe.symbol).filter(
            Universe.active == True,
            Universe.asset_class == asset_class,
        )
        if scope == "nifty50":
            query = query.filter(Universe.index_name == "Nifty 50")
        elif scope == "nifty500":
            query = query.filter(
                Universe.index_name.in_(
                    [
                        "Nifty 50",
                        "Nifty 500",
                        "Nifty Next 50",
                        "Nifty Midcap 150",
                        "Nifty Smallcap 250",
                    ]
                )
            )

        symbols = [row[0] for row in query.all()]
        return symbols
    finally:
        db.close()


def _is_cache_valid(fetched_at: Optional[datetime]) -> bool:
    if fetched_at is None:
        return False
    now = datetime.now(timezone.utc)
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    return (now - fetched_at) < timedelta(hours=CACHE_TTL_HOURS)


def _prepare_data(symbol: str, days: int = 200) -> tuple[Optional[dict], str]:
    """
    Fetch OHLCV + fundamentals + compute indicators for a symbol.

    Returns:
        (data_dict, error_message) where data_dict contains scalar metric values.
    """
    try:
        # Fetch prices
        df = fetch_stock_prices(symbol, "1d", days, exchange="NSE", use_cache=True)
        if df.empty or len(df) < 50:
            return None, f"Insufficient price data ({len(df)} bars)"

        # Compute indicators
        df = compute_indicators(df)

        # Latest row
        last = df.iloc[-1]

        # Helper: safe float conversion
        def get_float(col: str) -> float | None:
            if col not in df.columns:
                return None
            v = last[col]
            if pd.isna(v):
                return None
            try:
                return float(v)
            except (ValueError, TypeError):
                return None

        data: dict = {
            "symbol": symbol,
            "close": get_float("Close"),
            "open": get_float("Open"),
            "high": get_float("High"),
            "low": get_float("Low"),
            "volume": get_float("Volume"),
            # Technical indicators
            "rsi": get_float("rsi"),
            "sma_20": get_float("sma_20"),
            "sma_50": get_float("sma_50"),
            "sma_200": get_float("sma_200"),
            "ema_20": get_float("ema_20"),
            "ema_50": get_float("ema_50"),
            "ema_200": get_float("ema_200"),
            "macd": get_float("macd"),
            "macd_signal": get_float("macd_signal"),
            "macd_hist": get_float("macd_hist"),
            "bb_upper": get_float("bb_upper"),
            "bb_lower": get_float("bb_lower"),
            "bb_width": get_float("bb_width"),
            "atr": get_float("atr"),
        }

        # Fundamentals (cached)
        try:
            fund = get_stock_fundamentals(symbol, "NSE")
            data.update(
                {
                    "pe": fund.get("pe_ratio"),
                    "pb": fund.get("pb_ratio"),
                    "roe": fund.get("roe"),
                    "debt_to_equity": fund.get("debt_to_equity"),
                    "dividend_yield": fund.get("dividend_yield"),
                    "beta": fund.get("beta"),
                    "market_cap": fund.get("market_cap"),
                    "eps": fund.get("eps"),
                }
            )
        except Exception:
            pass  # non-fatal

        return data, ""
    except Exception as e:
        return None, str(e)


def _sanitize_value(v) -> float | int | str | bool | None:
    """Convert numpy types / NaNs to JSON-safe native types."""
    if v is None:
        return None
    if isinstance(v, (int, str, bool)):
        return v
    if isinstance(v, float):
        if np.isnan(v) or np.isinf(v):
            return None
        return round(v, 6)
    if isinstance(v, (np.int64, np.int32)):
        return int(v)
    if isinstance(v, (np.float64, np.float32)):
        fv = float(v)
        return None if np.isnan(fv) or np.isinf(fv) else round(fv, 6)
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    # Fallback: stringify
    return str(v)


def run_screener(
    screener_id: str,
    timeframe: str = "1d",
    use_cache: bool = True,
    db: Session | None = None,
) -> dict:
    """
    Execute a saved screener criteria against its universe.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        screener = db.query(ScreenerCriteria).filter_by(id=screener_id).first()
        if not screener:
            raise ValueError(f"Screener {screener_id} not found")

        rules = screener.rules_json
        conditions = rules.get("conditions", [])
        logic = rules.get("logic", "AND").upper()

        symbols = _universe_symbols(
            screener.scope, screener.asset_class, screener.custom_symbols
        )
        if not symbols:
            raise ValueError("No symbols in universe")

        # Cache check
        cached_symbols: set[str] = set()
        if use_cache:
            cutoff = datetime.now(timezone.utc).date()
            cached = (
                db.query(ScreenerResult)
                .filter(
                    ScreenerResult.screener_id == screener_id,
                    ScreenerResult.signal_date >= cutoff,
                )
                .all()
            )
            cached_symbols = {r.symbol for r in cached}

        start = datetime.utcnow()
        results = []
        passed_count = 0

        for symbol in symbols:
            if symbol in cached_symbols:
                continue

            data, err = _prepare_data(symbol, days=200)
            if err or data is None:
                logger.warning(f"Skip {symbol}: {err}")
                continue

            # Sector from Universe
            if not data.get("sector"):
                u = db.query(Universe.sector).filter_by(symbol=symbol).first()
                data["sector"] = u[0] if u else None

            passed, metrics = evaluate_all_conditions(data, conditions, logic)
            score = compute_score(data, conditions, logic) if passed else 0.0

            # Sanitize metrics for JSON storage
            clean_metrics = {k: _sanitize_value(v) for k, v in metrics.items()}

            result = ScreenerResult(
                screener_id=screener_id,
                symbol=symbol,
                signal_date=datetime.utcnow().date(),
                metrics_json=clean_metrics,
                passed=passed,
                score=score,
                computed_at=datetime.now(timezone.utc),
            )
            db.add(result)

            if passed:
                passed_count += 1

            results.append(
                {
                    "symbol": symbol,
                    "passed": passed,
                    "score": score,
                    "metrics": clean_metrics,
                }
            )

        db.commit()

        duration = (datetime.utcnow() - start).total_seconds()
        run = ScreenerRun(
            screener_id=screener_id,
            symbols_total=len(symbols),
            symbols_passed=passed_count,
            duration_sec=duration,
            filters_json={"timeframe": timeframe, "use_cache": use_cache},
            status="completed",
        )
        db.add(run)
        db.commit()

        return {
            "run_id": str(run.id),
            "screener_id": screener_id,
            "symbols_total": len(symbols),
            "symbols_passed": passed_count,
            "duration_seconds": duration,
            "results": results,
        }
    finally:
        if close_db:
            db.close()


def get_screener_results(
    screener_id: str,
    limit: int = 100,
    passed_only: bool = False,
    db: Session | None = None,
) -> list[dict]:
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        query = db.query(ScreenerResult).filter_by(screener_id=screener_id)
        if passed_only:
            query = query.filter_by(passed=True)
        rows = query.order_by(ScreenerResult.signal_date.desc()).limit(limit).all()

        out = []
        for r in rows:
            out.append(
                {
                    "id": str(r.id),
                    "symbol": r.symbol,
                    "date": r.signal_date.isoformat(),
                    "passed": r.passed,
                    "score": r.score,
                    "metrics": r.metrics_json or {},
                }
            )
        return out
    finally:
        if close_db:
            db.close()
