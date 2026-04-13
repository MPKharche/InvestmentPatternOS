from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import Pattern, Signal, Review, Outcome, LearningLog
from app.api.schemas import PatternStats
from app.llm.screener import llm_audit_pattern

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/patterns", response_model=list[PatternStats])
def pattern_stats(db: Session = Depends(get_db)):
    patterns = db.query(Pattern).all()
    results = []
    for p in patterns:
        total = db.query(func.count(Signal.id)).filter_by(pattern_id=p.id).scalar() or 0
        reviewed = db.query(func.count(Review.id)).join(Signal).filter(Signal.pattern_id == p.id).scalar() or 0
        executed = db.query(func.count(Review.id)).join(Signal).filter(
            Signal.pattern_id == p.id, Review.action == "executed"
        ).scalar() or 0
        hit = db.query(func.count(Outcome.id)).join(Signal).filter(
            Signal.pattern_id == p.id, Outcome.result == "hit_target"
        ).scalar() or 0
        stopped = db.query(func.count(Outcome.id)).join(Signal).filter(
            Signal.pattern_id == p.id, Outcome.result == "stopped_out"
        ).scalar() or 0
        avg_pnl = db.query(func.avg(Outcome.pnl_pct)).join(Signal).filter(
            Signal.pattern_id == p.id
        ).scalar()

        win_rate = round((hit / executed) * 100, 1) if executed > 0 else None
        results.append(PatternStats(
            pattern_id=p.id,
            pattern_name=p.name,
            total_signals=total,
            reviewed=reviewed,
            executed=executed,
            hit_target=hit,
            stopped_out=stopped,
            win_rate=win_rate,
            avg_pnl_pct=round(avg_pnl, 2) if avg_pnl else None,
        ))
    return results


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    total_signals = db.query(func.count(Signal.id)).scalar() or 0
    pending = db.query(func.count(Signal.id)).filter_by(status="pending").scalar() or 0
    executed = db.query(func.count(Review.id)).filter_by(action="executed").scalar() or 0
    hit = db.query(func.count(Outcome.id)).filter_by(result="hit_target").scalar() or 0
    stopped = db.query(func.count(Outcome.id)).filter_by(result="stopped_out").scalar() or 0
    active_patterns = db.query(func.count(Pattern.id)).filter_by(status="active").scalar() or 0
    return {
        "total_signals": total_signals,
        "pending_review": pending,
        "executed_trades": executed,
        "hit_target": hit,
        "stopped_out": stopped,
        "active_patterns": active_patterns,
        "overall_win_rate": round((hit / executed) * 100, 1) if executed > 0 else None,
    }


@router.post("/audit/{pattern_id}")
async def audit_pattern(pattern_id: str, db: Session = Depends(get_db)):
    """Run LLM audit on a pattern's outcome history and save insight to learning log."""
    pattern = db.query(Pattern).filter_by(id=pattern_id).first()
    if not pattern:
        raise HTTPException(404, "Pattern not found")

    # Build outcomes summary
    outcomes = (
        db.query(Outcome)
        .join(Signal)
        .filter(Signal.pattern_id == pattern_id)
        .all()
    )
    if not outcomes:
        raise HTTPException(400, "No outcomes yet to audit")

    summary_lines = []
    for o in outcomes:
        summary_lines.append(
            f"- result={o.result}, pnl={o.pnl_pct}%, feedback={o.feedback or 'none'}"
        )

    insight = await llm_audit_pattern(pattern.name, "\n".join(summary_lines))

    log = LearningLog(
        pattern_id=pattern_id,
        source="outcome_audit",
        insight_text=insight,
        version_applied=pattern.current_version,
    )
    db.add(log)
    db.commit()
    return {"insight": insight}
