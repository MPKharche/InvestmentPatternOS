"""Pydantic request/response schemas for all API routes."""
from __future__ import annotations
from datetime import date, datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


# ─── Universe ────────────────────────────────────────────────────────────────

class UniverseItem(BaseModel):
    id: str
    symbol: str
    exchange: str
    asset_class: str
    name: Optional[str]
    active: bool
    sector: Optional[str] = None
    index_name: Optional[str] = None

    class Config:
        from_attributes = True


class UniverseCreate(BaseModel):
    symbol: str
    exchange: str = "NSE"
    asset_class: str = "equity"
    name: Optional[str] = None
    sector: Optional[str] = None
    index_name: Optional[str] = None


# ─── Patterns ────────────────────────────────────────────────────────────────

class PatternSummary(BaseModel):
    id: str
    name: str
    description: Optional[str]
    asset_class: str
    timeframes: list[str]
    status: str
    current_version: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PatternCreate(BaseModel):
    name: str
    description: Optional[str] = None
    asset_class: str = "equity"
    timeframes: list[str] = ["1d"]


class PatternVersionOut(BaseModel):
    id: str
    pattern_id: str
    version: int
    rulebook_json: dict[str, Any]
    change_summary: Optional[str]
    approved_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class PatternVersionCreate(BaseModel):
    rulebook_json: dict[str, Any]
    change_summary: Optional[str] = None


# ─── Pattern Studio chat ──────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str          # user | assistant
    content: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    pattern_id: Optional[str] = None   # None for first turn (new pattern)
    message: str


class ChatResponse(BaseModel):
    pattern_id: str
    reply: str
    rulebook_draft: Optional[dict[str, Any]] = None


class StudyApplyPatchesRequest(BaseModel):
    """Merge partial rulebook fragments (from study suggestions) into current version."""
    patches: list[dict[str, Any]] = Field(default_factory=list)
    change_summary: str = "Applied study patches"


class PatternCandidateCreate(BaseModel):
    title: str
    objective: str
    source_type: str = "studio"
    screenshot_refs: list[str] = Field(default_factory=list)
    traits_json: dict[str, Any] = Field(default_factory=dict)
    draft_rules_json: dict[str, Any] = Field(default_factory=dict)
    conditions_json: dict[str, Any] = Field(default_factory=dict)
    universes_json: list[str] = Field(default_factory=list)


class PatternCandidateUpdate(BaseModel):
    title: Optional[str] = None
    objective: Optional[str] = None
    screenshot_refs: Optional[list[str]] = None
    traits_json: Optional[dict[str, Any]] = None
    draft_rules_json: Optional[dict[str, Any]] = None
    conditions_json: Optional[dict[str, Any]] = None
    universes_json: Optional[list[str]] = None
    status: Optional[str] = None
    validation_summary: Optional[dict[str, Any]] = None
    revision_notes: Optional[str] = None


class PatternCandidateOut(BaseModel):
    id: str
    title: str
    objective: str
    source_type: str
    screenshot_refs: Optional[list[str]] = None
    traits_json: dict[str, Any]
    draft_rules_json: dict[str, Any]
    conditions_json: dict[str, Any]
    universes_json: list[str]
    status: str
    validation_summary: Optional[dict[str, Any]] = None
    revision_notes: Optional[str] = None
    linked_pattern_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ─── Signals ─────────────────────────────────────────────────────────────────

class SignalOut(BaseModel):
    id: str
    pattern_id: str
    pattern_name: Optional[str] = None
    symbol: str
    exchange: str
    timeframe: str
    triggered_at: datetime
    confidence_score: float
    base_score: Optional[float]
    status: str
    llm_analysis: Optional[str] = None
    key_levels: Optional[dict[str, Any]] = None
    forward_horizon_returns: Optional[dict[str, Any]] = None
    equity_research_note: Optional[dict[str, Any]] = None

    class Config:
        from_attributes = True


class SignalReviewRequest(BaseModel):
    action: str = Field(..., pattern="^(executed|watching|skipped|dismissed)$")
    entry_price: Optional[float] = None
    sl_price: Optional[float] = None
    target_price: Optional[float] = None
    notes: Optional[str] = None


class TelegramFeedbackIn(BaseModel):
    action: str = Field(..., pattern="^(watching|traded|useful|skip|closed)$")
    username: Optional[str] = None
    chat_id: Optional[str] = None
    raw_payload: Optional[dict[str, Any]] = None


# ─── Outcomes ────────────────────────────────────────────────────────────────

class OutcomeCreate(BaseModel):
    result: str = Field(..., pattern="^(hit_target|stopped_out|partial|open|cancelled)$")
    exit_price: Optional[float] = None
    pnl_pct: Optional[float] = None
    notes: Optional[str] = None
    feedback: Optional[str] = None


class OutcomeOut(BaseModel):
    id: str
    signal_id: str
    result: Optional[str]
    exit_price: Optional[float]
    pnl_pct: Optional[float]
    notes: Optional[str]
    feedback: Optional[str]
    recorded_at: datetime

    class Config:
        from_attributes = True


