from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.charts.render import render_equity_chart_png, render_mf_nav_chart_png
from app.db.models import MFScheme, MFNavDaily
from app.db.session import get_db


router = APIRouter(prefix="/charts", tags=["charts"])


@router.get("/equity.png")
def equity_chart_png(
    symbol: str = Query(...),
    tf: str = Query("1d"),
    ind: str | None = Query(None),
):
    try:
        png = render_equity_chart_png(symbol, tf, indicators=ind)
    except Exception as exc:
        raise HTTPException(400, f"Chart render failed: {exc}")
    return Response(content=png, media_type="image/png")


@router.get("/mf.png")
def mf_chart_png(
    scheme_code: int = Query(...),
    ind: str | None = Query(None),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    limit: int = Query(800, ge=50, le=5000),
    db: Session = Depends(get_db),
):
    scheme = db.query(MFScheme).filter_by(scheme_code=scheme_code).first()
    if not scheme:
        raise HTTPException(404, "Scheme not found")

    q = db.query(MFNavDaily).filter_by(scheme_code=scheme_code)
    if from_date:
        q = q.filter(MFNavDaily.nav_date >= from_date)
    if to_date:
        q = q.filter(MFNavDaily.nav_date <= to_date)
    rows = q.order_by(MFNavDaily.nav_date.desc()).limit(limit).all()
    rows = list(reversed(rows))
    points = [(r.nav_date.isoformat(), float(r.nav)) for r in rows]
    try:
        png = render_mf_nav_chart_png(points, scheme.scheme_name or str(scheme_code), indicators=ind)
    except Exception as exc:
        raise HTTPException(400, f"Chart render failed: {exc}")
    return Response(content=png, media_type="image/png")

