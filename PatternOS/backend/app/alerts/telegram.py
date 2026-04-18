from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from statistics import mean
from typing import Any
import random
import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.charts.render import render_equity_chart_png
from app.db.models import Pattern, PatternEvent, Signal, SignalAlertJournal, SignalContext, Universe
from app.scanner.data import fetch_ohlcv

settings = get_settings()


def _avg(values: list[float | None]) -> float | None:
    clean = [v for v in values if v is not None]
    return round(mean(clean), 2) if clean else None


def _market_mood() -> str:
    df = fetch_ohlcv("^NSEI", "1d")
    if df is None or len(df) < 21:
        return "Neutral"
    close = float(df["Close"].iloc[-1])
    prev = float(df["Close"].iloc[-2])
    sma20 = float(df["Close"].tail(20).mean())
    day_ret = ((close - prev) / prev) * 100 if prev else 0.0
    if close > sma20 and day_ret > 0:
        return "Bullish"
    if close < sma20 and day_ret < 0:
        return "Bearish"
    return "Neutral"


def build_alert_payload(
    db: Session,
    signal: Signal,
    pattern: Pattern,
    key_levels: dict[str, Any] | None,
    analysis: str,
    equity_research: dict[str, Any] | None = None,
) -> dict[str, Any]:
    universe_item = db.query(Universe).filter_by(symbol=signal.symbol).first()
    sector = universe_item.sector if universe_item else None
    index_name = universe_item.index_name if universe_item else None

    recent = (
        db.query(PatternEvent)
        .filter(PatternEvent.pattern_id == pattern.id, PatternEvent.symbol == signal.symbol)
        .order_by(PatternEvent.created_at.desc())
        .limit(30)
        .all()
    )
    avg_ret_1w = _avg([e.ret_5d for e in recent])
    avg_ret_1m = _avg([e.ret_20d for e in recent])
    avg_ret_3m = None  # not directly available in current event schema

    payload = {
        "script_name": signal.symbol,
        "pattern_name": pattern.name,
        "confidence_level": round(signal.confidence_score, 2),
        "justified_analysis": analysis,
        "probabilistic_returns": {
            "sample_size": len(recent),
            "avg_return_1w_pct": avg_ret_1w,
            "avg_return_1m_pct": avg_ret_1m,
            "avg_return_3m_pct": avg_ret_3m,
        },
        "analysis_angles": {
            "stock_specific": analysis[:500],
            "sector_angle": sector or "Unknown sector",
            "market_mood": _market_mood(),
            "index_context": index_name or "N/A",
        },
        "trade_guidance": {
            "current_price": key_levels.get("entry") if key_levels else None,
            "estimated_target": key_levels.get("resistance") if key_levels else None,
            "estimated_timeline": signal.timeframe,
            "stop_loss": key_levels.get("stop_loss") if key_levels else None,
        },
        "generated_at": datetime.utcnow().isoformat(),
        "equity_research": equity_research,
    }
    return payload


async def send_telegram_alert(db: Session, signal: Signal, pattern: Pattern, payload: dict[str, Any]) -> SignalAlertJournal:
    """
    Backwards-compatible entrypoint: enqueue + attempt immediate delivery.

    New architecture uses the outbox worker (scheduler job) to deliver queued alerts
    with retries, so alerts aren't missed if Telegram/network is flaky.
    """
    journal = enqueue_telegram_alert(db, signal, payload)
    # Best-effort immediate delivery in dev; outbox will retry if it fails.
    await deliver_telegram_journal(db, journal)
    return journal


def enqueue_telegram_alert(db: Session, signal: Signal, payload: dict[str, Any]) -> SignalAlertJournal:
    journal = SignalAlertJournal(
        signal_id=signal.id,
        channel="telegram",
        payload_json=payload,
        status="queued",
        attempt_count=0,
        next_attempt_at=datetime.utcnow(),
    )
    db.add(journal)
    db.flush()
    return journal


def _backoff_seconds(attempt: int) -> int:
    # Exponential backoff with jitter: 5s -> 10s -> 20s -> 60s -> 5m -> 30m (capped)
    schedule = [5, 10, 20, 60, 300, 1800]
    base = schedule[min(attempt, len(schedule) - 1)]
    jitter = random.randint(0, max(1, int(base * 0.25)))
    return base + jitter


