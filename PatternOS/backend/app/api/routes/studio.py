"""Pattern Studio — chat, file-upload, backtest and study endpoints."""

from typing import Annotated, Optional
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
    Query,
    Body,
)
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import (
    Pattern,
    PatternChat,
    PatternVersion,
    PatternEvent,
    BacktestRun,
    PatternStudy,
    PatternCandidate,
)
from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    ChatMessage,
    PatternCandidateCreate,
    PatternCandidateOut,
    PatternCandidateUpdate,
    StudyApplyPatchesRequest,
    BacktestRunDetail,
    BacktestRunSummary,
    CompareRunsRequest,
    CompareRunsResponse,
    MetricDelta,
)
from app.utils.deep_merge import deep_merge
from app.llm.studio import run_studio_chat
from app.utils.file_processor import process_file

router = APIRouter(prefix="/studio", tags=["studio"])

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB per upload
ALLOWED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".pdf",
    ".docx",
    ".doc",
    ".txt",
    ".md",
}


@router.post("/candidates", response_model=PatternCandidateOut)
def create_candidate(body: PatternCandidateCreate, db: Session = Depends(get_db)):
    c = PatternCandidate(
        title=body.title,
        objective=body.objective,
        source_type=body.source_type,
        screenshot_refs=body.screenshot_refs,
        traits_json=body.traits_json,
        draft_rules_json=body.draft_rules_json,
        conditions_json=body.conditions_json,
        universes_json=body.universes_json,
        status="draft",
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.get("/candidates", response_model=list[PatternCandidateOut])
def list_candidates(status: str | None = Query(None), db: Session = Depends(get_db)):
    q = db.query(PatternCandidate).order_by(PatternCandidate.updated_at.desc())
    if status:
        q = q.filter(PatternCandidate.status == status)
    return q.limit(300).all()


@router.get("/candidates/{candidate_id}", response_model=PatternCandidateOut)
def get_candidate(candidate_id: str, db: Session = Depends(get_db)):
    c = db.query(PatternCandidate).filter_by(id=candidate_id).first()
    if not c:
        raise HTTPException(404, "Candidate not found")
    return c


@router.patch("/candidates/{candidate_id}", response_model=PatternCandidateOut)
def update_candidate(
    candidate_id: str, body: PatternCandidateUpdate, db: Session = Depends(get_db)
):
    c = db.query(PatternCandidate).filter_by(id=candidate_id).first()
    if not c:
        raise HTTPException(404, "Candidate not found")
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(c, key, value)
    db.commit()
    db.refresh(c)
    return c


def _draft_rules_nonempty(dr) -> bool:
    """JSONB may be None, {}, or a dict with content."""
    if dr is None:
        return False
    if isinstance(dr, dict) and len(dr) > 0:
        return True
    return bool(dr)


@router.post("/candidates/{candidate_id}/finalize")
def finalize_candidate(candidate_id: str, db: Session = Depends(get_db)):
    c = db.query(PatternCandidate).filter_by(id=candidate_id).first()
    if not c:
        raise HTTPException(404, "Candidate not found")
    if c.linked_pattern_id:
        return {
            "ok": True,
            "pattern_id": c.linked_pattern_id,
            "message": "Candidate already finalized",
        }
    if not _draft_rules_nonempty(c.draft_rules_json):
        raise HTTPException(
            400,
            "Candidate has no saved rulebook. In Studio: finish the Define tab so the Rulebook panel has JSON, "
            "click “Save to candidate”, then Finalize — or Finalize will auto-save if the panel already has a rulebook.",
        )

    pattern = Pattern(
        name=c.title[:100],
        description=c.objective,
        status="active",
        timeframes=["1d"],
    )
    db.add(pattern)
    db.flush()

    pv = PatternVersion(
        pattern_id=pattern.id,
        version=1,
        rulebook_json=c.draft_rules_json,
        change_summary="Finalized from pattern candidate",
    )
    db.add(pv)
    c.linked_pattern_id = pattern.id
    c.status = "approved_for_production"
    db.commit()
    return {"ok": True, "pattern_id": pattern.id}


async def _get_or_create_pattern(pattern_id: str | None, db: Session) -> Pattern:
    if pattern_id:
        p = db.query(Pattern).filter_by(id=pattern_id).first()
        if not p:
            raise HTTPException(404, "Pattern not found")
        return p
    p = Pattern(name=f"Draft {db.query(Pattern).count() + 1}", status="draft")
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _save_version_if_finalized(pattern: Pattern, rulebook_draft: dict, db: Session):
    if not (rulebook_draft and rulebook_draft.get("finalized")):
        return
    existing = db.query(PatternVersion).filter_by(pattern_id=pattern.id).count()
    new_ver = existing + 1
    pv = PatternVersion(
        pattern_id=pattern.id,
        version=new_ver,
        rulebook_json=rulebook_draft,
        change_summary="Created via Pattern Studio",
    )
    pattern.current_version = new_ver
    pattern.status = "active"
    db.add(pv)
    db.commit()


def _load_history(pattern_id: str, db: Session) -> list[dict]:
    msgs = (
        db.query(PatternChat)
        .filter_by(pattern_id=pattern_id)
        .order_by(PatternChat.created_at)
        .all()
    )
    return [{"role": m.role, "content": m.content} for m in msgs]


# ─── Text-only chat ───────────────────────────────────────────────────────────


@router.post("/chat", response_model=ChatResponse)
async def chat_text(body: ChatRequest, db: Session = Depends(get_db)):
    """Standard text chat — no file attachments."""
    pattern = await _get_or_create_pattern(body.pattern_id, db)
    history = _load_history(pattern.id, db)

    db.add(PatternChat(pattern_id=pattern.id, role="user", content=body.message))
    db.commit()

    reply, rulebook = await run_studio_chat(
        history=history,
        user_message=body.message,
        pattern_name=pattern.name,
    )

    db.add(PatternChat(pattern_id=pattern.id, role="assistant", content=reply))
    _save_version_if_finalized(pattern, rulebook, db)
    db.commit()

    return ChatResponse(pattern_id=pattern.id, reply=reply, rulebook_draft=rulebook)


# ─── File + message chat ──────────────────────────────────────────────────────


@router.post("/chat-with-files", response_model=ChatResponse)
async def chat_with_files(
    message: Annotated[str, Form(...)],
    pattern_id: Annotated[str | None, Form()] = None,
    files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    """
    Multipart chat endpoint — accepts text + up to 5 file attachments.
    Supported: JPG, PNG, WEBP, GIF, PDF, DOCX, TXT, MD.
    Files are processed into LLM vision/text content blocks.
    """
    if not message and not files:
        raise HTTPException(400, "Provide a message or at least one file.")

    pattern = await _get_or_create_pattern(pattern_id, db)
    history = _load_history(pattern.id, db)

    # Process uploaded files into LLM content blocks
    file_blocks = []
    file_labels = []
    for f in files[:5]:  # max 5 files per message
        from pathlib import Path

        ext = Path(f.filename or "").suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                400,
                f"Unsupported file type: {f.filename}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
            )
        data = await f.read()
        if len(data) > MAX_FILE_SIZE:
            raise HTTPException(400, f"File {f.filename} exceeds 20 MB limit.")
        blocks = process_file(f.filename or "upload", f.content_type or "", data)
        file_blocks.extend(blocks)
        file_labels.append(f.filename or "file")

    # Build display label for user message stored in DB
    user_display = message or ""
    if file_labels:
        user_display = f"[Attached: {', '.join(file_labels)}]\n{message}".strip()

    db.add(PatternChat(pattern_id=pattern.id, role="user", content=user_display))
    db.commit()

    reply, rulebook = await run_studio_chat(
        history=history,
        user_message=message or "Please analyze the attached file(s).",
        pattern_name=pattern.name,
        file_blocks=file_blocks if file_blocks else None,
    )

    db.add(PatternChat(pattern_id=pattern.id, role="assistant", content=reply))
    _save_version_if_finalized(pattern, rulebook, db)
    db.commit()

    return ChatResponse(pattern_id=pattern.id, reply=reply, rulebook_draft=rulebook)


# ─── Chat history ─────────────────────────────────────────────────────────────


@router.get("/{pattern_id}/history", response_model=list[ChatMessage])
def get_history(pattern_id: str, db: Session = Depends(get_db)):
    return (
        db.query(PatternChat)
        .filter_by(pattern_id=pattern_id)
        .order_by(PatternChat.created_at)
        .all()
    )


# ─── Backtest endpoints ───────────────────────────────────────────────────────


@router.post("/{pattern_id}/backtest")
async def start_backtest(
    pattern_id: str,
    engine: str = Query("internal"),
    body: dict = Body(default={}),
    db: Session = Depends(get_db),
):
    """Start a backtest run in a thread pool so the event loop stays responsive."""
    import asyncio
    from app.scanner.backtest import run_backtest
    from app.scanner.vectorbt_backtest import run_backtest_vectorbt
    from app.db.session import SessionLocal

    p = db.query(Pattern).filter_by(id=pattern_id).first()
    if not p:
        raise HTTPException(404, "Pattern not found")
    pv = db.query(PatternVersion).filter_by(pattern_id=pattern_id).first()
    if not pv:
        raise HTTPException(400, "No rulebook defined yet. Define the pattern first.")

    scope = body.get("scope", "nifty50") if body else "nifty50"
    symbols = body.get("symbols", "") if body else ""

    # Parse custom symbols if provided
    symbol_list = None
    if symbols:
        if isinstance(symbols, str):
            symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
        elif isinstance(symbols, list):
            symbol_list = [s.strip() for s in symbols if s]

    engine_norm = (engine or "internal").strip().lower()
    if engine_norm not in ("internal", "vectorbt"):
        raise HTTPException(400, "Invalid engine; use internal|vectorbt")

    def _run_in_thread():
        # Each thread needs its own Session — SQLAlchemy sessions are not thread-safe
        thread_db = SessionLocal()
        try:
            if engine_norm == "vectorbt":
                return run_backtest_vectorbt(
                    pattern_id, thread_db, scope=scope, symbols=symbol_list
                )
            return run_backtest(pattern_id, thread_db, scope=scope, symbols=symbol_list)
        finally:
            thread_db.close()

    try:
        run_id = await asyncio.to_thread(_run_in_thread)
        return {"run_id": run_id, "status": "complete"}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/{pattern_id}/backtest/runs", response_model=list[BacktestRunDetail])
def list_backtest_runs(pattern_id: str, db: Session = Depends(get_db)):
    runs = (
        db.query(BacktestRun)
        .filter_by(pattern_id=pattern_id)
        .order_by(BacktestRun.started_at.desc())
        .limit(10)
        .all()
    )
    return [
        BacktestRunDetail(
            id=r.id,
            pattern_id=r.pattern_id,
            version_num=r.version_num,
            engine=getattr(r, "engine", "internal"),
            symbols_scanned=r.symbols_scanned,
            events_found=r.events_found,
            success_count=r.success_count,
            failure_count=r.failure_count,
            neutral_count=r.neutral_count,
            success_rate=r.success_rate,
            avg_ret_5d=r.avg_ret_5d,
            avg_ret_10d=r.avg_ret_10d,
            avg_ret_20d=r.avg_ret_20d,
            stats_json=r.stats_json,
            params_json=r.params_json,
            notes=r.notes,
            tags=r.tags if r.tags else None,
            status=r.status,
            error_message=r.error_message,
            started_at=r.started_at,
            completed_at=r.completed_at,
        )
        for r in runs
    ]


@router.get("/{pattern_id}/backtest/runs/{run_id}", response_model=BacktestRunDetail)
def get_backtest_run(pattern_id: str, run_id: str, db: Session = Depends(get_db)):
    """Get detailed information for a single backtest run."""
    run = db.query(BacktestRun).filter_by(pattern_id=pattern_id, id=run_id).first()
    if not run:
        raise HTTPException(404, "Backtest run not found")

    return BacktestRunDetail(
        id=run.id,
        pattern_id=run.pattern_id,
        version_num=run.version_num,
        engine=getattr(run, "engine", "internal"),
        symbols_scanned=run.symbols_scanned,
        events_found=run.events_found,
        success_count=run.success_count,
        failure_count=run.failure_count,
        neutral_count=run.neutral_count,
        success_rate=run.success_rate,
        avg_ret_5d=run.avg_ret_5d,
        avg_ret_10d=run.avg_ret_10d,
        avg_ret_20d=run.avg_ret_20d,
        stats_json=run.stats_json,
        params_json=run.params_json,
        notes=run.notes,
        tags=run.tags if run.tags else None,
        status=run.status,
        error_message=run.error_message,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


@router.post("/{pattern_id}/backtest/compare", response_model=CompareRunsResponse)
def compare_backtest_runs(
    pattern_id: str,
    body: CompareRunsRequest,
    db: Session = Depends(get_db),
):
    """
    Compare multiple backtest runs side-by-side.
    Returns run details + metric deltas (baseline = first run, comparison = others).
    """
    if len(body.run_ids) < 2:
        raise HTTPException(400, "At least 2 run_ids required for comparison")

    runs = []
    for rid in body.run_ids:
        r = db.query(BacktestRun).filter_by(pattern_id=pattern_id, id=rid).first()
        if not r:
            raise HTTPException(404, f"Run {rid} not found")
        runs.append(r)

    baseline = runs[0]
    metrics = []

    # Metric keys to compare (name, baseline attr, comparison attr)
    metric_map = [
        ("events_found", "events_found"),
        ("success_rate", "success_rate"),
        ("avg_ret_5d", "avg_ret_5d"),
        ("avg_ret_10d", "avg_ret_10d"),
        ("avg_ret_20d", "avg_ret_20d"),
    ]

    improved = []
    degraded = []

    for m_key, attr in metric_map:
        baseline_val = getattr(baseline, attr)
        for idx in range(1, len(runs)):
            comp_val = getattr(runs[idx], attr)
            delta = None
            delta_pct = None
            if baseline_val is not None and comp_val is not None:
                delta = comp_val - baseline_val
                if baseline_val != 0:
                    delta_pct = (delta / abs(baseline_val)) * 100

                # Determine if improved or degraded
                # Higher success_rate and avg_ret are better; lower is not considered degraded here
                if comp_val > baseline_val:
                    improved.append(m_key)
                elif comp_val < baseline_val:
                    degraded.append(m_key)

            metrics.append(
                MetricDelta(
                    metric=m_key,
                    baseline=baseline_val,
                    comparison=comp_val,
                    delta=delta,
                    delta_pct=delta_pct,
                )
            )

    return CompareRunsResponse(
        runs=[
            BacktestRunDetail(
                id=r.id,
                pattern_id=r.pattern_id,
                version_num=r.version_num,
                engine=getattr(r, "engine", "internal"),
                symbols_scanned=r.symbols_scanned,
                events_found=r.events_found,
                success_count=r.success_count,
                failure_count=r.failure_count,
                neutral_count=r.neutral_count,
                success_rate=r.success_rate,
                avg_ret_5d=r.avg_ret_5d,
                avg_ret_10d=r.avg_ret_10d,
                avg_ret_20d=r.avg_ret_20d,
                stats_json=r.stats_json,
                params_json=r.params_json,
                notes=r.notes,
                tags=r.tags if r.tags else None,
                status=r.status,
                error_message=r.error_message,
                started_at=r.started_at,
                completed_at=r.completed_at,
            )
            for r in runs
        ],
        metrics=metrics,
        improved_metrics=list(set(improved)),
        degraded_metrics=list(set(degraded)),
    )


@router.get("/{pattern_id}/events")
def list_events(
    pattern_id: str,
    symbol: str = Query(None),
    outcome: str = Query(None),
    backtest_run_id: str = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    q = db.query(PatternEvent).filter(PatternEvent.pattern_id == pattern_id)
    if backtest_run_id:
        q = q.filter(PatternEvent.backtest_run_id == backtest_run_id)
    if symbol:
        q = q.filter(PatternEvent.symbol == symbol)
    if outcome:
        q = q.filter(PatternEvent.outcome == outcome)
    total = q.count()
    events = (
        q.order_by(PatternEvent.detected_at.desc()).offset(offset).limit(limit).all()
    )
    return {
        "total": total,
        "events": [
            {
                "id": e.id,
                "symbol": e.symbol,
                "timeframe": e.timeframe,
                "detected_at": e.detected_at,
                "entry_price": e.entry_price,
                "backtest_run_id": e.backtest_run_id,
                "ret_5d": e.ret_5d,
                "ret_10d": e.ret_10d,
                "ret_20d": e.ret_20d,
                "ret_21d": e.ret_21d,
                "ret_63d": e.ret_63d,
                "ret_126d": e.ret_126d,
                "max_gain_20d": e.max_gain_20d,
                "max_loss_20d": e.max_loss_20d,
                "outcome": e.outcome,
                "indicator_snapshot": e.indicator_snapshot,
                "user_feedback": e.user_feedback,
                "user_notes": e.user_notes,
            }
            for e in events
        ],
    }


@router.patch("/events/{event_id}/feedback")
def update_event_feedback(event_id: str, body: dict, db: Session = Depends(get_db)):
    evt = db.query(PatternEvent).filter_by(id=event_id).first()
    if not evt:
        raise HTTPException(404, "Event not found")
    evt.user_feedback = body.get("feedback")
    evt.user_notes = body.get("notes")
    db.commit()
    return {"ok": True}


@router.post("/{pattern_id}/study/apply-patches")
def apply_study_patches(
    pattern_id: str, body: StudyApplyPatchesRequest, db: Session = Depends(get_db)
):
    """
    Deep-merge each patch dict into the active rulebook and create a new PatternVersion.
    Use suggestion.apply_patch values from the study JSON (or any partial rulebook fragments).
    """
    from datetime import datetime as dt

    p = db.query(Pattern).filter_by(id=pattern_id).first()
    if not p:
        raise HTTPException(404, "Pattern not found")
    pv = (
        db.query(PatternVersion)
        .filter_by(pattern_id=pattern_id, version=p.current_version)
        .first()
    )
    if not pv:
        raise HTTPException(400, "No active rulebook version")
    rb: dict = dict(pv.rulebook_json or {})
    for patch in body.patches:
        if isinstance(patch, dict) and patch:
            rb = deep_merge(rb, patch)
    new_ver = p.current_version + 1
    nxt = PatternVersion(
        pattern_id=pattern_id,
        version=new_ver,
        rulebook_json=rb,
        change_summary=body.change_summary[:500],
        approved_at=dt.utcnow(),
    )
    p.current_version = new_ver
    p.updated_at = dt.utcnow()
    db.add(nxt)
    db.commit()
    db.refresh(nxt)
    return {"ok": True, "version": new_ver, "pattern_version_id": nxt.id}


@router.post("/{pattern_id}/study")
async def generate_study(pattern_id: str, db: Session = Depends(get_db)):
    """Generate LLM study from latest backtest results."""
    from app.llm.pattern_study import generate_pattern_study

    p = db.query(Pattern).filter_by(id=pattern_id).first()
    if not p:
        raise HTTPException(404, "Pattern not found")
    pv = (
        db.query(PatternVersion)
        .filter_by(pattern_id=pattern_id)
        .order_by(PatternVersion.version.desc())
        .first()
    )
    run = (
        db.query(BacktestRun)
        .filter_by(pattern_id=pattern_id, status="complete")
        .order_by(BacktestRun.started_at.desc())
        .first()
    )
    if not run:
        raise HTTPException(
            400, "No completed backtest run found. Run a backtest first."
        )

    events = db.query(PatternEvent).filter_by(backtest_run_id=run.id).limit(100).all()
    sample = [
        {
            "symbol": e.symbol,
            "detected_at": e.detected_at,
            "outcome": e.outcome,
            "ret_5d": e.ret_5d,
            "ret_10d": e.ret_10d,
            "ret_20d": e.ret_20d,
            "ret_21d": e.ret_21d,
            "ret_63d": e.ret_63d,
            "ret_126d": e.ret_126d,
            "indicators": e.indicator_snapshot,
        }
        for e in events
    ]

    run_stats = {
        "symbols_scanned": run.symbols_scanned,
        "events_found": run.events_found,
        "success_count": run.success_count,
        "failure_count": run.failure_count,
        "neutral_count": run.neutral_count,
        "success_rate": run.success_rate,
        "avg_ret_5d": run.avg_ret_5d,
        "avg_ret_10d": run.avg_ret_10d,
        "avg_ret_20d": run.avg_ret_20d,
    }
    all_run_ev = db.query(PatternEvent).filter_by(backtest_run_id=run.id).all()

    def _mean(xs: list[float]) -> float | None:
        return round(sum(xs) / len(xs), 4) if xs else None

    r21 = [float(e.ret_21d) for e in all_run_ev if e.ret_21d is not None]
    r63 = [float(e.ret_63d) for e in all_run_ev if e.ret_63d is not None]
    r126 = [float(e.ret_126d) for e in all_run_ev if e.ret_126d is not None]
    run_stats["avg_ret_21d"] = _mean(r21)
    run_stats["avg_ret_63d"] = _mean(r63)
    run_stats["avg_ret_126d"] = _mean(r126)

    result = await generate_pattern_study(
        pattern_name=p.name,
        rulebook=pv.rulebook_json if pv else {},
        run_stats=run_stats,
        sample_events=sample,
    )

    study = PatternStudy(
        pattern_id=pattern_id,
        backtest_run_id=run.id,
        llm_analysis=result.get("analysis", ""),
        success_factors=result.get("success_factors"),
        failure_factors=result.get("failure_factors"),
        rulebook_suggestions=result.get("rulebook_suggestions"),
        confidence_improvements=result.get("confidence_improvements"),
    )
    db.add(study)
    db.commit()
    db.refresh(study)

    return {
        "id": study.id,
        "analysis": study.llm_analysis,
        "success_factors": study.success_factors,
        "failure_factors": study.failure_factors,
        "rulebook_suggestions": study.rulebook_suggestions,
        "confidence_improvements": study.confidence_improvements,
    }


@router.get("/{pattern_id}/study/latest")
def get_latest_study(pattern_id: str, db: Session = Depends(get_db)):
    study = (
        db.query(PatternStudy)
        .filter_by(pattern_id=pattern_id)
        .order_by(PatternStudy.created_at.desc())
        .first()
    )
    if not study:
        return None
    return {
        "id": study.id,
        "analysis": study.llm_analysis,
        "success_factors": study.success_factors,
        "failure_factors": study.failure_factors,
        "rulebook_suggestions": study.rulebook_suggestions,
        "confidence_improvements": study.confidence_improvements,
        "created_at": study.created_at.isoformat() if study.created_at else None,
    }
