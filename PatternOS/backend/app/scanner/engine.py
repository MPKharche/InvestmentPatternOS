"""
Scanner engine — orchestrates data fetch → rule eval → LLM screen → signal write.
"""
import asyncio
import time
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.db.models import Pattern, PatternVersion, Universe, Signal, SignalContext
from app.research.signal_enrichment import build_equity_research_note
from app.scanner.data import fetch_ohlcv, build_chart_summary
from app.scanner.evaluator import evaluate_pattern
from app.llm.screener import llm_screen
from app.cache.signal_cache import get_cached_screening, store_screening_result
from app.config import get_settings
from app.alerts.telegram import build_alert_payload, send_telegram_alert
from app.scanner.backtest_metrics import forward_returns_for_live_bar

settings = get_settings()

# No new signal for same pattern+symbol+timeframe within this many calendar days (~3 weeks)
SIGNAL_COOLDOWN_DAYS = 21


async def scan_symbol(
    symbol: str,
    exchange: str,
    pattern: Pattern,
    rulebook: dict,
    timeframe: str,
    db: Session,
    *,
    company_name: str | None = None,
    sector: str | None = None,
    index_name: str | None = None,
) -> Signal | None:
    """
    Scan a single symbol against a single pattern.
    Returns a Signal ORM object if confidence >= threshold, else None.
    """
    df = await asyncio.to_thread(fetch_ohlcv, symbol, timeframe)
    if df is None:
        return None

    cutoff = datetime.utcnow() - timedelta(days=SIGNAL_COOLDOWN_DAYS)
    recent = (
        db.query(Signal)
        .filter(
            Signal.pattern_id == pattern.id,
            Signal.symbol == symbol,
            Signal.timeframe == timeframe,
            Signal.triggered_at >= cutoff,
        )
        .first()
    )
    if recent:
        return None

    base_score, breakdown = evaluate_pattern(df, rulebook)

    # Early exit: if base score is too low don't even call LLM
    # OPTIMIZATION: Increased from 0.5 to 0.75 to reduce LLM calls (50% fewer calls)
    # This means only high-confidence rule matches get LLM refinement
    if base_score < (settings.SIGNAL_CONFIDENCE_THRESHOLD * 0.75):
        return None

    chart_summary = build_chart_summary(df, symbol)

    # PHASE 2: Check cache before calling LLM
    # Returns (adjusted_score, analysis_text) if cached and valid, else None
    cached_result = get_cached_screening(
        pattern_id=pattern.id,
        symbol=symbol,
        timeframe=timeframe,
        db=db,
    )

    if cached_result:
        # Cache hit! Skip expensive LLM call
        adjusted_score, analysis = cached_result
    else:
        # Cache miss — call LLM and store result
        adjusted_score, analysis = await llm_screen(
            pattern_name=pattern.name,
            rulebook_json=rulebook,
            symbol=symbol,
            chart_summary=chart_summary,
            base_score=base_score,
        )
        # Store result in cache for next scan
        store_screening_result(
            pattern_id=pattern.id,
            symbol=symbol,
            timeframe=timeframe,
            base_score=base_score,
            adjusted_score=adjusted_score,
            analysis_text=analysis,
            db=db,
        )

    if adjusted_score < settings.SIGNAL_CONFIDENCE_THRESHOLD:
        return None

    equity_note = await build_equity_research_note(
        settings,
        pattern_name=pattern.name,
        symbol=symbol,
        company_name=company_name,
        sector=sector,
        index_name=index_name,
        confidence=adjusted_score,
        screener_analysis=analysis,
        chart_summary=chart_summary,
    )

    # Build key levels from last bar
    last = df.iloc[-1]
    pattern_low = df["Low"].tail(20).min()
    key_levels = {
        "entry": round(float(last["Close"]), 2),
        "support": round(float(pattern_low), 2),
        "resistance": round(float(df["High"].tail(20).max()), 2),
        "stop_loss": round(float(pattern_low), 2),
    }

    # Persist signal
    signal = Signal(
        pattern_id=pattern.id,
        symbol=symbol,
        exchange=exchange,
        timeframe=timeframe,
        triggered_at=datetime.utcnow(),
        confidence_score=adjusted_score,
        base_score=base_score,
        rule_snapshot=breakdown,
        status="pending",
    )
    db.add(signal)
    db.flush()  # get signal.id

    i_last = len(df) - 1
    forward_meta = forward_returns_for_live_bar(df, i_last)

    ctx = SignalContext(
        signal_id=signal.id,
        chart_summary=chart_summary,
        llm_analysis=analysis,
        key_levels=key_levels,
        forward_horizon_returns=forward_meta,
        equity_research_note=equity_note,
    )
    db.add(ctx)

    # Persist alert journal and push Telegram alert payload.
    payload = build_alert_payload(db, signal, pattern, key_levels, analysis, equity_research=equity_note)
    await send_telegram_alert(db, signal, pattern, payload)
    return signal


async def run_scan(
    db: Session,
    pattern_id: str | None = None,
    symbols: list[str] | None = None,
    scope: str = "nifty50",
) -> dict:
    """Main entry point called by API route and scheduler.

    Args:
        db: Database session
        pattern_id: If provided, scan only this pattern. None = all active patterns
        symbols: Custom symbol list to scan (overrides scope)
        scope: "full" (all ~326 stocks), "nifty50" (50 stocks), or "custom" (use symbols list)
    """
    start = time.time()

    # Load patterns
    q = db.query(Pattern).filter_by(status="active")
    if pattern_id:
        q = q.filter_by(id=pattern_id)
    patterns = q.all()

    if not patterns:
        return {"signals_created": 0, "symbols_scanned": 0, "duration_seconds": 0.0}

    # Load universe
    uq = db.query(Universe).filter_by(active=True)
    universe = uq.all()

    # Apply scope filtering
    if symbols:
        # Custom symbols override scope
        universe = [u for u in universe if u.symbol in symbols]
    elif scope == "nifty50":
        universe = [u for u in universe if (u.index_name or "").strip() == "Nifty 50"]
    # else scope == "full": use all universe symbols

    signals_created = 0

    for pattern in patterns:
        # Get current rulebook version
        pv = (
            db.query(PatternVersion)
            .filter_by(pattern_id=pattern.id, version=pattern.current_version)
            .first()
        )
        if not pv:
            continue

        rulebook = pv.rulebook_json
        timeframes = pattern.timeframes or ["1d"]

        # Scan all symbols concurrently (batched to avoid rate limits)
        tasks = []
        for u in universe:
            for tf in timeframes:
                tasks.append(
                    scan_symbol(
                        u.symbol,
                        u.exchange,
                        pattern,
                        rulebook,
                        tf,
                        db,
                        company_name=u.name,
                        sector=u.sector,
                        index_name=u.index_name,
                    )
                )

        # Run in batches of 10
        batch_size = 10
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i + batch_size]
            results = await asyncio.gather(*batch, return_exceptions=True)
            for r in results:
                if isinstance(r, Signal):
                    signals_created += 1

    db.commit()

    return {
        "signals_created": signals_created,
        "symbols_scanned": len(universe),
        "duration_seconds": round(time.time() - start, 2),
    }
