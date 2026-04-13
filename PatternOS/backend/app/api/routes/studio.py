"""Pattern Studio — chat, file-upload, backtest and study endpoints."""
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Body
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import Pattern, PatternChat, PatternVersion, PatternEvent, BacktestRun, PatternStudy
from app.api.schemas import ChatRequest, ChatResponse, ChatMessage
from app.llm.studio import run_studio_chat
from app.utils.file_processor import process_file

router = APIRouter(prefix="/studio", tags=["studio"])

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB per upload
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf", ".docx", ".doc", ".txt", ".md"}


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
    message: Annotated[str, Form()] = "",
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
            raise HTTPException(400, f"Unsupported file type: {f.filename}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")
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
    body: dict = Body(default={}),
    db: Session = Depends(get_db)
):
    """Start a backtest run in a thread pool so the event loop stays responsive."""
    import asyncio
    from app.scanner.backtest import run_backtest
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

    def _run_in_thread():
        # Each thread needs its own Session — SQLAlchemy sessions are not thread-safe
        thread_db = SessionLocal()
        try:
            return run_backtest(pattern_id, thread_db, scope=scope, symbols=symbol_list)
        finally:
            thread_db.close()

    try:
        run_id = await asyncio.to_thread(_run_in_thread)
        return {"run_id": run_id, "status": "complete"}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/{pattern_id}/backtest/runs")
def list_backtest_runs(pattern_id: str, db: Session = Depends(get_db)):
    runs = (
        db.query(BacktestRun)
        .filter_by(pattern_id=pattern_id)
        .order_by(BacktestRun.started_at.desc())
        .limit(10)
        .all()
    )
    return [
        {
            "id": r.id, "version_num": r.version_num, "status": r.status,
            "symbols_scanned": r.symbols_scanned, "events_found": r.events_found,
            "success_count": r.success_count, "failure_count": r.failure_count,
            "neutral_count": r.neutral_count, "success_rate": r.success_rate,
            "avg_ret_5d": r.avg_ret_5d, "avg_ret_10d": r.avg_ret_10d, "avg_ret_20d": r.avg_ret_20d,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in runs
    ]


@router.get("/{pattern_id}/events")
def list_events(
    pattern_id: str,
    symbol: str = Query(None),
    outcome: str = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    q = db.query(PatternEvent).filter(PatternEvent.pattern_id == pattern_id)
    if symbol:
        q = q.filter(PatternEvent.symbol == symbol)
    if outcome:
        q = q.filter(PatternEvent.outcome == outcome)
    total = q.count()
    events = q.order_by(PatternEvent.detected_at.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "events": [
            {
                "id": e.id, "symbol": e.symbol, "timeframe": e.timeframe,
                "detected_at": e.detected_at, "entry_price": e.entry_price,
                "ret_5d": e.ret_5d, "ret_10d": e.ret_10d, "ret_20d": e.ret_20d,
                "max_gain_20d": e.max_gain_20d, "max_loss_20d": e.max_loss_20d,
                "outcome": e.outcome, "indicator_snapshot": e.indicator_snapshot,
                "user_feedback": e.user_feedback, "user_notes": e.user_notes,
            }
            for e in events
        ]
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
        raise HTTPException(400, "No completed backtest run found. Run a backtest first.")

    events = db.query(PatternEvent).filter_by(backtest_run_id=run.id).limit(100).all()
    sample = [
        {
            "symbol": e.symbol, "detected_at": e.detected_at, "outcome": e.outcome,
            "ret_10d": e.ret_10d, "ret_20d": e.ret_20d,
            "indicators": e.indicator_snapshot,
        }
        for e in events
    ]

    run_stats = {
        "symbols_scanned": run.symbols_scanned, "events_found": run.events_found,
        "success_count": run.success_count, "failure_count": run.failure_count,
        "neutral_count": run.neutral_count, "success_rate": run.success_rate,
        "avg_ret_5d": run.avg_ret_5d, "avg_ret_10d": run.avg_ret_10d, "avg_ret_20d": run.avg_ret_20d,
    }

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
