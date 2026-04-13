from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import Pattern, PatternVersion, LearningLog
from app.api.schemas import (
    PatternSummary, PatternCreate,
    PatternVersionOut, PatternVersionCreate,
    LearningLogOut,
)

router = APIRouter(prefix="/patterns", tags=["patterns"])


@router.get("/", response_model=list[PatternSummary])
def list_patterns(db: Session = Depends(get_db)):
    return db.query(Pattern).order_by(Pattern.created_at.desc()).all()


@router.post("/", response_model=PatternSummary, status_code=201)
def create_pattern(body: PatternCreate, db: Session = Depends(get_db)):
    pattern = Pattern(**body.model_dump())
    db.add(pattern)
    db.commit()
    db.refresh(pattern)
    return pattern


@router.get("/{pattern_id}", response_model=PatternSummary)
def get_pattern(pattern_id: str, db: Session = Depends(get_db)):
    p = db.query(Pattern).filter_by(id=pattern_id).first()
    if not p:
        raise HTTPException(404, "Pattern not found")
    return p


@router.patch("/{pattern_id}/status")
def update_status(pattern_id: str, status: str, db: Session = Depends(get_db)):
    p = db.query(Pattern).filter_by(id=pattern_id).first()
    if not p:
        raise HTTPException(404, "Pattern not found")
    if status not in ("active", "paused", "draft"):
        raise HTTPException(400, "Invalid status")
    p.status = status
    db.commit()
    return {"ok": True}


# ─── Versions ────────────────────────────────────────────────────────────────

@router.get("/{pattern_id}/versions", response_model=list[PatternVersionOut])
def list_versions(pattern_id: str, db: Session = Depends(get_db)):
    return (
        db.query(PatternVersion)
        .filter_by(pattern_id=pattern_id)
        .order_by(PatternVersion.version.desc())
        .all()
    )


@router.post("/{pattern_id}/versions", response_model=PatternVersionOut, status_code=201)
def create_version(pattern_id: str, body: PatternVersionCreate, db: Session = Depends(get_db)):
    p = db.query(Pattern).filter_by(id=pattern_id).first()
    if not p:
        raise HTTPException(404, "Pattern not found")
    new_ver = p.current_version + 1
    pv = PatternVersion(
        pattern_id=pattern_id,
        version=new_ver,
        rulebook_json=body.rulebook_json,
        change_summary=body.change_summary,
        approved_at=datetime.utcnow(),
    )
    p.current_version = new_ver
    p.updated_at = datetime.utcnow()
    db.add(pv)
    db.commit()
    db.refresh(pv)
    return pv


@router.get("/{pattern_id}/versions/{version}", response_model=PatternVersionOut)
def get_version(pattern_id: str, version: int, db: Session = Depends(get_db)):
    pv = db.query(PatternVersion).filter_by(pattern_id=pattern_id, version=version).first()
    if not pv:
        raise HTTPException(404, "Version not found")
    return pv


# ─── Learning log ────────────────────────────────────────────────────────────

@router.get("/{pattern_id}/learning", response_model=list[LearningLogOut])
def get_learning_log(pattern_id: str, db: Session = Depends(get_db)):
    return (
        db.query(LearningLog)
        .filter_by(pattern_id=pattern_id)
        .order_by(LearningLog.created_at.desc())
        .all()
    )
