from __future__ import annotations

import asyncio
from io import BytesIO

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from app.charts.render import render_equity_chart_png, render_mf_nav_chart_png
from app.config import get_settings
from app.db.models import (
    MFNavDaily,
    MFScheme,
    MFSignal,
    Signal,
    SignalAlertJournal,
    TelegramFeedback,
)
from app.db.session import SessionLocal


settings = get_settings()


def _is_allowed(update: Update) -> bool:
    chat = update.effective_chat
    user = update.effective_user
    if not chat:
        return False
    chat_id = str(chat.id)
    allowed_chats = settings.telegram_allowed_chat_ids
    if allowed_chats and chat_id not in allowed_chats:
        return False
    allowed_users = settings.telegram_allowed_usernames
    if allowed_users:
        username = (user.username or "").lstrip("@") if user else ""
        if not username or username not in allowed_users:
            return False
    return True


async def _deny(update: Update) -> None:
    try:
        if update.message:
            await update.message.reply_text("Not authorized for this bot.")
    except Exception:
        pass


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        await _deny(update)
        return
    text = (
        "*PatternOS Bot*\n\n"
        "Commands:\n"
        "- `/chart SYMBOL [tf] [inds]` e.g. `/chart AXISBANK.NS 1d ema,rsi,macd`\n"
        "- `/signal SYMBOL` latest PatternOS signal\n"
        "- `/mf SCHEME_CODE` MF facts + latest NAV date + recent MF signals\n"
        "- `/mfchart SCHEME_CODE [inds]` e.g. `/mfchart 119551 ema,rsi,macd`\n"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_chart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        await _deny(update)
        return
    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: /chart SYMBOL [tf] [inds]")
        return
    symbol = args[0].strip()
    tf = args[1].strip() if len(args) >= 2 else "1d"
    inds = args[2].strip() if len(args) >= 3 else "ema,rsi,macd"
    try:
        png = await asyncio.to_thread(render_equity_chart_png, symbol, tf, indicators=inds)
    except Exception as exc:
        await update.message.reply_text(f"Chart failed: {exc}")
        return
    bio = BytesIO(png)
    bio.name = f"{symbol}.png"
    await update.message.reply_photo(photo=bio, caption=f"{symbol} ({tf})  inds={inds}")


async def cmd_signal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        await _deny(update)
        return
    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: /signal SYMBOL")
        return
    symbol = args[0].strip()
    db = SessionLocal()
    try:
        s = db.query(Signal).filter_by(symbol=symbol).order_by(Signal.triggered_at.desc()).first()
        if not s:
            await update.message.reply_text("No signals found.")
            return
        msg = (
            f"*Latest Signal*\n"
            f"Symbol: `{s.symbol}`\n"
            f"Pattern: `{s.pattern_id}`\n"
            f"Timeframe: `{s.timeframe}`\n"
            f"Confidence: *{round(float(s.confidence_score), 2)}%*\n"
            f"Triggered: `{s.triggered_at.isoformat() if s.triggered_at else ''}`\n"
            f"Status: `{s.status}`"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    finally:
        db.close()


async def cmd_mf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        await _deny(update)
        return
    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: /mf SCHEME_CODE")
        return
    try:
        scheme_code = int(args[0].strip())
    except Exception:
        await update.message.reply_text("Invalid scheme code.")
        return

    db = SessionLocal()
    try:
        s = db.query(MFScheme).filter_by(scheme_code=scheme_code).first()
        if not s:
            await update.message.reply_text("Scheme not found.")
            return
        latest_nav = db.query(MFNavDaily).filter_by(scheme_code=scheme_code).order_by(MFNavDaily.nav_date.desc()).first()
        sigs = (
            db.query(MFSignal)
            .filter_by(scheme_code=scheme_code)
            .order_by(MFSignal.triggered_at.desc())
            .limit(5)
            .all()
        )
        lines = [
            f"*{s.scheme_name or scheme_code}*",
            f"Scheme: `{scheme_code}`",
            f"AMC: `{(s.amc_name or '').strip()}`",
            f"Category: `{(s.category or '').strip()}`",
            f"Monitored: `{bool(s.monitored)}`",
        ]
        if latest_nav:
            lines.append(f"Latest NAV: *{float(latest_nav.nav):.4f}* on `{latest_nav.nav_date.isoformat()}`")
        if sigs:
            lines.append("\n*Recent MF signals:*")
            for x in sigs:
                lines.append(f"- `{x.signal_type}` {x.confidence_score:.1f}% on `{x.nav_date.isoformat()}`")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    finally:
        db.close()


async def cmd_mfchart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        await _deny(update)
        return
    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: /mfchart SCHEME_CODE [inds]")
        return
    try:
        scheme_code = int(args[0].strip())
    except Exception:
        await update.message.reply_text("Invalid scheme code.")
        return
    inds = args[1].strip() if len(args) >= 2 else "ema,rsi,macd"

    db = SessionLocal()
    try:
        scheme = db.query(MFScheme).filter_by(scheme_code=scheme_code).first()
        if not scheme:
            await update.message.reply_text("Scheme not found.")
            return
        rows = (
            db.query(MFNavDaily)
            .filter_by(scheme_code=scheme_code)
            .order_by(MFNavDaily.nav_date.asc())
            .limit(2000)
            .all()
        )
        points = [(r.nav_date.isoformat(), float(r.nav)) for r in rows]
        png = await asyncio.to_thread(render_mf_nav_chart_png, points, scheme.scheme_name or str(scheme_code), indicators=inds)
    except Exception as exc:
        await update.message.reply_text(f"MF chart failed: {exc}")
        return
    finally:
        db.close()

    bio = BytesIO(png)
    bio.name = f"MF_{scheme_code}.png"
    await update.message.reply_photo(photo=bio, caption=f"{scheme_code}  inds={inds}")


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        await _deny(update)
        return
    q = update.callback_query
    if not q:
        return
    data = (q.data or "").strip()
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "signal":
        await q.answer()
        return
    signal_id = parts[1]
    action = parts[2]

    db = SessionLocal()
    try:
        s = db.query(Signal).filter_by(id=signal_id).first()
        if not s:
            await q.answer("Signal not found", show_alert=False)
            return
        # Best-effort map to existing semantics
        if action in ("watching", "traded", "useful"):
            s.status = "reviewed"
        elif action == "skip":
            s.status = "dismissed"

        msg = q.message
        message_id = str(msg.message_id) if msg else None
        chat_id = str(msg.chat.id) if (msg and msg.chat) else None
        alert = None
        if message_id:
            aq = db.query(SignalAlertJournal).filter(SignalAlertJournal.telegram_message_id == message_id)
            if chat_id:
                aq = aq.filter(SignalAlertJournal.telegram_chat_id == chat_id)
            alert = aq.first()

        fb = TelegramFeedback(
            signal_id=s.id,
            alert_id=alert.id if alert else None,
            action=action,
            username=(q.from_user.username if q.from_user else None),
            chat_id=chat_id,
            raw_payload={"data": data},
        )
        db.add(fb)
        db.commit()
        await q.answer("Saved")
    finally:
        db.close()


def main() -> None:
    if not settings.TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")
    if settings.TELEGRAM_MODE.strip().lower() != "polling":
        raise RuntimeError("TELEGRAM_MODE must be 'polling' to run worker")

    app = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("chart", cmd_chart))
    app.add_handler(CommandHandler("signal", cmd_signal))
    app.add_handler(CommandHandler("mf", cmd_mf))
    app.add_handler(CommandHandler("mfchart", cmd_mfchart))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

