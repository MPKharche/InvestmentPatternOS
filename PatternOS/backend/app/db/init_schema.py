"""
Database schema initialization script.
Run this once after adding new models to create the tables.

Usage:
    python -c "from app.db.init_schema import init_db; init_db()"
"""
from app.db.session import engine, Base
from app.db.models import (
    Universe, Pattern, PatternVersion, Signal, SignalContext,
    Review, Outcome, LearningLog, PatternChat, PatternEvent,
    BacktestRun, PatternStudy, ScreeningCache
)


def init_db():
    """Create all tables in the database."""
    print("Creating database schema...")
    Base.metadata.create_all(bind=engine)
    print("[SUCCESS] Database schema initialized successfully!")


if __name__ == "__main__":
    init_db()
