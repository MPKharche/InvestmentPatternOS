"""
Signal screening cache manager.

Provides caching for LLM screening results with 24-hour TTL.
Reduces LLM calls by ~30-40% for repeated symbol+pattern combinations.
"""
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.db.models import ScreeningCache


CACHE_TTL_HOURS = 24  # Cache expires after 24 hours


def get_cached_screening(
    pattern_id: str,
    symbol: str,
    timeframe: str,
    db: Session,
) -> tuple[float, str] | None:
    """
    Retrieve cached LLM screening result if valid.
    Returns (adjusted_score, analysis_text) or None if not cached/expired.
    """
    cache = db.query(ScreeningCache).filter_by(
        pattern_id=pattern_id,
        symbol=symbol,
        timeframe=timeframe,
    ).first()

    if not cache:
        return None

    # Check if cache has expired
    now = datetime.now(timezone.utc)
    cached_at = cache.cached_at
    if cached_at.tzinfo is None:
        cached_at = cached_at.replace(tzinfo=timezone.utc)

    age = now - cached_at
    if age > timedelta(hours=CACHE_TTL_HOURS):
        # Expired — delete it
        db.delete(cache)
        db.commit()
        return None

    return float(cache.adjusted_score), cache.analysis_text


def store_screening_result(
    pattern_id: str,
    symbol: str,
    timeframe: str,
    base_score: float,
    adjusted_score: float,
    analysis_text: str,
    db: Session,
) -> None:
    """
    Store or update LLM screening result in cache.
    Overwrites previous cache entry for same pattern+symbol+timeframe.
    """
    now = datetime.now(timezone.utc)

    # Check if cache entry exists
    existing = db.query(ScreeningCache).filter_by(
        pattern_id=pattern_id,
        symbol=symbol,
        timeframe=timeframe,
    ).first()

    if existing:
        # Update existing cache
        existing.base_score = base_score
        existing.adjusted_score = adjusted_score
        existing.analysis_text = analysis_text
        existing.cached_at = now
    else:
        # Create new cache entry
        cache = ScreeningCache(
            pattern_id=pattern_id,
            symbol=symbol,
            timeframe=timeframe,
            base_score=base_score,
            adjusted_score=adjusted_score,
            analysis_text=analysis_text,
            cached_at=now,
        )
        db.add(cache)

    db.commit()


def purge_expired_cache(db: Session) -> int:
    """
    Remove all expired cache entries (>24 hours old).
    Called periodically (e.g., every 6 hours) or on startup.
    Returns number of deleted entries.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=CACHE_TTL_HOURS)
    count = db.query(ScreeningCache).filter(ScreeningCache.cached_at < cutoff).delete()
    db.commit()
    return count
