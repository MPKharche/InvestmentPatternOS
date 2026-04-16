"""Pydantic request/response schemas for all API routes."""
from __future__ import annotations
from datetime import datetime
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
