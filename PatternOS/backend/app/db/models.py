"""SQLAlchemy ORM models — mirror the SQL schema exactly."""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, String, Boolean, Integer, Float, Text,
    DateTime, ForeignKey, ARRAY, JSON, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.db.session import Base


def _uuid():
    return str(uuid.uuid4())


class Universe(Base):
    __tablename__ = "universe"
    id          = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    symbol      = Column(String(20), nullable=False)
    exchange    = Column(String(20), nullable=False, default="NSE")
    asset_class = Column(String(30), nullable=False, default="equity")
    name        = Column(String(100))
    active      = Column(Boolean, nullable=False, default=True)
    sector      = Column(String(50), nullable=True)
    index_name  = Column(String(50), nullable=True)   # e.g. "Nifty 50", "Nifty Next 50", "Nifty Midcap 150", "Nifty Smallcap 250"
    created_at  = Column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("symbol", "exchange"),)


class Pattern(Base):
    __tablename__ = "patterns"
    id              = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name            = Column(String(100), nullable=False, unique=True)
    description     = Column(Text)
    asset_class     = Column(String(30), default="equity")
    timeframes      = Column(ARRAY(String), default=["1d"])
    status          = Column(String(20), nullable=False, default="active")
    current_version = Column(Integer, nullable=False, default=1)
    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at      = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    versions  = relationship("PatternVersion", back_populates="pattern", cascade="all, delete-orphan")
    signals   = relationship("Signal", back_populates="pattern")
    chat      = relationship("PatternChat", back_populates="pattern", cascade="all, delete-orphan")
    learning  = relationship("LearningLog", back_populates="pattern", cascade="all, delete-orphan")
    candidates = relationship("PatternCandidate", back_populates="linked_pattern")


class PatternVersion(Base):
    __tablename__ = "pattern_versions"
    id             = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    pattern_id     = Column(UUID(as_uuid=False), ForeignKey("patterns.id", ondelete="CASCADE"), nullable=False)
    version        = Column(Integer, nullable=False)
    rulebook_json  = Column(JSONB, nullable=False)
    change_summary = Column(Text)
    approved_at    = Column(DateTime(timezone=True))
    created_at     = Column(DateTime(timezone=True), default=datetime.utcnow)

    pattern = relationship("Pattern", back_populates="versions")
    __table_args__ = (UniqueConstraint("pattern_id", "version"),)


class Signal(Base):
    __tablename__ = "signals"
    id               = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    pattern_id       = Column(UUID(as_uuid=False), ForeignKey("patterns.id"), nullable=False)
    symbol           = Column(String(20), nullable=False)
    exchange         = Column(String(20), nullable=False, default="NSE")
    timeframe        = Column(String(10), nullable=False, default="1d")
    triggered_at     = Column(DateTime(timezone=True), default=datetime.utcnow)
    confidence_score = Column(Float, nullable=False)
    base_score       = Column(Float)
    rule_snapshot    = Column(JSONB)
    status           = Column(String(20), nullable=False, default="pending")

    pattern = relationship("Pattern", back_populates="signals")
    context = relationship("SignalContext", back_populates="signal", uselist=False, cascade="all, delete-orphan")
    review  = relationship("Review", back_populates="signal", uselist=False, cascade="all, delete-orphan")
    outcome = relationship("Outcome", back_populates="signal", uselist=False, cascade="all, delete-orphan")


class SignalContext(Base):
    __tablename__ = "signal_context"
    id            = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    signal_id     = Column(UUID(as_uuid=False), ForeignKey("signals.id", ondelete="CASCADE"), nullable=False, unique=True)
    chart_summary = Column(Text)
    llm_analysis  = Column(Text)
    key_levels    = Column(JSONB)
    forward_horizon_returns = Column(JSONB)
    equity_research_note = Column(JSONB)
    created_at    = Column(DateTime(timezone=True), default=datetime.utcnow)

    signal = relationship("Signal", back_populates="context")