async def deliver_telegram_journal(db: Session, journal: SignalAlertJournal) -> SignalAlertJournal:
    payload = journal.payload_json or {}

    if not settings.TELEGRAM_ALERTS_ENABLED:
        journal.status = "failed"
        journal.last_error = "TELEGRAM_ALERTS_ENABLED=false"
        return journal

    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        journal.status = "failed"
        journal.last_error = "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID"
        payload["delivery_error"] = journal.last_error
        journal.payload_json = payload
        return journal

    message = (
        f"PatternOS Alert\n"
        f"Script: {payload['script_name']}\n"
        f"Pattern: {payload['pattern_name']}\n"
        f"Confidence: {payload['confidence_level']}%\n"
        f"1W/1M/3M avg: {payload['probabilistic_returns']['avg_return_1w_pct']} / "
        f"{payload['probabilistic_returns']['avg_return_1m_pct']} / "
        f"{payload['probabilistic_returns']['avg_return_3m_pct']}\n"
        f"Price: {payload['trade_guidance']['current_price']} | "
        f"Target: {payload['trade_guidance']['estimated_target']} | "
        f"SL: {payload['trade_guidance']['stop_loss']}\n"
        f"Market mood: {payload['analysis_angles']['market_mood']}\n"
        f"Analysis: {payload['justified_analysis'][:700]}"
    )
    eq = payload.get("equity_research") or {}
    if isinstance(eq, dict) and (eq.get("headline") or eq.get("body")):
        message += (
            f"\n\nAI desk ({eq.get('stance', 'view')}): {eq.get('headline', '')}\n"
            f"{(eq.get('body') or '')[:500]}"
        )

    keyboard = {
        "inline_keyboard": [[
            {"text": "Watch", "callback_data": f"signal:{signal.id}:watching"},
            {"text": "Traded", "callback_data": f"signal:{signal.id}:traded"},
            {"text": "Useful", "callback_data": f"signal:{signal.id}:useful"},
            {"text": "Skip", "callback_data": f"signal:{signal.id}:skip"},
        ]]
    }

    try:
        journal.attempt_count = int(journal.attempt_count or 0) + 1
        journal.last_attempt_at = datetime.utcnow()
        # Prefer sending a chart image with caption (more useful than plain text).
        signal = db.query(Signal).filter_by(id=journal.signal_id).first()
        png = None
        if signal:
            try:
                png = await asyncio.to_thread(render_equity_chart_png, signal.symbol, signal.timeframe or "1d", indicators="ema,rsi,macd")
            except Exception:
                png = None

        async with httpx.AsyncClient(timeout=20) as client:
            if png:
                import json as _json
                url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendPhoto"
                caption = message[:900]
                resp = await client.post(
                    url,
                    data={
                        "chat_id": settings.TELEGRAM_CHAT_ID,
                        "caption": caption,
                        "reply_markup": _json.dumps(keyboard),
                    },
                    files={"photo": ("chart.png", png, "image/png")},
                )
            else:
                url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
                resp = await client.post(
                    url,
                    json={
                        "chat_id": settings.TELEGRAM_CHAT_ID,
                        "text": message[:3500],
                        "reply_markup": keyboard,
                    },
                )
        journal.last_http_status = int(resp.status_code)
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(str(data))
        msg = data.get("result", {})
        journal.status = "sent"
        journal.telegram_chat_id = str(msg.get("chat", {}).get("id"))
        journal.telegram_message_id = str(msg.get("message_id"))
        journal.delivered_at = datetime.utcnow()
        journal.next_attempt_at = None
        journal.last_error = None
    except Exception as exc:
        journal.status = "queued"
        journal.last_error = str(exc)[:500]
        payload["delivery_error"] = journal.last_error
        journal.payload_json = payload
        # Schedule retry unless we've exhausted attempts.
        max_attempts = int(settings.TELEGRAM_ALERT_MAX_ATTEMPTS or 10)
        if int(journal.attempt_count or 0) >= max_attempts:
            journal.status = "failed"
            journal.next_attempt_at = None
        else:
            journal.next_attempt_at = datetime.utcnow() + timedelta(seconds=_backoff_seconds(int(journal.attempt_count or 0)))

    return journal


async def deliver_queued_telegram_alerts(db: Session, *, limit: int = 25) -> int:
    """
    Deliver queued Telegram alerts (outbox worker).
    Returns number of successful sends this run.
    """
    now = datetime.utcnow()
    rows = (
        db.query(SignalAlertJournal)
        .filter(SignalAlertJournal.channel == "telegram")
        .filter(SignalAlertJournal.status == "queued")
        .filter((SignalAlertJournal.next_attempt_at.is_(None)) | (SignalAlertJournal.next_attempt_at <= now))
        .order_by(SignalAlertJournal.created_at.asc())
        .limit(limit)
        .all()
    )
    sent = 0
    for j in rows:
        await deliver_telegram_journal(db, j)
        if j.status == "sent":
            sent += 1
    db.commit()
    return sent


def reconcile_today_telegram_outbox(db: Session) -> int:
    """
    Safety net: ensure any signal created today has an outbox row.
    This prevents missed alerts if the scanner process crashed between writing the Signal and enqueuing.
    """
    if not settings.TELEGRAM_ALERTS_ENABLED:
        return 0

    today = datetime.utcnow().date()
    start = datetime(today.year, today.month, today.day)
    end = start + timedelta(days=1)

    signals = (
        db.query(Signal)
        .filter(Signal.triggered_at >= start, Signal.triggered_at < end)
        .order_by(Signal.triggered_at.asc())
        .all()
    )

    added = 0
    for s in signals:
        exists = db.query(SignalAlertJournal).filter_by(signal_id=s.id, channel="telegram").first()
        if exists:
            continue
        pat = db.query(Pattern).filter_by(id=s.pattern_id).first()
        if not pat:
            continue
        ctx = db.query(SignalContext).filter_by(signal_id=s.id).first()
        key_levels = (ctx.key_levels if ctx else None) or None
        analysis = (ctx.llm_analysis if ctx else None) or ""
        equity_note = (ctx.equity_research_note if ctx else None) or None
        payload = build_alert_payload(db, s, pat, key_levels, analysis, equity_research=equity_note)
        enqueue_telegram_alert(db, s, payload)
        added += 1

    db.commit()
    return added
