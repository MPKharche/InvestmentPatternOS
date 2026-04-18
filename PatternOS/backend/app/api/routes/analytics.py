from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, desc, case
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.db.session import get_db
from app.db.models import (
    Pattern,
    Signal,
    Review,
    Outcome,
    LearningLog,
    PatternEvent,
    Universe,
)
from app.api.schemas import PatternStats
from app.llm.screener import llm_audit_pattern

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/patterns", response_model=list[PatternStats])
def pattern_stats(db: Session = Depends(get_db)):
    patterns = db.query(Pattern).all()
    results = []
    for p in patterns:
        total = db.query(func.count(Signal.id)).filter_by(pattern_id=p.id).scalar() or 0
        reviewed = (
            db.query(func.count(Review.id))
            .join(Signal)
            .filter(Signal.pattern_id == p.id)
            .scalar()
            or 0
        )
        executed = (
            db.query(func.count(Review.id))
            .join(Signal)
            .filter(Signal.pattern_id == p.id, Review.action == "executed")
            .scalar()
            or 0
        )
        hit = (
            db.query(func.count(Outcome.id))
            .join(Signal)
            .filter(Signal.pattern_id == p.id, Outcome.result == "hit_target")
            .scalar()
            or 0
        )
        stopped = (
            db.query(func.count(Outcome.id))
            .join(Signal)
            .filter(Signal.pattern_id == p.id, Outcome.result == "stopped_out")
            .scalar()
            or 0
        )
        avg_pnl = (
            db.query(func.avg(Outcome.pnl_pct))
            .join(Signal)
            .filter(Signal.pattern_id == p.id)
            .scalar()
        )

        win_rate = round((hit / executed) * 100, 1) if executed > 0 else None
        results.append(
            PatternStats(
                pattern_id=p.id,
                pattern_name=p.name,
                total_signals=total,
                reviewed=reviewed,
                executed=executed,
                hit_target=hit,
                stopped_out=stopped,
                win_rate=win_rate,
                avg_pnl_pct=round(avg_pnl, 2) if avg_pnl else None,
            )
        )
    return results


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    total_signals = db.query(func.count(Signal.id)).scalar() or 0
    pending = db.query(func.count(Signal.id)).filter_by(status="pending").scalar() or 0
    executed = (
        db.query(func.count(Review.id)).filter_by(action="executed").scalar() or 0
    )
    hit = db.query(func.count(Outcome.id)).filter_by(result="hit_target").scalar() or 0
    stopped = (
        db.query(func.count(Outcome.id)).filter_by(result="stopped_out").scalar() or 0
    )
    active_patterns = (
        db.query(func.count(Pattern.id)).filter_by(status="active").scalar() or 0
    )
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
        db.query(Outcome).join(Signal).filter(Signal.pattern_id == pattern_id).all()
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


# ─── Pattern Performance Analytics ────────────────────────────────────────────


@router.get("/pattern-performance")
def pattern_performance(
    pattern_id: str | None = None,
    timeframe: str | None = None,
    sector: str | None = None,
    min_signals: int = Query(10, ge=1),
    db: Session = Depends(get_db),
):
    """
    Detailed pattern performance metrics with filtering.

    Returns success rates, avg returns at multiple horizons (5d, 10d, 20d, etc.),
    max gain/loss, and confidence intervals.

    Filters:
      - pattern_id: specific pattern
      - timeframe: "1d", "1h", etc.
      - sector: universe sector filter
      - min_signals: minimum signals to include pattern (default 10)
    """
    # Build query from PatternEvent (backtest outcomes)
    query = db.query(PatternEvent).join(Pattern, PatternEvent.pattern_id == Pattern.id)

    if pattern_id:
        query = query.filter(PatternEvent.pattern_id == pattern_id)
    if timeframe:
        query = query.filter(PatternEvent.timeframe == timeframe)
    if sector:
        query = query.join(Universe, PatternEvent.symbol == Universe.symbol).filter(
            Universe.sector == sector
        )

    events = query.all()

    # Aggregate by pattern
    pattern_metrics = {}
    for ev in events:
        pid = ev.pattern_id
        if pid not in pattern_metrics:
            pattern_metrics[pid] = {
                "pattern_id": pid,
                "pattern_name": ev.pattern.name if ev.pattern else "Unknown",
                "count": 0,
                "wins": 0,
                "losses": 0,
                "returns_5d": [],
                "returns_10d": [],
                "returns_20d": [],
                "returns_63d": [],
                "max_gain_20d": [],
                "max_loss_20d": [],
            }
        stats = pattern_metrics[pid]
        stats["count"] += 1

        # Classify outcome
        outcome = ev.outcome
        if outcome == "hit_target":
            stats["wins"] += 1
        elif outcome == "stopped_out":
            stats["losses"] += 1

        # Collect returns
        for horizon in ["5d", "10d", "20d", "63d"]:
            val = getattr(ev, f"ret_{horizon}")
            if val is not None:
                stats[f"returns_{horizon}"].append(val)

        if ev.max_gain_20d is not None:
            stats["max_gain_20d"].append(ev.max_gain_20d)
        if ev.max_loss_20d is not None:
            stats["max_loss_20d"].append(ev.max_loss_20d)

    # Build response
    results = []
    for pid, s in pattern_metrics.items():
        if s["count"] < min_signals:
            continue
        win_rate = round((s["wins"] / s["count"]) * 100, 1) if s["count"] > 0 else 0.0

        def avg(lst):
            return round(sum(lst) / len(lst), 2) if lst else None

        results.append(
            {
                "pattern_id": pid,
                "pattern_name": s["pattern_name"],
                "signals": s["count"],
                "wins": s["wins"],
                "losses": s["losses"],
                "win_rate": win_rate,
                "avg_return_5d": avg(s["returns_5d"]),
                "avg_return_10d": avg(s["returns_10d"]),
                "avg_return_20d": avg(s["returns_20d"]),
                "avg_return_63d": avg(s["returns_63d"]),
                "avg_max_gain_20d": avg(s["max_gain_20d"]),
                "avg_max_loss_20d": avg(s["max_loss_20d"]),
            }
        )

    # Sort by win_rate desc, then signals desc
    results.sort(key=lambda x: (-x["win_rate"], -x["signals"]))
    return results


