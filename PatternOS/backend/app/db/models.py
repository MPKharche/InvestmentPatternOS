"""SQLAlchemy ORM models — mirror the SQL schema exactly."""

import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column,
    String,
    Boolean,
    Integer,
    Float,
    Text,
    DateTime,
    Date,
    ForeignKey,
    ARRAY,
    JSON,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.db.session import Base


def _uuid():
    return str(uuid.uuid4())


class Universe(Base):
    __tablename__ = "universe"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    symbol = Column(String(20), nullable=False)
    exchange = Column(String(20), nullable=False, default="NSE")
    asset_class = Column(String(30), nullable=False, default="equity")
    name = Column(String(100))
    active = Column(Boolean, nullable=False, default=True)
    sector = Column(String(50), nullable=True)
    index_name = Column(
        String(50), nullable=True
    )  # e.g. "Nifty 50", "Nifty Next 50", "Nifty Midcap 150", "Nifty Smallcap 250"
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("symbol", "exchange"),)


class Pattern(Base):
    __tablename__ = "patterns"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text)
    asset_class = Column(String(30), default="equity")
    timeframes = Column(ARRAY(String), default=["1d"])
    status = Column(String(20), nullable=False, default="active")
    current_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    versions = relationship(
        "PatternVersion", back_populates="pattern", cascade="all, delete-orphan"
    )
    signals = relationship("Signal", back_populates="pattern")
    chat = relationship(
        "PatternChat", back_populates="pattern", cascade="all, delete-orphan"
    )
    learning = relationship(
        "LearningLog", back_populates="pattern", cascade="all, delete-orphan"
    )
    candidates = relationship("PatternCandidate", back_populates="linked_pattern")


class PatternVersion(Base):
    __tablename__ = "pattern_versions"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    pattern_id = Column(
        UUID(as_uuid=False),
        ForeignKey("patterns.id", ondelete="CASCADE"),
        nullable=False,
    )
    version = Column(Integer, nullable=False)
    rulebook_json = Column(JSONB, nullable=False)
    change_summary = Column(Text)
    approved_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    pattern = relationship("Pattern", back_populates="versions")
    __table_args__ = (UniqueConstraint("pattern_id", "version"),)


class Signal(Base):
    __tablename__ = "signals"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    pattern_id = Column(UUID(as_uuid=False), ForeignKey("patterns.id"), nullable=False)
    symbol = Column(String(20), nullable=False)
    exchange = Column(String(20), nullable=False, default="NSE")
    timeframe = Column(String(10), nullable=False, default="1d")
    triggered_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    confidence_score = Column(Float, nullable=False)
    base_score = Column(Float)
    rule_snapshot = Column(JSONB)
    status = Column(String(20), nullable=False, default="pending")

    pattern = relationship("Pattern", back_populates="signals")
    context = relationship(
        "SignalContext",
        back_populates="signal",
        uselist=False,
        cascade="all, delete-orphan",
    )
    review = relationship(
        "Review", back_populates="signal", uselist=False, cascade="all, delete-orphan"
    )
    outcome = relationship(
        "Outcome", back_populates="signal", uselist=False, cascade="all, delete-orphan"
    )