class Review(Base):
    __tablename__ = "reviews"
    id           = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    signal_id    = Column(UUID(as_uuid=False), ForeignKey("signals.id", ondelete="CASCADE"), nullable=False, unique=True)
    action       = Column(String(20), nullable=False)
    entry_price  = Column(Float)
    sl_price     = Column(Float)
    target_price = Column(Float)
    notes        = Column(Text)
    reviewed_at  = Column(DateTime(timezone=True), default=datetime.utcnow)

    signal  = relationship("Signal", back_populates="review")


class Outcome(Base):
    __tablename__ = "outcomes"
    id          = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    signal_id   = Column(UUID(as_uuid=False), ForeignKey("signals.id", ondelete="CASCADE"), nullable=False, unique=True)
    result      = Column(String(20))
    exit_price  = Column(Float)
    pnl_pct     = Column(Float)
    notes       = Column(Text)
    feedback    = Column(Text)
    recorded_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    signal = relationship("Signal", back_populates="outcome")


class LearningLog(Base):
    __tablename__ = "learning_log"
    id              = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    pattern_id      = Column(UUID(as_uuid=False), ForeignKey("patterns.id", ondelete="CASCADE"), nullable=False)
    source          = Column(String(30), nullable=False)
    insight_text    = Column(Text, nullable=False)
    version_applied = Column(Integer)
    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)

    pattern = relationship("Pattern", back_populates="learning")


class PatternChat(Base):
    __tablename__ = "pattern_chat"
    id         = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    pattern_id = Column(UUID(as_uuid=False), ForeignKey("patterns.id", ondelete="CASCADE"))
    role       = Column(String(10), nullable=False)
    content    = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    pattern = relationship("Pattern", back_populates="chat")


class PatternEvent(Base):
    __tablename__ = "pattern_events"
    id                  = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    pattern_id          = Column(UUID(as_uuid=False), ForeignKey("patterns.id", ondelete="CASCADE"), nullable=False)
    symbol              = Column(String(20), nullable=False)
    exchange            = Column(String(20), default="NSE")
    timeframe           = Column(String(10), default="1d")
    detected_at         = Column(String(10), nullable=False)  # date string YYYY-MM-DD
    entry_price         = Column(Float)
    indicator_snapshot  = Column(JSONB)
    chart_context       = Column(Text)
    ret_5d              = Column(Float)
    ret_10d             = Column(Float)
    ret_20d             = Column(Float)
    ret_21d             = Column(Float)
    ret_63d             = Column(Float)
    ret_126d            = Column(Float)
    max_gain_20d        = Column(Float)
    max_loss_20d        = Column(Float)
    outcome             = Column(String(20))
    user_feedback       = Column(String(20))
    user_notes          = Column(Text)
    backtest_run_id     = Column(UUID(as_uuid=False))
    created_at          = Column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__      = (UniqueConstraint("pattern_id", "symbol", "timeframe", "detected_at"),)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"
    id              = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    pattern_id      = Column(UUID(as_uuid=False), ForeignKey("patterns.id", ondelete="CASCADE"), nullable=False)
    version_num     = Column(Integer, default=1)
    symbols_scanned = Column(Integer, default=0)
    events_found    = Column(Integer, default=0)
    success_count   = Column(Integer, default=0)
    failure_count   = Column(Integer, default=0)
    neutral_count   = Column(Integer, default=0)
    success_rate    = Column(Float)
    avg_ret_5d      = Column(Float)
    avg_ret_10d     = Column(Float)
    avg_ret_20d     = Column(Float)
    status          = Column(String(20), default="running")
    error_message   = Column(Text)
    started_at      = Column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at    = Column(DateTime(timezone=True))


class PatternStudy(Base):
    __tablename__ = "pattern_studies"
    id                      = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    pattern_id              = Column(UUID(as_uuid=False), ForeignKey("patterns.id", ondelete="CASCADE"), nullable=False)
    backtest_run_id         = Column(UUID(as_uuid=False))
    llm_analysis            = Column(Text, nullable=False)
    success_factors         = Column(JSONB)
    failure_factors         = Column(JSONB)
    rulebook_suggestions    = Column(JSONB)
    confidence_improvements = Column(JSONB)
    created_at              = Column(DateTime(timezone=True), default=datetime.utcnow)


