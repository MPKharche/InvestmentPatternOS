"""
APScheduler background job definitions.
Starts with the FastAPI app via lifespan.
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.config import get_settings

logger = logging.getLogger("patternos.scheduler")

scheduler = AsyncIOScheduler()
settings = get_settings()


def start_scheduler():
    """Register jobs and start the scheduler."""

    @scheduler.scheduled_job(CronTrigger(hour=7, minute=0, timezone="Asia/Kolkata"))
    async def daily_scan_nse():
        """Runs daily at 7:00 AM IST — before NSE market open."""
        logger.info("Running daily NSE scan...")
        if settings.TELEGRAM_MODE.strip().lower() == "polling":
            return
        from app.db.session import SessionLocal
        from app.scanner.engine import run_scan
        db = SessionLocal()
        try:
            result = await run_scan(db=db)
            logger.info(f"Daily scan complete: {result}")
        finally:
            db.close()

    @scheduler.scheduled_job(CronTrigger(hour="*/12", timezone="Asia/Kolkata"))
    async def cleanup_expired_cache():
        """Runs every 12 hours — clean up expired screening cache entries."""
        logger.debug("Running cache cleanup...")
        from app.db.session import SessionLocal
        from app.cache.signal_cache import purge_expired_cache
        db = SessionLocal()
        try:
            count = purge_expired_cache(db)
            if count > 0:
                logger.info(f"Cache cleanup: purged {count} expired entries")
            else:
                logger.debug("Cache cleanup: no expired entries")
        finally:
            db.close()

    @scheduler.scheduled_job(CronTrigger(minute="*/15", timezone="Asia/Kolkata"))
    async def sync_telegram_feedback_job():
        """Runs every 15 minutes — import Telegram button feedback (only if a bot token is set)."""
        if not (settings.TELEGRAM_BOT_TOKEN or "").strip():
            return
        from app.db.session import SessionLocal
        from app.alerts.feedback_sync import sync_feedback_from_telegram
        db = SessionLocal()
        try:
            processed = await sync_feedback_from_telegram(db)
            if processed:
                logger.info(f"Telegram feedback sync: processed {processed} callback updates")
        finally:
            db.close()

    @scheduler.scheduled_job(CronTrigger(minute="*/3", timezone="Asia/Kolkata"))
    async def deliver_telegram_outbox_job():
        """Runs every 3 minutes — deliver queued Telegram alerts with retries."""
        if not settings.TELEGRAM_ALERTS_ENABLED:
            return
        from app.db.session import SessionLocal
        from app.alerts.telegram import deliver_queued_telegram_alerts
        db = SessionLocal()
        try:
            sent = await deliver_queued_telegram_alerts(db, limit=25)
            if sent:
                logger.info(f"Telegram outbox: delivered {sent} alerts")
        finally:
            db.close()

    @scheduler.scheduled_job(CronTrigger(hour=7, minute=15, timezone="Asia/Kolkata"))
    async def reconcile_telegram_outbox_daily():
        """Runs daily after scan — ensure today's signals have an outbox row to deliver."""
        if not settings.TELEGRAM_ALERTS_ENABLED:
            return
        from app.db.session import SessionLocal
        from app.alerts.telegram import reconcile_today_telegram_outbox
        db = SessionLocal()
        try:
            added = reconcile_today_telegram_outbox(db)
            if added:
                logger.info(f"Telegram outbox reconcile: enqueued {added} missing alerts for today")
        finally:
            db.close()

    @scheduler.scheduled_job(CronTrigger(hour=18, minute=30, timezone="Asia/Kolkata"))
    async def daily_mf_nav_ingest():
        """Runs daily at 6:30 PM IST — ingest AMFI NAVAll and compute MF signals for monitored schemes."""
        if not settings.MF_INGESTION_ENABLED:
            logger.info("MF ingestion disabled (MF_INGESTION_ENABLED=false); skipping NAV ingest.")
            return
        logger.info("Running MF daily NAV ingest...")
        from app.db.session import SessionLocal
        from app.mf.pipelines import ingest_amfi_navall
        db = SessionLocal()
        try:
            stats = ingest_amfi_navall(db)
            logger.info(f"MF NAV ingest complete: {stats}")
        finally:
            db.close()

    @scheduler.scheduled_job(CronTrigger(day=7, hour=19, minute=0, timezone="Asia/Kolkata"))
    async def monthly_mf_holdings_ingest():
        """Runs monthly (7th) — fetch holdings snapshots for monitored MF families and compute portfolio signals."""
        if not settings.MF_INGESTION_ENABLED or not settings.MF_HOLDINGS_ENABLED:
            logger.info("MF holdings disabled; skipping holdings ingest (day 7).")
            return
        logger.info("Running MF monthly holdings ingest (day 7)...")
        from app.db.session import SessionLocal
        from app.mf.pipelines import ingest_monthly_holdings
        db = SessionLocal()
        try:
            stats = ingest_monthly_holdings(db)
            logger.info(f"MF holdings ingest complete: {stats}")
        finally:
            db.close()

    @scheduler.scheduled_job(CronTrigger(day=10, hour=19, minute=0, timezone="Asia/Kolkata"))
    async def monthly_mf_holdings_retry():
        """Retry holdings ingest (day 10) to catch delayed AMC disclosures."""
        if not settings.MF_INGESTION_ENABLED or not settings.MF_HOLDINGS_ENABLED:
            logger.info("MF holdings disabled; skipping holdings ingest retry (day 10).")
            return
        logger.info("Running MF monthly holdings ingest retry (day 10)...")
        from app.db.session import SessionLocal
        from app.mf.pipelines import ingest_monthly_holdings
        db = SessionLocal()
        try:
            stats = ingest_monthly_holdings(db)
            logger.info(f"MF holdings ingest retry complete: {stats}")
        finally:
            db.close()

    scheduler.start()
    logger.info("Scheduler started.")


def stop_scheduler():
    if not scheduler.running:
        return
    scheduler.shutdown(wait=False)