class SignalContext(Base):
    __tablename__ = "signal_context"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    signal_id = Column(
        UUID(as_uuid=False),
        ForeignKey("signals.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    chart_summary = Column(Text)
    llm_analysis = Column(Text)
    key_levels = Column(JSONB)
    forward_horizon_returns = Column(JSONB)
    equity_research_note = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    signal = relationship("Signal", back_populates="context")


class Review(Base):
    __tablename__ = "reviews"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    signal_id = Column(
        UUID(as_uuid=False),
        ForeignKey("signals.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    action = Column(String(20), nullable=False)
    entry_price = Column(Float)
    sl_price = Column(Float)
    target_price = Column(Float)
    notes = Column(Text)
    reviewed_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    signal = relationship("Signal", back_populates="review")


class Outcome(Base):
    __tablename__ = "outcomes"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    signal_id = Column(
        UUID(as_uuid=False),
        ForeignKey("signals.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    result = Column(String(20))
    exit_price = Column(Float)
    pnl_pct = Column(Float)
    notes = Column(Text)
    feedback = Column(Text)
    recorded_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    signal = relationship("Signal", back_populates="outcome")


class LearningLog(Base):
    __tablename__ = "learning_log"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    pattern_id = Column(
        UUID(as_uuid=False),
        ForeignKey("patterns.id", ondelete="CASCADE"),
        nullable=False,
    )
    source = Column(String(30), nullable=False)
    insight_text = Column(Text, nullable=False)
    version_applied = Column(Integer)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    pattern = relationship("Pattern", back_populates="learning")


class PatternChat(Base):
    __tablename__ = "pattern_chat"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    pattern_id = Column(
        UUID(as_uuid=False), ForeignKey("patterns.id", ondelete="CASCADE")
    )
    role = Column(String(10), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    pattern = relationship("Pattern", back_populates="chat")


class PatternEvent(Base):
    __tablename__ = "pattern_events"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    pattern_id = Column(
        UUID(as_uuid=False),
        ForeignKey("patterns.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol = Column(String(20), nullable=False)
    exchange = Column(String(20), default="NSE")
    timeframe = Column(String(10), default="1d")
    detected_at = Column(String(10), nullable=False)  # date string YYYY-MM-DD
    entry_price = Column(Float)
    indicator_snapshot = Column(JSONB)
    chart_context = Column(Text)
    ret_5d = Column(Float)
    ret_10d = Column(Float)
    ret_20d = Column(Float)
    ret_21d = Column(Float)
    ret_63d = Column(Float)
    ret_126d = Column(Float)
    max_gain_20d = Column(Float)
    max_loss_20d = Column(Float)
    outcome = Column(String(20))
    user_feedback = Column(String(20))
    user_notes = Column(Text)
    backtest_run_id = Column(UUID(as_uuid=False))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("pattern_id", "symbol", "timeframe", "detected_at"),
    )


class BacktestRun(Base):
    __tablename__ = "backtest_runs"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    pattern_id = Column(
        UUID(as_uuid=False),
        ForeignKey("patterns.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_num = Column(Integer, default=1)
    engine = Column(String(20), default="internal")  # internal|vectorbt
    symbols_scanned = Column(Integer, default=0)
    events_found = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    neutral_count = Column(Integer, default=0)
    success_rate = Column(Float)
    avg_ret_5d = Column(Float)
    avg_ret_10d = Column(Float)
    avg_ret_20d = Column(Float)
    stats_json = Column(JSONB)
    params_json = Column(
        JSONB
    )  # scan parameters (symbols, scope, dates, pattern_version)
    notes = Column(Text)  # user annotation
    tags = Column(JSONB)  # grouping tags e.g. ["production", "experiment"]
    status = Column(String(20), default="running")
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at = Column(DateTime(timezone=True))


class PatternStudy(Base):
    __tablename__ = "pattern_studies"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    pattern_id = Column(
        UUID(as_uuid=False),
        ForeignKey("patterns.id", ondelete="CASCADE"),
        nullable=False,
    )
    backtest_run_id = Column(UUID(as_uuid=False))
    llm_analysis = Column(Text, nullable=False)
    success_factors = Column(JSONB)
    failure_factors = Column(JSONB)
    rulebook_suggestions = Column(JSONB)
    confidence_improvements = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class ScreeningCache(Base):
    """
    Cache for LLM screening results.
    Key: pattern_id + symbol + timeframe (24-hour TTL)
    Prevents redundant LLM calls for same symbol+pattern within 24 hours.
    """

    __tablename__ = "screening_cache"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    pattern_id = Column(
        UUID(as_uuid=False),
        ForeignKey("patterns.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol = Column(String(20), nullable=False)
    timeframe = Column(String(10), nullable=False, default="1d")
    base_score = Column(Float, nullable=False)
    adjusted_score = Column(Float, nullable=False)
    analysis_text = Column(Text, nullable=False)
    cached_at = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    __table_args__ = (
        UniqueConstraint("pattern_id", "symbol", "timeframe"),
        Index("idx_screening_cache_expire", "cached_at"),
    )


class PatternCandidate(Base):
    """Draft-to-production candidate pattern lifecycle."""

    __tablename__ = "pattern_candidates"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    title = Column(String(160), nullable=False)
    objective = Column(Text, nullable=False)
    source_type = Column(
        String(20), nullable=False, default="studio"
    )  # studio|upload|system
    screenshot_refs = Column(JSONB)  # list of URLs/paths
    traits_json = Column(JSONB, nullable=False, default=dict)
    draft_rules_json = Column(JSONB, nullable=False, default=dict)
    conditions_json = Column(JSONB, nullable=False, default=dict)
    universes_json = Column(JSONB, nullable=False, default=list)
    status = Column(
        String(30), nullable=False, default="draft"
    )  # draft|under_validation|revision|approved_for_production|retired
    validation_summary = Column(JSONB)
    revision_notes = Column(Text)
    linked_pattern_id = Column(UUID(as_uuid=False), ForeignKey("patterns.id"))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    linked_pattern = relationship("Pattern", back_populates="candidates")


class SignalAlertJournal(Base):
    """Stores delivered alerts and payload lineage for each detected signal."""

    __tablename__ = "signal_alert_journal"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    signal_id = Column(
        UUID(as_uuid=False),
        ForeignKey("signals.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel = Column(String(20), nullable=False, default="telegram")
    status = Column(String(20), nullable=False, default="queued")  # queued|sent|failed
    payload_json = Column(JSONB, nullable=False, default=dict)
    telegram_chat_id = Column(String(40))
    telegram_message_id = Column(String(40))
    delivered_at = Column(DateTime(timezone=True))
    attempt_count = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime(timezone=True))
    last_attempt_at = Column(DateTime(timezone=True))
    last_error = Column(Text)
    last_http_status = Column(Integer)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class TelegramFeedback(Base):
    """User feedback captured from Telegram alert actions."""

    __tablename__ = "telegram_feedback"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    signal_id = Column(
        UUID(as_uuid=False),
        ForeignKey("signals.id", ondelete="CASCADE"),
        nullable=False,
    )
    alert_id = Column(
        UUID(as_uuid=False), ForeignKey("signal_alert_journal.id", ondelete="SET NULL")
    )
    action = Column(String(40), nullable=False)  # watching|traded|useful|skip|closed
    username = Column(String(120))
    chat_id = Column(String(40))
    raw_payload = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class PatternReviewCycle(Base):
    """Periodic reinforced-learning review snapshots for a pattern."""

    __tablename__ = "pattern_review_cycles"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    pattern_id = Column(
        UUID(as_uuid=False),
        ForeignKey("patterns.id", ondelete="CASCADE"),
        nullable=False,
    )
    review_period_start = Column(DateTime(timezone=True))
    review_period_end = Column(DateTime(timezone=True))
    justified_analysis = Column(Text, nullable=False)
    suggested_changes = Column(JSONB)
    metrics_before_json = Column(JSONB)
    metrics_after_json = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class TelegramSyncState(Base):
    """Stores Telegram getUpdates offset to avoid duplicate feedback processing."""

    __tablename__ = "telegram_sync_state"
    id = Column(Integer, primary_key=True, default=1)
    last_update_id = Column(Integer, nullable=False, default=0)
    updated_at = Column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


# ============================================================================
# Data Cache - Stock prices and fundamentals (24h TTL)
# ============================================================================


class StockPrice(Base):
    __tablename__ = "stock_prices"
    symbol = Column(String(20), primary_key=True)
    timeframe = Column(String(10), primary_key=True, default="1d")
    trade_date = Column(Date, primary_key=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    fetched_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    __table_args__ = (Index("idx_stock_prices_expire", "fetched_at"),)


class StockFundamental(Base):
    __tablename__ = "stock_fundamentals"
    symbol = Column(String(20), primary_key=True)
    pe_ratio = Column(Float)
    pb_ratio = Column(Float)
    debt_to_equity = Column(Float)
    roe = Column(Float)
    dividend_yield = Column(Float)
    beta = Column(Float)
    market_cap = Column(Float)
    enterprise_value = Column(Float)
    forward_pe = Column(Float)
    trailing_pe = Column(Float)
    eps = Column(Float)
    revenue_per_share = Column(Float)
    fetched_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    __table_args__ = (Index("idx_stock_fundamentals_expire", "fetched_at"),)


# ============================================================================
# Mutual Funds module
# ============================================================================


class MFScheme(Base):
    __tablename__ = "mf_schemes"
    scheme_code = Column(Integer, primary_key=True)
    isin_growth = Column(String(20))
    isin_reinvest = Column(String(20))
    scheme_name = Column(Text)

    family_id = Column(Integer, index=True)
    family_name = Column(Text)
    amc_name = Column(Text)
    amc_slug = Column(Text)
    category = Column(Text)
    plan_type = Column(String(20))
    option_type = Column(String(30))
    risk_label = Column(Text)
    expense_ratio = Column(Float)
    aum = Column(Float)
    min_sip = Column(Float)
    min_lumpsum = Column(Float)
    exit_load = Column(Text)
    benchmark = Column(Text)
    launch_date = Column(Date)
    morningstar_sec_id = Column(Text)
    value_research_fund_id = Column(Integer)
    yahoo_finance_symbol = Column(String(32))

    latest_nav = Column(Float)
    latest_nav_date = Column(Date)
    is_active = Column(Boolean, nullable=False, default=True)

    monitored = Column(Boolean, nullable=False, default=False, index=True)
    notes = Column(Text)

    # External links (best-effort deep links with safe fallbacks)
    valueresearch_url = Column(Text)
    morningstar_url = Column(Text)
    yahoo_finance_url = Column(Text)
    valueresearch_link_status = Column(String(20))
    morningstar_link_status = Column(String(20))
    yahoo_link_status = Column(String(20))
    links_last_checked_at = Column(DateTime(timezone=True))
    links_last_check_status = Column(Integer)

    # Enrichment caching
    mfdata_fetched_at = Column(DateTime(timezone=True))
    returns_json = Column(JSONB)
    ratios_json = Column(JSONB)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


class MFProviderState(Base):
    __tablename__ = "mf_provider_state"
    provider = Column(String(40), primary_key=True)
    paused_until = Column(DateTime(timezone=True))
    consecutive_failures = Column(Integer, nullable=False, default=0)
    last_error = Column(Text)
    updated_at = Column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


class MFIngestionCursor(Base):
    __tablename__ = "mf_ingestion_cursors"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    provider = Column(String(40), nullable=False)
    endpoint_class = Column(String(60), nullable=False)
    scheme_code = Column(Integer)
    family_id = Column(Integer)
    cursor_json = Column(JSONB, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


class MFIngestionTask(Base):
    __tablename__ = "mf_ingestion_tasks"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    run_id = Column(
        UUID(as_uuid=False), ForeignKey("mf_ingestion_runs.id", ondelete="CASCADE")
    )
    provider = Column(String(40), nullable=False)
    endpoint_class = Column(String(60), nullable=False)
    scheme_code = Column(Integer)
    family_id = Column(Integer)
    started_at = Column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    finished_at = Column(DateTime(timezone=True))
    status = Column(String(20), nullable=False, default="running")
    request_count = Column(Integer, nullable=False, default=0)
    retry_count = Column(Integer, nullable=False, default=0)
    backoff_seconds = Column(Float, nullable=False, default=0.0)
    http_statuses = Column(JSONB)
    error_text = Column(Text)


class MFNavDaily(Base):
    __tablename__ = "mf_nav_daily"
    scheme_code = Column(
        Integer,
        ForeignKey("mf_schemes.scheme_code", ondelete="CASCADE"),
        primary_key=True,
    )
    nav_date = Column(Date, primary_key=True)
    nav = Column(Float, nullable=False)
    source = Column(String(20), nullable=False, default="amfi")
    ingested_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    scheme = relationship("MFScheme")


class MFNavMetricsDaily(Base):
    __tablename__ = "mf_nav_metrics_daily"
    scheme_code = Column(
        Integer,
        ForeignKey("mf_schemes.scheme_code", ondelete="CASCADE"),
        primary_key=True,
    )
    nav_date = Column(Date, primary_key=True)

    day_change = Column(Float)
    day_change_pct = Column(Float)

    ret_7d = Column(Float)
    ret_30d = Column(Float)
    ret_90d = Column(Float)
    ret_365d = Column(Float)

    rolling_52w_high_nav = Column(Float)
    is_52w_high = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    scheme = relationship("MFScheme")


class MFFamilyHoldingsSnapshot(Base):
    __tablename__ = "mf_family_holdings_snapshot"
    family_id = Column(Integer, primary_key=True)
    month = Column(Date, primary_key=True)  # first day of month

    total_aum = Column(Float)
    equity_pct = Column(Float)
    debt_pct = Column(Float)
    other_pct = Column(Float)
    fetched_at = Column(DateTime(timezone=True))
    raw_json = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class MFHolding(Base):
    __tablename__ = "mf_holdings"
    family_id = Column(Integer, primary_key=True)
    month = Column(Date, primary_key=True)
    holding_type = Column(String(10), primary_key=True)  # equity|debt|other
    name = Column(Text, primary_key=True)

    weight_pct = Column(Float)
    market_value = Column(Float)
    quantity = Column(Float)
    month_change_qty = Column(Float)
    month_change_pct = Column(Float)

    credit_rating = Column(Text)
    maturity_date = Column(Date)

    isin = Column(String(20))
    ticker = Column(Text)
    sector = Column(Text)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class MFSectorAlloc(Base):
    __tablename__ = "mf_sector_alloc"
    family_id = Column(Integer, primary_key=True)
    month = Column(Date, primary_key=True)
    sector = Column(Text, primary_key=True)
    weight_pct = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class MFRulebook(Base):
    __tablename__ = "mf_rulebooks"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name = Column(String(160), nullable=False, unique=True)
    status = Column(String(20), nullable=False, default="active")
    current_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    versions = relationship(
        "MFRulebookVersion", back_populates="rulebook", cascade="all, delete-orphan"
    )


class MFRulebookVersion(Base):
    __tablename__ = "mf_rulebook_versions"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    rulebook_id = Column(
        UUID(as_uuid=False),
        ForeignKey("mf_rulebooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    version = Column(Integer, nullable=False)
    rulebook_json = Column(JSONB, nullable=False)
    change_summary = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    rulebook = relationship("MFRulebook", back_populates="versions")
    __table_args__ = (UniqueConstraint("rulebook_id", "version"),)


class MFSignal(Base):
    __tablename__ = "mf_signals"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    scheme_code = Column(
        Integer,
        ForeignKey("mf_schemes.scheme_code", ondelete="CASCADE"),
        nullable=False,
    )
    family_id = Column(Integer)
    signal_type = Column(String(60), nullable=False)
    nav_date = Column(Date)
    triggered_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    base_score = Column(Float)
    confidence_score = Column(Float, nullable=False)
    context_json = Column(JSONB)
    llm_analysis = Column(Text)
    status = Column(String(20), nullable=False, default="pending")
    reviewed_at = Column(DateTime(timezone=True))
    review_action = Column(String(40))
    review_notes = Column(Text)

    scheme = relationship("MFScheme")
    __table_args__ = (UniqueConstraint("scheme_code", "signal_type", "nav_date"),)


class MFIngestionRun(Base):
    __tablename__ = "mf_ingestion_runs"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    run_type = Column(String(40), nullable=False)
    started_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    finished_at = Column(DateTime(timezone=True))
    status = Column(String(20), nullable=False, default="running")
    stats_json = Column(JSONB)
    error_text = Column(Text)


# ============================================================================
# Custom Screener — user-defined rule-based screening
# ============================================================================


class ScreenerCriteria(Base):
    """Saved screening rule sets."""

    __tablename__ = "screener_criteria"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    asset_class = Column(String(30), nullable=False, default="equity")  # equity|mf
    scope = Column(
        String(30), nullable=False, default="nifty500"
    )  # nifty50|nifty500|custom
    custom_symbols = Column(JSONB)  # array of strings if scope='custom'
    rules_json = Column(
        JSONB, nullable=False
    )  # { "logic": "AND", "conditions": [...] }
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    results = relationship(
        "ScreenerResult", back_populates="screener", cascade="all, delete-orphan"
    )
    runs = relationship(
        "ScreenerRun", back_populates="screener", cascade="all, delete-orphan"
    )

    @property
    def rules(self):
        """Expose rules_json as rules for API compatibility."""
        return self.rules_json

    @rules.setter
    def rules(self, value):
        """Set rules_json when rules is assigned."""
        self.rules_json = value


class ScreenerResult(Base):
    """Cached scan results — one row per symbol per screener per day."""

    __tablename__ = "screener_results"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    screener_id = Column(
        UUID(as_uuid=False),
        ForeignKey("screener_criteria.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol = Column(String(20), nullable=False)
    signal_date = Column(Date, nullable=False)  # date of the price bar evaluated
    metrics_json = Column(JSONB)  # {"rsi": 23.5, "pe": 12.4, ...}
    passed = Column(Boolean, nullable=False, default=False)
    score = Column(Float)  # 0-100 match score
    computed_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    screener = relationship("ScreenerCriteria", back_populates="results")
    __table_args__ = (
        UniqueConstraint("screener_id", "symbol", "signal_date"),
        Index("idx_screener_results_lookup", "screener_id", "passed", "signal_date"),
    )


class ScreenerRun(Base):
    """Audit log of screener executions."""

    __tablename__ = "screener_runs"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    screener_id = Column(
        UUID(as_uuid=False),
        ForeignKey("screener_criteria.id", ondelete="CASCADE"),
        nullable=False,
    )
    triggered_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    symbols_total = Column(Integer, nullable=False)  # universe size
    symbols_passed = Column(Integer, nullable=False)  # matched
    duration_sec = Column(Float, nullable=False)
    filters_json = Column(JSONB)  # runtime params: timeframe, use_cache, etc.
    status = Column(
        String(20), nullable=False, default="completed"
    )  # queued|running|completed|failed

    screener = relationship("ScreenerCriteria", back_populates="runs")


class ScreenerTemplate(Base):
    """Pre-defined screener rule templates for one-click setup."""

    __tablename__ = "screener_templates"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text)
    category = Column(
        String(50), nullable=False
    )  # "technical", "fundamental", "momentum", "value", etc.
    asset_class = Column(String(30), default="equity")
    rules_json = Column(
        JSONB, nullable=False
    )  # { "logic": "AND", "conditions": [...] }
    tags = Column(JSONB)  # e.g. ["oscillator", "trend", "volatility"]
    is_active = Column(Boolean, nullable=False, default=True)
    usage_count = Column(Integer, default=0)  # how many times template was used
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


# ==============================================================================
# Stress Testing (Feature 3)
# ==============================================================================


class PortfolioSnapshot(Base):
    """User-uploaded portfolio positions for stress-testing."""

    __tablename__ = "portfolio_snapshots"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(String(100), nullable=True)  # optional multi-user support
    name = Column(String(200), nullable=False)  # e.g. "My Tech Portfolio"
    positions_json = Column(
        JSONB, nullable=False
    )  # [{"symbol": "RELIANCE", "qty": 100, "avg_price": 2500}, ...]
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


class StressTestRun(Base):
    """Historical stress-test run on a portfolio."""

    __tablename__ = "stress_test_runs"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    portfolio_id = Column(
        UUID(as_uuid=False),
        ForeignKey("portfolio_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    scenario = Column(
        String(50), nullable=False
    )  # "2008_crisis", "2020_covid", "2022_inflation", "custom"
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    initial_value = Column(Float, nullable=False)
    final_value = Column(Float)
    max_drawdown_pct = Column(Float)  # portfolio max drawdown during period
    var_95 = Column(Float)  # Value at Risk (5th percentile)
    beta_weighted = Column(Float)  # portfolio beta vs NIFTY
    results_json = Column(JSONB)  # per-symbol P&L breakdown
    status = Column(
        String(20), nullable=False, default="queued"
    )  # queued|running|completed|failed
    error_message = Column(Text)
    triggered_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at = Column(DateTime(timezone=True))

    portfolio = relationship("PortfolioSnapshot", backref="stress_runs")
