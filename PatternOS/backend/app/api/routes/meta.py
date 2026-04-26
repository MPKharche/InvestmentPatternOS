from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings


router = APIRouter(prefix="/meta", tags=["meta"])
settings = get_settings()


def _has(mod: str) -> bool:
    try:
        if mod == "vectorbt":
            from app.compat.vectorbt_shim import apply_vectorbt_ptb_compat

            apply_vectorbt_ptb_compat()
        __import__(mod)
        return True
    except Exception:
        return False


@router.get("/capabilities")
def capabilities():
    return {
        "optional": {
            "talib": _has("talib"),
            "vectorbt": _has("vectorbt"),
            "mplfinance": _has("mplfinance"),
        },
        "telegram": {
            "mode": settings.TELEGRAM_MODE,
            "alerts_enabled": settings.TELEGRAM_ALERTS_ENABLED,
            "bot_token_configured": bool(settings.TELEGRAM_BOT_TOKEN),
        },
        "llm": {
            "disabled": bool(settings.LLM_DISABLED),
            "openrouter_key_configured": bool(settings.OPENROUTER_API_KEY),
        },
    }

