from __future__ import annotations

from datetime import datetime
from statistics import mean
from typing import Any
import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Pattern, PatternEvent, Signal, SignalAlertJournal, Universe
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
    journal = SignalAlertJournal(signal_id=signal.id, channel="telegram", payload_json=payload, status="queued")
    db.add(journal)
    db.flush()

    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        journal.status = "failed"
        payload["delivery_error"] = "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID"
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

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                json={
                    "chat_id": settings.TELEGRAM_CHAT_ID,
                    "text": message,
                    "reply_markup": keyboard,
                },
            )
        data = resp.json()
        if not data.get("ok"):
            journal.status = "failed"
            payload["delivery_error"] = str(data)
            journal.payload_json = payload
            return journal
        msg = data.get("result", {})
        journal.status = "sent"
        journal.telegram_chat_id = str(msg.get("chat", {}).get("id"))
        journal.telegram_message_id = str(msg.get("message_id"))
        journal.delivered_at = datetime.utcnow()
    except Exception as exc:
        journal.status = "failed"
        payload["delivery_error"] = str(exc)
        journal.payload_json = payload

    return journal
