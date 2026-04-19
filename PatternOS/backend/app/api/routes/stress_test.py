"""Stress Testing routes — portfolio CSV upload + scenario backtesting."""

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Body,
    UploadFile,
    File,
    BackgroundTasks,
    Form,
)
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Any
from datetime import datetime
from uuid import UUID
import pandas as pd
import io

from app.db.session import get_db, SessionLocal
from app.db.models import PortfolioSnapshot, StressTestRun
from app.stress_test.engine import run_stress_test_scenario, SCENARIOS

router = APIRouter(prefix="/stress-test", tags=["stress-test"])

# ============================================================================
# Pydantic Schemas
# ============================================================================


class PositionCreate(BaseModel):
    symbol: str
    qty: int = Field(..., gt=0)
    avg_price: float = Field(..., gt=0)


class PortfolioCreate(BaseModel):
    user_id: Optional[str] = None
    name: str = Field(..., min_length=1, max_length=200)
    positions: List[PositionCreate]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "My Tech Portfolio",
                "positions": [
                    {"symbol": "RELIANCE.NS", "qty": 100, "avg_price": 2500},
                    {"symbol": "TCS.NS", "qty": 50, "avg_price": 3500},
                ],
            }
        }
    )


class PortfolioOut(BaseModel):
    id: str
    user_id: Optional[str]
    name: str
    positions_json: List[Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StressTestRequest(BaseModel):
    scenario: str = Field(
        ..., description="Scenario key: 2008_crisis, 2020_covid, 2022_inflation, custom"
    )
    start_date: Optional[str] = None  # YYYY-MM-DD for custom
    end_date: Optional[str] = None  # YYYY-MM-DD for custom

    model_config = ConfigDict(json_schema_extra={"example": {"scenario": "2020_covid"}})


class StressTestResult(BaseModel):
    id: str
    portfolio_id: str
    scenario: str
    start_date: str
    end_date: str
    initial_value: float
    final_value: Optional[float]
    max_drawdown_pct: Optional[float]
    var_95: Optional[float]
    beta_weighted: Optional[float]
    results_json: Optional[dict]
    triggered_at: str
    completed_at: Optional[str]

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Portfolio CRUD
# ============================================================================


@router.post("/portfolio", response_model=PortfolioOut, status_code=201)
def create_portfolio(body: PortfolioCreate, db: Session = Depends(get_db)):
    """
    Create a portfolio from JSON positions.

    Accepts a list of {symbol, qty, avg_price}. Symbol format: "RELIANCE.NS" (NSE) or "AAPL" (NASDAQ).
    NSE symbols without .NS suffix will be auto-appended.
    """
    # Validate user_id
    if body.user_id and len(body.user_id) > 100:
        raise HTTPException(400, "user_id too long (max 100 chars)")

    # Normalize symbols
    normalized = []
    for pos in body.positions:
        sym = pos.symbol.strip().upper()
        # If symbol has no exchange suffix, assume NSE
        if "." not in sym:
            sym = f"{sym}.NS"
        normalized.append(
            {
                "symbol": sym,
                "qty": pos.qty,
                "avg_price": pos.avg_price,
            }
        )

    portfolio = PortfolioSnapshot(
        user_id=body.user_id,
        name=body.name,
        positions_json=normalized,
    )
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)
    return portfolio


@router.post("/portfolio/upload", response_model=PortfolioOut, status_code=201)
async def upload_portfolio_csv(
    file: UploadFile = File(...),
    user_id: Optional[str] = Form(None),
    name: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Upload portfolio as CSV.

    CSV columns: symbol,qty,avg_price
    Example:
        RELIANCE.NS,100,2500
        TCS.NS,50,3500

    NSE symbols can be provided with or without .NS suffix.
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(400, "Only CSV files supported")

    # Validate user_id length
    if user_id and len(user_id) > 100:
        raise HTTPException(400, "user_id too long (max 100 chars)")

    content = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(400, f"Invalid CSV: {e}")

    required = {"symbol", "qty", "avg_price"}
    if not required.issubset(df.columns):
        raise HTTPException(400, f"CSV must have columns: {', '.join(required)}")

    positions = []
    for _, row in df.iterrows():
        raw_sym = str(row["symbol"]).strip().upper()
        # If symbol has no exchange suffix, assume NSE
        if "." not in raw_sym:
            raw_sym = f"{raw_sym}.NS"
        positions.append(
            {
                "symbol": raw_sym,
                "qty": int(row["qty"]),
                "avg_price": float(row["avg_price"]),
            }
        )

    portfolio_name = name or (
        file.filename.rsplit(".", 1)[0] if file.filename else "Uploaded Portfolio"
    )
    portfolio = PortfolioSnapshot(
        user_id=user_id,
        name=portfolio_name,
        positions_json=positions,
    )
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)
    return portfolio


@router.get("/portfolio/{portfolio_id}", response_model=PortfolioOut)
def get_portfolio(portfolio_id: str, db: Session = Depends(get_db)):
    """Get a portfolio by ID."""
    p = db.query(PortfolioSnapshot).filter_by(id=portfolio_id).first()
    if not p:
        raise HTTPException(404, "Portfolio not found")
    return p


