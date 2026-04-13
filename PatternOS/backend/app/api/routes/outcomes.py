from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import Outcome, Signal
from app.api.schemas import OutcomeCreate, OutcomeOut

router = APIRouter(prefix="/outcomes", tags=["outcomes"])


@router.get("/", response_model=list[OutcomeOut])
def list_outcomes(db: Session = Depends(get_db)):
    return db.query(Outcome).order_by(Outcome.recorded_at.desc()).all()


@router.post("/{signal_id}", response_model=OutcomeOut, status_code=201)
def create_outcome(signal_id: str, body: OutcomeCreate, db: Session = Depends(get_db)):
    s = db.query(Signal).filter_by(id=signal_id).first()
    if not s:
        raise HTTPException(404, "Signal not found")
    existing = db.query(Outcome).filter_by(signal_id=signal_id).first()
    if existing:
        for k, v in body.model_dump(exclude_none=True).items():
            setattr(existing, k, v)
        db.commit()
        db.refresh(existing)
        return existing
    o = Outcome(signal_id=signal_id, **body.model_dump())
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


@router.get("/{signal_id}", response_model=OutcomeOut)
def get_outcome(signal_id: str, db: Session = Depends(get_db)):
    o = db.query(Outcome).filter_by(signal_id=signal_id).first()
    if not o:
        raise HTTPException(404, "Outcome not found")
    return o
