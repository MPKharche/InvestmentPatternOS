"""
vectorbt 0.26.x imports telegram.error.Unauthorized, removed in python-telegram-bot v20+.
Shim the legacy name so optional vectorbt imports work alongside PTB v21.
"""

_applied = False


def apply_vectorbt_ptb_compat() -> None:
    global _applied
    if _applied:
        return
    _applied = True
    try:
        import telegram.error as te  # type: ignore
    except Exception:
        return
    if getattr(te, "Unauthorized", None) is not None:
        return
    try:
        forbidden = te.Forbidden
    except Exception:
        return

    class Unauthorized(forbidden):  # type: ignore[misc, valid-type]
        """Legacy alias expected by vectorbt.messaging.telegram."""

    te.Unauthorized = Unauthorized  # type: ignore[attr-defined]