class ScreeningCache(Base):
    """
    Cache for LLM screening results.
    Key: pattern_id + symbol + timeframe (24-hour TTL)
    Prevents redundant LLM calls for same symbol+pattern within 24 hours.
    """
    __tablename__ = "screening_cache"
    id               = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    pattern_id       = Column(UUID(as_uuid=False), ForeignKey("patterns.id", ondelete="CASCADE"), nullable=False)
    symbol           = Column(String(20), nullable=False)
    timeframe        = Column(String(10), nullable=False, default="1d")
    base_score       = Column(Float, nullable=False)
    adjusted_score   = Column(Float, nullable=False)
    analysis_text    = Column(Text, nullable=False)
    cached_at        = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    __table_args__   = (UniqueConstraint("pattern_id", "symbol", "timeframe"), Index("idx_screening_cache_expire", "cached_at"))


class PatternCandidate(Base):
    """Draft-to-production candidate pattern lifecycle."""
    __tablename__ = "pattern_candidates"
    id                 = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    title              = Column(String(160), nullable=False)
    objective          = Column(Text, nullable=False)
    source_type        = Column(String(20), nullable=False, default="studio")  # studio|upload|system
    screenshot_refs    = Column(JSONB)  # list of URLs/paths
    traits_json        = Column(JSONB, nullable=False, default=dict)
    draft_rules_json   = Column(JSONB, nullable=False, default=dict)
    conditions_json    = Column(JSONB, nullable=False, default=dict)
    universes_json     = Column(JSONB, nullable=False, default=list)
    status             = Column(String(30), nullable=False, default="draft")  # draft|under_validation|revision|approved_for_production|retired
    validation_summary = Column(JSONB)
    revision_notes     = Column(Text)
    linked_pattern_id  = Column(UUID(as_uuid=False), ForeignKey("patterns.id"))
    created_at         = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at         = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    linked_pattern = relationship("Pattern", back_populates="candidates")


class SignalAlertJournal(Base):
    """Stores delivered alerts and payload lineage for each detected signal."""
    __tablename__ = "signal_alert_journal"
    id                  = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    signal_id           = Column(UUID(as_uuid=False), ForeignKey("signals.id", ondelete="CASCADE"), nullable=False)
    channel             = Column(String(20), nullable=False, default="telegram")
    status              = Column(String(20), nullable=False, default="queued")  # queued|sent|failed
    payload_json        = Column(JSONB, nullable=False, default=dict)
    telegram_chat_id    = Column(String(40))
    telegram_message_id = Column(String(40))
    delivered_at        = Column(DateTime(timezone=True))
    created_at          = Column(DateTime(timezone=True), default=datetime.utcnow)


class TelegramFeedback(Base):
    """User feedback captured from Telegram alert actions."""
    __tablename__ = "telegram_feedback"
    id           = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    signal_id    = Column(UUID(as_uuid=False), ForeignKey("signals.id", ondelete="CASCADE"), nullable=False)
    alert_id     = Column(UUID(as_uuid=False), ForeignKey("signal_alert_journal.id", ondelete="SET NULL"))
    action       = Column(String(40), nullable=False)  # watching|traded|useful|skip|closed
    username     = Column(String(120))
    chat_id      = Column(String(40))
    raw_payload  = Column(JSONB)
    created_at   = Column(DateTime(timezone=True), default=datetime.utcnow)


class PatternReviewCycle(Base):
    """Periodic reinforced-learning review snapshots for a pattern."""
    __tablename__ = "pattern_review_cycles"
    id                    = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    pattern_id            = Column(UUID(as_uuid=False), ForeignKey("patterns.id", ondelete="CASCADE"), nullable=False)
    review_period_start   = Column(DateTime(timezone=True))
    review_period_end     = Column(DateTime(timezone=True))
    justified_analysis    = Column(Text, nullable=False)
    suggested_changes     = Column(JSONB)
    metrics_before_json   = Column(JSONB)
    metrics_after_json    = Column(JSONB)
    created_at            = Column(DateTime(timezone=True), default=datetime.utcnow)


class TelegramSyncState(Base):
    """Stores Telegram getUpdates offset to avoid duplicate feedback processing."""
    __tablename__ = "telegram_sync_state"
    id             = Column(Integer, primary_key=True, default=1)
    last_update_id = Column(Integer, nullable=False, default=0)
    updated_at     = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
