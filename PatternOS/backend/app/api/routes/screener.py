"""Custom Screener routes — user-defined rule-based screening."""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Any
from datetime import datetime
from uuid import UUID

from app.db.session import get_db, SessionLocal
from app.db.models import (
    ScreenerCriteria,
    ScreenerResult,
    ScreenerRun,
    ScreenerTemplate,
)
from app.screener.engine import run_screener, get_screener_results

router = APIRouter(prefix="/screener", tags=["screener"])


# ============================================================================
# Pydantic Schemas
# ============================================================================


class ConditionModel(BaseModel):
    field: str
    operator: str
    value: Optional[Any] = None
    min: Optional[float] = None
    max: Optional[float] = None

    model_config = ConfigDict(extra="allow")


class RulesModel(BaseModel):
    logic: str = Field("AND", pattern="^(AND|OR)$")
    conditions: List[ConditionModel]

    model_config = ConfigDict(extra="allow")


class ScreenerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    asset_class: str = Field("equity", pattern="^(equity|mf)$")
    scope: str = Field("nifty500", pattern="^(nifty50|nifty500|custom)$")
    custom_symbols: Optional[List[str]] = None
    rules: RulesModel

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "RSI Oversold + Low PE",
                "asset_class": "equity",
                "scope": "nifty500",
                "rules": {
                    "logic": "AND",
                    "conditions": [
                        {"field": "rsi", "operator": "<", "value": 30},
                        {"field": "pe", "operator": "between", "min": 5, "max": 20},
                    ],
                },
            }
        }
    )


class ScreenerUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    rules: Optional[RulesModel] = None
    scope: Optional[str] = Field(None, pattern="^(nifty50|nifty500|custom)$")
    custom_symbols: Optional[List[str]] = None

    model_config = ConfigDict(extra="allow")


class ScreenerOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    asset_class: str
    scope: str
    custom_symbols: Optional[List[str]]
    rules: dict
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ScreenerResultOut(BaseModel):
    id: str
    symbol: str
    date: str
    passed: bool
    score: Optional[float]
    metrics: dict

    model_config = ConfigDict(from_attributes=True)


class ScreenerRunOut(BaseModel):
    id: str
    triggered_at: datetime
    symbols_total: int
    symbols_passed: int
    duration_sec: float
    status: str

    model_config = ConfigDict(from_attributes=True)


class ScreenerRunDetail(ScreenerRunOut):
    filters: Optional[dict] = None
    results: Optional[List[dict]] = None


class ScreenerTemplateOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    category: str
    asset_class: str
    rules_json: dict
    tags: Optional[List[str]] = None
    is_active: bool
    usage_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# CRUD
# ============================================================================


@router.post("/", response_model=ScreenerOut, status_code=201)
def create_screener(body: ScreenerCreate, db: Session = Depends(get_db)):
    """Create a new screener criteria."""
    screener = ScreenerCriteria(
        name=body.name,
        description=body.description,
        asset_class=body.asset_class,
        scope=body.scope,
        custom_symbols=body.custom_symbols,
        rules_json=body.rules.dict(),
    )
    db.add(screener)
    db.commit()
    db.refresh(screener)
    return screener


@router.get("/", response_model=List[ScreenerOut])
def list_screeners(
    asset_class: Optional[str] = Query(None, pattern="^(equity|mf)$"),
    db: Session = Depends(get_db),
):
    """List all saved screener criteria."""
    query = db.query(ScreenerCriteria)
    if asset_class:
        query = query.filter_by(asset_class=asset_class)
    screeners = query.order_by(ScreenerCriteria.updated_at.desc()).all()
    return screeners


@router.get("/presets", response_model=List[ScreenerTemplateOut])
def list_presets(
    category: Optional[str] = Query(None),
    asset_class: str = Query("equity", pattern="^(equity|mf)$"),
    db: Session = Depends(get_db),
):
    """
    List available screener preset templates.

    These are pre-defined rule sets users can instantly apply in the builder.

    Args:
        category: Filter by category ("technical", "fundamental", "momentum", "value")
        asset_class: "equity" or "mf"

    Returns:
        List of templates with name, description, rules_json, tags, usage_count
    """
    query = db.query(ScreenerTemplate).filter_by(
        is_active=True, asset_class=asset_class
    )
    if category:
        query = query.filter_by(category=category)
    templates = query.order_by(ScreenerTemplate.usage_count.desc()).limit(50).all()
    return templates


@router.get("/{id}", response_model=ScreenerOut)
def get_screener(id: str, db: Session = Depends(get_db)):
    """Get a single screener by ID."""
    screener = db.query(ScreenerCriteria).filter_by(id=id).first()
    if not screener:
        raise HTTPException(404, "Screener not found")
    return screener


