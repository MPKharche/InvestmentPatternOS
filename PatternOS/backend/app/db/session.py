from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import get_settings

settings = get_settings()

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        # Best-effort rollback; never let cleanup errors mask the real exception.
        try:
            db.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            db.close()
        except Exception:
            pass
