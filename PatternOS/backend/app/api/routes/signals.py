from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from app.db.session import get_db
from app.db.models import Signal, SignalContext, Review, Pattern, TelegramFeedback
from app.api.schemas import SignalOut, SignalReviewRequest, TelegramFeedbackIn

router = APIRouter(prefix="/signals", tags=["signals"])


def _enrich(signal: Signal) -> SignalOut:
    ctx = signal.context
    return SignalOut(
        id=signal.id,
        pattern_id=signal.pattern_id,
        pattern_name=signal.pattern.name if signal.pattern else None,
        symbol=signal.symbol,
        exchange=signal.exchange,
        timeframe=signal.timeframe,
        triggered_at=signal.triggered_at,
        confidence_score=signal.confidence_score,
        base_score=signal.base_score,
        status=signal.status,
        llm_analysis=ctx.llm_analysis if ctx else None,
        key_levels=ctx.key_levels if ctx else None,
        forward_horizon_returns=ctx.forward_horizon_returns if ctx else None,
        equity_research_note=ctx.equity_research_note if ctx else None,
    )


@router.get("/", response_model=list[SignalOut])
def list_signals(
    status: str = Query("pending", description="pending|reviewed|dismissed|all"),
    pattern_id: str = Query(None),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    q = (
        db.query(Signal)
        .options(joinedload(Signal.context), joinedload(Signal.pattern))
        .order_by(Signal.triggered_at.desc())
    )
    if status != "all":
        q = q.filter(Signal.status == status)
    if pattern_id:
        q = q.filter(Signal.pattern_id == pattern_id)
    return [_enrich(s) for s in q.limit(limit).all()]


@router.get("/{signal_id}", response_model=SignalOut)
def get_signal(signal_id: str, db: Session = Depends(get_db)):
    s = (
        db.query(Signal)
        .options(joinedload(Signal.context), joinedload(Signal.pattern))
        .filter_by(id=signal_id)
        .first()
    )
    if not s:
        raise HTTPException(404, "Signal not found")
    return _enrich(s)


@router.post("/{signal_id}/review", status_code=200)
def review_signal(signal_id: str, body: SignalReviewRequest, db: Session = Depends(get_db)):
    s = db.query(Signal).filter_by(id=signal_id).first()
    if not s:
        raise HTTPException(404, "Signal not found")

    existing = db.query(Review).filter_by(signal_id=signal_id).first()
    if existing:
        existing.action = body.action
        existing.entry_price = body.entry_price
        existing.sl_price = body.sl_price
        existing.target_price = body.target_price
        existing.notes = body.notes
    else:
        rev = Review(
            signal_id=signal_id,
            action=body.action,
            entry_price=body.entry_price,
            sl_price=body.sl_price,
            target_price=body.target_price,
            notes=body.notes,
        )
        db.add(rev)

    s.status = "reviewed" if body.action in ("executed", "watching") else "dismissed"
    db.commit()
    return {"ok": True}


@router.post("/{signal_id}/telegram-feedback", status_code=200)
def record_telegram_feedback(signal_id: str, body: TelegramFeedbackIn, db: Session = Depends(get_db)):
    s = db.query(Signal).filter_by(id=signal_id).first()
    if not s:
        raise HTTPException(404, "Signal not found")

    fb = TelegramFeedback(
        signal_id=signal_id,
        action=body.action,
        username=body.username,
        chat_id=body.chat_id,
        raw_payload=body.raw_payload,
    )
    db.add(fb)
    if body.action in ("watching", "traded", "useful"):
        s.status = "reviewed"
    elif body.action in ("skip",):
        s.status = "dismissed"
    db.commit()
    return {"ok": True}
