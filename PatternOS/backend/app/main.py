"""PatternOS — FastAPI application entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.api.routes import universe, patterns, signals, outcomes, analytics, scanner, studio, mf, charts, meta
from app.scheduler.jobs import start_scheduler, stop_scheduler
from app.db.session import SessionLocal
from app.db.canonical_pattern_seed import ensure_canonical_divergence_patterns
from app.db.schema_fixups import ensure_latest_schema
from app.cache.signal_cache import purge_expired_cache

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure DB has columns that newer code expects (safe, idempotent).
    try:
        ensure_latest_schema()
    except Exception as e:
        print(f"[DB] Schema fixup warning: {e}")

    # Startup: cache cleanup + canonical MACD/RSI divergence patterns (idempotent)
    db = SessionLocal()
    try:
        try:
            expired_count = purge_expired_cache(db)
            if expired_count > 0:
                print(f"[Cache] Purged {expired_count} expired screening results on startup")
            else:
                print("[Cache] No expired entries to purge on startup")
        except Exception as e:
            print(f"[Cache] Startup cleanup error: {e}")
        try:
            for line in ensure_canonical_divergence_patterns(db):
                print(f"[Seed] {line}")
        except Exception as e:
            print(f"[Seed] Canonical divergence patterns (MACD/RSI): {e}")
    finally:
        db.close()

    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="PatternOS API",
    version="0.1.0",
    description="AI-powered chart pattern recognition & signal intelligence system",
    debug=(settings.APP_ENV == "development"),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all routers
app.include_router(universe.router,  prefix="/api/v1")
app.include_router(patterns.router,  prefix="/api/v1")
app.include_router(signals.router,   prefix="/api/v1")
app.include_router(outcomes.router,  prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(scanner.router,   prefix="/api/v1")
app.include_router(studio.router,    prefix="/api/v1")
app.include_router(mf.router,        prefix="/api/v1")
app.include_router(charts.router,    prefix="/api/v1")
app.include_router(meta.router,      prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}
