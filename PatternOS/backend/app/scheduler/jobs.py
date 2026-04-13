"""
APScheduler background job definitions.
Starts with the FastAPI app via lifespan.
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("patternos.scheduler")

scheduler = AsyncIOScheduler()


def start_scheduler():
    """Register jobs and start the scheduler."""

    @scheduler.scheduled_job(CronTrigger(hour=7, minute=0, timezone="Asia/Kolkata"))
    async def daily_scan_nse():
        """Runs daily at 7:00 AM IST — before NSE market open."""
        logger.info("Running daily NSE scan...")
        from app.db.session import SessionLocal
        from app.scanner.engine import run_scan
        db = SessionLocal()
        try:
            result = await run_scan(db=db)
            logger.info(f"Daily scan complete: {result}")
        finally:
            db.close()

    @scheduler.scheduled_job(CronTrigger(hour="*/6", timezone="Asia/Kolkata"))
    async def cleanup_expired_cache():
        """Runs every 6 hours — clean up expired screening cache entries."""
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

    scheduler.start()
    logger.info("Scheduler started.")


def stop_scheduler():
    scheduler.shutdown(wait=False)
