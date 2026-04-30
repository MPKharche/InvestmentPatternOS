"""
Fire-and-forget HTTP notifications to n8n (or any webhook URL).
Does not raise into the signal / scan path on failure.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger("patternos.integrations")

SYNC_TIMEOUT = 8.0


def _headers() -> dict[str, str]:
    s = get_settings()
    h = {"Content-Type": "application/json"}
    sec = (s.N8N_WEBHOOK_SECRET or "").strip()
    if sec:
        h["X-PatternOS-Secret"] = sec
    return h


def _webhook_url() -> str:
    return (get_settings().N8N_WEBHOOK_URL or "").strip()


def emit_patternos_event_sync(event_type: str, payload: dict[str, Any]) -> None:
    """Sync POST for callers outside async (e.g. MF pipelines)."""
    url = _webhook_url()
    if not url:
        return
    body = {"event": event_type, "payload": payload}
    try:
        httpx.post(url, json=body, headers=_headers(), timeout=SYNC_TIMEOUT)
    except Exception as exc:
        logger.debug("webhook emit skipped/failed: %s", exc)


async def emit_patternos_event(event_type: str, payload: dict[str, Any]) -> None:
    """Async POST from scanner / async routes."""
    url = _webhook_url()
    if not url:
        return
    body = {"event": event_type, "payload": payload}
    try:
        async with httpx.AsyncClient(timeout=SYNC_TIMEOUT) as client:
            await client.post(url, json=body, headers=_headers())
    except Exception as exc:
        logger.debug("webhook emit skipped/failed: %s", exc)