# ─── Sector Rotation Dashboard ────────────────────────────────────────────────


@router.get("/sectors")
def sector_heatmap(
    timeframe: str = Query("1d", regex="^(1d|1w|1mo)$"),
    days: int = Query(30, ge=5, le=365),
    db: Session = Depends(get_db),
):
    """
    Sector performance heatmap data.

    Returns list of sectors with:
      - name
      - avg_return (over period)
      - best_performing_stock
      - worst_performing_stock
      - symbol_count
    """
    # Get all stocks with sector info
    stocks = (
        db.query(Universe)
        .filter(Universe.sector.isnot(None), Universe.active == True)
        .all()
    )
    if not stocks:
        raise HTTPException(404, "No universe stocks with sector data")

    # Group by sector
    from collections import defaultdict

    sector_data = defaultdict(list)

    for stock in stocks:
        sector_name = stock.sector or "Unknown"
        sector_data[sector_name].append(stock.symbol)

    # For each sector, get avg performance from PatternEvent (using latest returns)
    result = []
    for sector_name, symbols in sector_data.items():
        # Get latest 20-day returns for stocks in this sector
        events = (
            db.query(PatternEvent)
            .filter(PatternEvent.symbol.in_(symbols))
            .filter(PatternEvent.ret_20d.isnot(None))
            .order_by(PatternEvent.detected_at.desc())
            .limit(len(symbols) * 3)  # get recent events
            .all()
        )

        if not events:
            continue

        # Take most recent event per symbol to avoid duplicates
        latest_by_symbol = {}
        for ev in events:
            if ev.symbol not in latest_by_symbol:
                latest_by_symbol[ev.symbol] = ev

        returns = [
            ev.ret_20d for ev in latest_by_symbol.values() if ev.ret_20d is not None
        ]
        if not returns:
            continue

        avg_return = round(sum(returns) / len(returns), 2)

        # Find best/worst performers
        sorted_by_ret = sorted(
            latest_by_symbol.items(), key=lambda x: x[1].ret_20d or 0
        )
        worst = sorted_by_ret[0][1] if sorted_by_ret else None
        best = sorted_by_ret[-1][1] if sorted_by_ret else None

        result.append(
            {
                "sector": sector_name,
                "avg_return": avg_return,
                "symbol_count": len(returns),
                "best_performer": best.symbol if best else None,
                "best_return": best.ret_20d if best else None,
                "worst_performer": worst.symbol if worst else None,
                "worst_return": worst.ret_20d if worst else None,
            }
        )

        result.sort(key=lambda x: -x["avg_return"])
        return result


@router.get("/outcomes")
def list_outcomes(
    pattern_id: str | None = None,
    symbol: str | None = None,
    result: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """
    List all pattern outcomes (historical backtest results).

    Optional filters:
      - pattern_id: filter by pattern
      - symbol: filter by stock symbol
      - result: "hit_target", "stopped_out", "partial", "open", "cancelled"
    """
    query = db.query(PatternEvent)

    if pattern_id:
        query = query.filter(PatternEvent.pattern_id == pattern_id)
    if symbol:
        query = query.filter(PatternEvent.symbol == symbol)
    if result:
        query = query.filter(PatternEvent.outcome == result)

    events = query.order_by(PatternEvent.detected_at.desc()).limit(limit).all()

    results = []
    for ev in events:
        results.append(
            {
                "pattern_id": ev.pattern_id,
                "symbol": ev.symbol,
                "timeframe": ev.timeframe,
                "detected_at": ev.detected_at,
                "entry_price": ev.entry_price,
                "outcome": ev.outcome,
                "ret_5d": ev.ret_5d,
                "ret_10d": ev.ret_10d,
                "ret_20d": ev.ret_20d,
                "ret_63d": ev.ret_63d,
                "max_gain_20d": ev.max_gain_20d,
                "max_loss_20d": ev.max_loss_20d,
                "user_feedback": ev.user_feedback,
            }
        )
    return results