@router.patch("/{id}", response_model=ScreenerOut)
def update_screener(id: str, body: ScreenerUpdate, db: Session = Depends(get_db)):
    """Update a screener."""
    screener = db.query(ScreenerCriteria).filter_by(id=id).first()
    if not screener:
        raise HTTPException(404, "Screener not found")

    updates = body.model_dump(exclude_unset=True)
    for key, val in updates.items():
        if key == "rules":
            setattr(screener, "rules_json", val.dict())
        else:
            setattr(screener, key, val)

    db.commit()
    db.refresh(screener)
    return screener


@router.delete("/{id}", status_code=204)
def delete_screener(id: str, db: Session = Depends(get_db)):
    """Delete a screener and all its results/runs."""
    screener = db.query(ScreenerCriteria).filter_by(id=id).first()
    if not screener:
        raise HTTPException(404, "Screener not found")
    db.delete(screener)
    db.commit()
    return None


# ============================================================================
# Execution
# ============================================================================


@router.post("/run")
def run_screener_now(
    body: dict,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Execute a screener scan.

    Request:
        { "screener_id": "...", "timeframe": "1d", "use_cache": true }

    Returns:
        { "run_id": "...", "status": "queued" }

    Execution happens async (background task). Poll /run/{run_id}/status for results.
    """
    screener_id = body.get("screener_id")
    timeframe = body.get("timeframe", "1d")
    use_cache = body.get("use_cache", True)

    if not screener_id:
        raise HTTPException(400, "screener_id required")

    # Validate screener exists
    screener = db.query(ScreenerCriteria).filter_by(id=screener_id).first()
    if not screener:
        raise HTTPException(404, "Screener not found")

    # Create run entry
    run = ScreenerRun(
        screener_id=screener_id,
        symbols_total=0,  # will update after
        symbols_passed=0,
        duration_sec=0,
        filters_json={"timeframe": timeframe, "use_cache": use_cache},
        status="queued",
    )
    db.add(run)
    db.commit()
    run_id = str(run.id)

    # Queue background task
    background.add_task(
        _run_screener_task, str(run_id), str(screener_id), timeframe, use_cache
    )

    return {"run_id": run_id, "status": "queued"}


def _run_screener_task(run_id: str, screener_id: str, timeframe: str, use_cache: bool):
    """Background task wrapper."""
    db = SessionLocal()
    try:
        result = run_screener(screener_id, timeframe, use_cache, db=db)

        # Update run record
        run = db.query(ScreenerRun).filter_by(id=run_id).first()
        if run:
            run.status = "completed"
            run.symbols_total = result["symbols_total"]
            run.symbols_passed = result["symbols_passed"]
            run.duration_sec = result["duration_seconds"]
            db.commit()
    except Exception as e:
        logger.error(f"Screener run {run_id} failed: {e}")
        run = db.query(ScreenerRun).filter_by(id=run_id).first()
        if run:
            run.status = "failed"
            db.commit()
    finally:
        db.close()


@router.get("/run/{run_id}/status", response_model=ScreenerRunOut)
def get_run_status(run_id: str, db: Session = Depends(get_db)):
    """Get status of a queued/completed run."""
    run = db.query(ScreenerRun).filter_by(id=run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    return run


@router.get("/run/{run_id}/results", response_model=List[ScreenerResultOut])
def get_run_results(run_id: str, db: Session = Depends(get_db)):
    """
    Get results for a specific run.

    Note: results are stored in screener_results table with screener_id and signal_date.
    We return all results that match the run's screener_id and cover that date.
    """
    run = db.query(ScreenerRun).filter_by(id=run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")

    # Fetch latest results for this screener
    return get_screener_results(
        str(run.screener_id), limit=500, passed_only=False, db=db
    )


@router.get("/{id}/results", response_model=List[ScreenerResultOut])
def get_screener_latest_results(
    id: str,
    passed_only: bool = Query(False),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Get latest scan results for a screener."""
    return get_screener_results(id, limit=limit, passed_only=passed_only, db=db)


@router.get("/{id}/runs", response_model=List[ScreenerRunOut])
def get_screener_runs(
    id: str, limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)
):
    """Get execution history for a screener."""
    screener = db.query(ScreenerCriteria).filter_by(id=id).first()
    if not screener:
        raise HTTPException(404, "Screener not found")

    runs = (
        db.query(ScreenerRun)
        .filter_by(screener_id=id)
        .order_by(ScreenerRun.triggered_at.desc())
        .limit(limit)
        .all()
    )
    return runs