# ─── Analytics ───────────────────────────────────────────────────────────────

class PatternStats(BaseModel):
    pattern_id: str
    pattern_name: str
    total_signals: int
    reviewed: int
    executed: int
    hit_target: int
    stopped_out: int
    win_rate: Optional[float]
    avg_pnl_pct: Optional[float]


# ─── Scanner ─────────────────────────────────────────────────────────────────

class ScanRequest(BaseModel):
    pattern_id: Optional[str] = None   # None = run all active patterns
    symbols: Optional[list[str]] = None  # None = full universe
    scope: Optional[str] = "nifty50"  # "full", "nifty50", or "custom"; if custom, use symbols list


class ScanResult(BaseModel):
    signals_created: int
    symbols_scanned: int
    duration_seconds: float


# ─── Learning log ────────────────────────────────────────────────────────────

class LearningLogOut(BaseModel):
    id: str
    pattern_id: str
    source: str
    insight_text: str
    version_applied: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


# ───────────────────────── Mutual Funds ─────────────────────────


class MFSchemeOut(BaseModel):
    scheme_code: int
    scheme_name: Optional[str] = None
    isin_growth: Optional[str] = None
    isin_reinvest: Optional[str] = None

    family_id: Optional[int] = None
    family_name: Optional[str] = None
    amc_name: Optional[str] = None
    amc_slug: Optional[str] = None
    category: Optional[str] = None
    plan_type: Optional[str] = None
    option_type: Optional[str] = None
    risk_label: Optional[str] = None
    expense_ratio: Optional[float] = None
    aum: Optional[float] = None
    min_sip: Optional[float] = None
    min_lumpsum: Optional[float] = None
    exit_load: Optional[str] = None
    benchmark: Optional[str] = None
    launch_date: Optional[date] = None

    latest_nav: Optional[float] = None
    latest_nav_date: Optional[date] = None
    is_active: bool = True
    monitored: bool = False
    notes: Optional[str] = None

    # External links (safe generated fallbacks; no scraping)
    valueresearch_url: Optional[str] = None
    morningstar_url: Optional[str] = None
    valueresearch_link_status: Optional[str] = None
    morningstar_link_status: Optional[str] = None
    morningstar_sec_id: Optional[str] = None
    returns_json: Optional[dict[str, Any]] = None
    ratios_json: Optional[dict[str, Any]] = None

    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MFSchemeUpdate(BaseModel):
    monitored: Optional[bool] = None
    notes: Optional[str] = None
    valueresearch_url: Optional[str] = None
    morningstar_url: Optional[str] = None
    morningstar_sec_id: Optional[str] = None
    valueresearch_link_status: Optional[str] = None
    morningstar_link_status: Optional[str] = None


class MFNavPoint(BaseModel):
    nav_date: date
    nav: float


class MFSignalOut(BaseModel):
    id: str
    scheme_code: int
    scheme_name: Optional[str] = None
    family_id: Optional[int] = None
    signal_type: str
    nav_date: Optional[date] = None
    triggered_at: datetime
    base_score: Optional[float] = None
    confidence_score: float
    status: str
    llm_analysis: Optional[str] = None
    context_json: Optional[dict[str, Any]] = None
    reviewed_at: Optional[datetime] = None
    review_action: Optional[str] = None
    review_notes: Optional[str] = None


class MFSignalReviewRequest(BaseModel):
    action: str
    notes: Optional[str] = None


class MFRulebookOut(BaseModel):
    id: str
    name: str
    status: str
    current_version: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MFRulebookCreate(BaseModel):
    name: str
    status: str = "active"
    rulebook_json: dict[str, Any]
    change_summary: str = "Initial MF rulebook"


class MFRulebookUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None


class MFRulebookNewVersion(BaseModel):
    rulebook_json: dict[str, Any]
    change_summary: str = "Update MF rulebook"
    set_current: bool = True


class MFRulebookActivateVersion(BaseModel):
    version: int


class MFRulebookVersionOut(BaseModel):
    id: str
    rulebook_id: str
    version: int
    rulebook_json: dict[str, Any]
    change_summary: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class MFIngestionRunOut(BaseModel):
    id: str
    run_type: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str
    stats_json: Optional[dict[str, Any]] = None
    error_text: Optional[str] = None

    class Config:
        from_attributes = True


class MFIngestionStatus(BaseModel):
    # NOTE: FastAPI+Pydantic v2 OpenAPI generation can be fragile with nested models.
    # Keep these as JSON blobs for now to preserve /openapi.json availability.
    latest_nav_run: Optional[dict[str, Any]] = None
    latest_holdings_run: Optional[dict[str, Any]] = None
    monitored_schemes: int
    schemes_total: int
    nav_rows_total: int
    signals_pending: int
    providers: Optional[list[dict[str, Any]]] = None


class MFProviderStateOut(BaseModel):
    provider: str
    paused_until: Optional[datetime] = None
    consecutive_failures: int
    last_error: Optional[str] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MFProviderPauseRequest(BaseModel):
    minutes: int = 60
    reason: Optional[str] = None
