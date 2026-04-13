from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import Universe
from app.api.schemas import UniverseItem, UniverseCreate

router = APIRouter(prefix="/universe", tags=["universe"])


@router.get("/indices", response_model=list[str])
def list_indices(db: Session = Depends(get_db)):
    rows = db.query(Universe.index_name).filter(Universe.index_name != None).distinct().all()
    return sorted([r[0] for r in rows if r[0]])


@router.get("/", response_model=list[UniverseItem])
def list_universe(
    active_only: bool = True,
    search: str = Query(None),
    index_name: str = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Universe)
    if active_only:
        q = q.filter(Universe.active == True)
    if search:
        pattern = f"%{search.upper()}%"
        q = q.filter(
            (func.upper(Universe.symbol).like(pattern)) |
            (func.upper(Universe.name).like(pattern))
        )
    if index_name:
        q = q.filter(Universe.index_name == index_name)
    return q.order_by(Universe.symbol).all()


@router.post("/", response_model=UniverseItem, status_code=201)
def add_symbol(body: UniverseCreate, db: Session = Depends(get_db)):
    existing = db.query(Universe).filter_by(symbol=body.symbol, exchange=body.exchange).first()
    if existing:
        raise HTTPException(400, "Symbol already exists")
    item = Universe(**body.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/{symbol_id}/toggle", response_model=UniverseItem)
def toggle_symbol(symbol_id: str, db: Session = Depends(get_db)):
    item = db.query(Universe).filter_by(id=symbol_id).first()
    if not item:
        raise HTTPException(404, "Symbol not found")
    item.active = not item.active
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{symbol_id}", status_code=204)
def delete_symbol(symbol_id: str, db: Session = Depends(get_db)):
    item = db.query(Universe).filter_by(id=symbol_id).first()
    if not item:
        raise HTTPException(404, "Symbol not found")
    db.delete(item)
    db.commit()
