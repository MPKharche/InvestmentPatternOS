from __future__ import annotations

from datetime import datetime
import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Signal, SignalAlertJournal, TelegramFeedback, TelegramSyncState

settings = get_settings()


def _map_action(action: str) -> str:
    action = action.lower()
    mapping = {
        "watching": "reviewed",
        "traded": "reviewed",
        "useful": "reviewed",
        "skip": "dismissed",
    }
    return mapping.get(action, "pending")


def _get_state(db: Session) -> TelegramSyncState:
    state = db.query(TelegramSyncState).filter_by(id=1).first()
    if not state:
        state = TelegramSyncState(id=1, last_update_id=0, updated_at=datetime.utcnow())
        db.add(state)
        db.flush()
    return state


async def sync_feedback_from_telegram(db: Session) -> int:
    """Pull callback updates from Telegram and persist user feedback actions."""
    if not settings.TELEGRAM_BOT_TOKEN:
        return 0

    state = _get_state(db)
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {"offset": state.last_update_id + 1, "timeout": 0}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(url, params=params)
    data = resp.json()
    if not data.get("ok"):
        return 0

    processed = 0
    for upd in data.get("result", []):
        state.last_update_id = max(state.last_update_id, int(upd.get("update_id", 0)))
        cbq = upd.get("callback_query")
        if not cbq:
            continue
        callback_data = cbq.get("data", "")
        parts = callback_data.split(":")
        if len(parts) != 3 or parts[0] != "signal":
            continue
        signal_id = parts[1]
        action = parts[2]

        signal = db.query(Signal).filter_by(id=signal_id).first()
        if not signal:
            continue

        message = cbq.get("message", {})
        message_id = str(message.get("message_id")) if message.get("message_id") is not None else None
        chat_id = str(message.get("chat", {}).get("id")) if message.get("chat") else None
        alert = None
        if message_id:
            q = db.query(SignalAlertJournal).filter(SignalAlertJournal.telegram_message_id == message_id)
            if chat_id:
                q = q.filter(SignalAlertJournal.telegram_chat_id == chat_id)
            alert = q.first()

        feedback = TelegramFeedback(
            signal_id=signal.id,
            alert_id=alert.id if alert else None,
            action=action,
            username=cbq.get("from", {}).get("username"),
            chat_id=chat_id,
            raw_payload=cbq,
        )
        db.add(feedback)
        signal.status = _map_action(action)
        processed += 1

    db.commit()
    return processed