@router.put("/portfolio/{portfolio_id}", response_model=PortfolioOut)
def update_portfolio(
    portfolio_id: str,
    body: PortfolioCreate,
    db: Session = Depends(get_db),
):
    """Update portfolio positions."""
    p = db.query(PortfolioSnapshot).filter_by(id=portfolio_id).first()
    if not p:
        raise HTTPException(404, "Portfolio not found")

    p.name = body.name
    p.positions_json = [pos.model_dump() for pos in body.positions]
    p.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(p)
    return p


@router.delete("/portfolio/{portfolio_id}", status_code=204)
def delete_portfolio(portfolio_id: str, db: Session = Depends(get_db)):
    """Delete a portfolio."""
    p = db.query(PortfolioSnapshot).filter_by(id=portfolio_id).first()
    if not p:
        raise HTTPException(404, "Portfolio not found")
    db.delete(p)
    db.commit()
    return None


@router.get("/portfolio/{portfolio_id}/runs")
def list_portfolio_runs(portfolio_id: str, db: Session = Depends(get_db)):
    """List all stress test runs for a portfolio."""
    runs = (
        db.query(StressTestRun)
        .filter_by(portfolio_id=portfolio_id)
        .order_by(StressTestRun.triggered_at.desc())
        .limit(20)
        .all()
    )
    return [
        {
            "id": r.id,
            "scenario": r.scenario,
            "start_date": r.start_date.isoformat(),
            "end_date": r.end_date.isoformat(),
            "initial_value": r.initial_value,
            "final_value": r.final_value,
            "max_drawdown_pct": r.max_drawdown_pct,
            "var_95": r.var_95,
            "triggered_at": r.triggered_at.isoformat(),
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in runs
    ]


# ============================================================================
# Stress Test Execution
# ============================================================================


@router.get("/scenarios")
def list_scenarios():
    """
    List predefined stress test scenarios.

    Each scenario defines a historical crisis period with start/end dates.
    """
    # Format SCENARIOS for API response
    formatted = []
    for key, scenario in SCENARIOS.items():
        formatted.append({
            "key": key,
            "name": scenario.get("name", key),
            "start": scenario["start"],
            "end": scenario["end"],
            "description": scenario.get("description", "")
        })
    return formatted


@router.post("/run", response_model=StressTestResult)
def run_stress_test(
    portfolio_id: str,
    body: StressTestRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Execute stress test on a portfolio against a historical scenario (async).

    Returns the StressTestRun with initial status "queued". Poll GET /stress-test/run/{run_id}
    for completion. Results are stored and can be retrieved later.
    """
    portfolio = db.query(PortfolioSnapshot).filter_by(id=portfolio_id).first()
    if not portfolio:
        raise HTTPException(404, "Portfolio not found")

    # Create a queued run record
    run = StressTestRun(
        portfolio_id=UUID(portfolio_id),
        scenario=body.scenario,
        start_date=datetime.strptime(
            body.start_date or SCENARIOS[body.scenario]["start"], "%Y-%m-%d"
        ).date(),
        end_date=datetime.strptime(
            body.end_date or SCENARIOS[body.scenario]["end"], "%Y-%m-%d"
        ).date(),
        initial_value=0,  # will be filled by engine
        status="queued",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # Run computation in background
    background.add_task(
        _execute_stress_test,
        run_id=run.id,
        portfolio_id=portfolio_id,
        scenario_key=body.scenario,
        start_date=body.start_date,
        end_date=body.end_date,
    )

    return run


@router.get("/run/{run_id}", response_model=StressTestResult)
def get_stress_test_run(run_id: str, db: Session = Depends(get_db)):
    """Get details of a stress test run."""
    r = db.query(StressTestRun).filter_by(id=run_id).first()
    if not r:
        raise HTTPException(404, "Run not found")
    return r


def _execute_stress_test(
    run_id: str,
    portfolio_id: str,
    scenario_key: str,
    start_date: Optional[str],
    end_date: Optional[str],
):
    """
    Background task that executes the stress test and updates the run record.
    """
    from app.stress_test.engine import run_stress_test_scenario
    
    try:
        # Get fresh session for background task
        from app.db.session import SessionLocal
        local_db = SessionLocal()
        
        # Get portfolio and run
        portfolio = local_db.query(PortfolioSnapshot).filter_by(id=portfolio_id).first()
        run = local_db.query(StressTestRun).filter_by(id=run_id).first()
        
        if not portfolio or not run:
            if run:
                run.status = "failed"
                run.error_message = "Portfolio or run not found"
                local_db.commit()
            return
        
        # Update status to running
        run.status = "running"
        local_db.commit()
        
        # Execute stress test
        try:
            result_run = run_stress_test_scenario(
                portfolio=portfolio,
                scenario_key=scenario_key,
                start_date=start_date,
                end_date=end_date,
                db=local_db,
            )
            
            # Update run with results
            run.final_value = result_run.final_value
            run.max_drawdown_pct = result_run.max_drawdown_pct
            run.var_95 = result_run.var_95
            run.beta_weighted = result_run.beta_weighted
            run.results_json = result_run.results_json
            run.status = "completed"
            run.completed_at = datetime.utcnow()
            
        except Exception as e:
            run.status = "failed"
            run.error_message = str(e)
        
        local_db.commit()
        
    except Exception as e:
        # Log error but don't crash background task
        print(f"Error in stress test background task: {e}")
    finally:
        if 'local_db' in locals():
            local_db.close()
