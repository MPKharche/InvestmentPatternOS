from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import (
    MFScheme,
    MFNavDaily,
    MFNavMetricsDaily,
    MFFamilyHoldingsSnapshot,
    MFHolding,
    MFSectorAlloc,
    MFSignal,
    MFRulebook,
    MFRulebookVersion,
    MFIngestionRun,
    MFProviderState,
)
from app.api.schemas import (
    MFSchemeOut,
    MFSchemeDetailOut,
    MFSchemeUpdate,
    MFNavPoint,
    MFSignalOut,
    MFSignalReviewRequest,
    MFRulebookOut,
    MFRulebookCreate,
    MFRulebookUpdate,
    MFRulebookNewVersion,
    MFRulebookActivateVersion,
    MFRulebookVersionOut,
    MFIngestionStatus,
    MFProviderStateOut,
    MFProviderPauseRequest,
)
from app.mf.pipelines import (
    ingest_amfi_navall,
    ingest_monthly_holdings,
    bootstrap_holdings_history,
    backfill_nav_history_mfapi,
    check_external_links,
    gap_fill_nav_history_mfdata,
    ensure_default_mf_rulebook,
    ensure_curated_watchlist,
    compute_nav_metrics,
    generate_nav_signals,
    enrich_schemes_mfdata_batch,
    mark_monitored_for_schemes_with_nav,
    demote_monitored_outside_equity_direct_growth,
    sync_priority_amc_equity_direct_growth_monitored,
)
from app.mf.rules import validate_rulebook_v1
from app.mf.links import ensure_scheme_links
from app.mf.safety import pause_provider, resume_provider
from app.mf.safety import IngestionTask, provider_is_paused, task
from app.mf.mfdata import fetch_scheme, fetch_family_holdings, fetch_family_sectors
from app.config import get_settings
from app.scanner.indicators import compute_indicators, indicators_to_records
from app.scanner.talib_candles import detect_talib_candlestick_patterns
from app.scanner.pattern_detector import detect_chart_patterns, detect_candlestick_patterns
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import io
import requests
from app.charts.render import render_mf_nav_chart_png

router = APIRouter(prefix="/mf", tags=["mutual-funds"])
settings = get_settings()


_SEARCH_STOP = {
    "fund",
    "mutual",
    "mf",
    "plan",
    "direct",
    "regular",
    "growth",
    "dividend",
    "option",
    "value",
    "val",
}


def _search_tokens(raw: str) -> list[str]:
    raw = " ".join((raw or "").strip().split())
    toks = []
    for t in raw.split(" "):
        t = t.strip().lower()
        if len(t) < 2:
            continue
        if t in _SEARCH_STOP:
            continue
        toks.append(t)
    return toks[:8]


def _scheme_relevance_score(s: MFScheme, raw_query: str, tokens: list[str]) -> int:
    """
    Small, predictable relevance scorer (in-memory) for non-technical "it just works" search.
    """
    q = (raw_query or "").strip().lower()
    name = (s.scheme_name or "").lower()
    amc = (s.amc_name or "").lower()
    fam = (s.family_name or "").lower()
    cat = (s.category or "").lower()
    hay = f"{name} {amc} {fam} {cat}".strip()

    score = 0
    if q and q in name:
        score += 40
    if q and q in hay:
        score += 15

    amc_noise = {"asset", "management", "company", "limited", "ltd", "mutual", "trust", "pvt", "private"}
    for t in tokens:
        if t in name:
            score += 12
        # AMC names often contain generic words ("asset management company limited") that should not dominate ranking.
        if t in amc and t not in amc_noise:
            score += 6
        if t in fam:
            score += 6
        if t in cat:
            score += 4

    # Boost multi-token phrase presence in the scheme name (e.g., "dynamic asset").
    if len(tokens) >= 2:
        phrase = " ".join(tokens[:2])
        if phrase and phrase in name:
            score += 18

    # Soft tie-breakers: prefer more recently updated NAV pointers.
    if s.latest_nav_date:
        score += 1
    return score


def _parse_date_any(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    s = str(v).strip()
    if not s:
        return None
    # Try ISO first (YYYY-MM-DD or full datetime).
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        pass
    # Common non-ISO formats seen in free MF holdings sources.
    for fmt in (
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d %b %Y",
        "%d %B %Y",
        "%d-%b-%Y",
        "%d-%B-%Y",
    ):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    # Last resort: try the leading YYYY-MM-DD portion.
    if len(s) >= 10:
        head = s[:10]
        try:
            return datetime.strptime(head, "%Y-%m-%d").date()
        except Exception:
            return None
    return None


def _parse_dt_any(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    s = str(v).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        # Don't guess timezones; keep it unset if not parseable.
        return None


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        try:
            return float(v)
        except Exception:
            return None
    s = str(v).strip()
    if not s:
        return None
    # Common cleanup: remove commas and percent signs.
    s = s.replace(",", "").replace("%", "")
    try:
        return float(s)
    except Exception:
        return None


def _safe_task_finish(t: IngestionTask | None, *, ok: bool, error: str | None = None) -> None:
    if t is None:
        return
    try:
        t.finish(ok=ok, error=error)
    except Exception:
        # Never let observability writes break user-facing endpoints.
        pass


def _mf_nav_limit_for_tf(tf: str, base: int) -> int:
    """Fetch enough daily NAV rows before resampling to weekly/monthly bars."""
    tf = (tf or "1d").strip()
    b = max(int(base), 60)
    if tf == "1w":
        return min(10_000, max(b * 8, 400))
    if tf == "1M":
        return min(10_000, max(b * 35, 500))
    return min(10_000, b)


def _json_response(payload: dict[str, Any]) -> Response:
    """
    Return a JSON response without relying on Starlette's strict JSON encoding.
    This is used for user-triggered endpoints where we prefer "never 500" over strictness.
    """
    try:
        body = json.dumps(payload, ensure_ascii=False, default=str, allow_nan=True).encode("utf-8")
    except Exception:
        body = b'{"ok":true,"fetched":false,"error":"response_encoding_failed"}'
    return Response(content=body, media_type="application/json")


@router.get("/schemes", response_model=list[MFSchemeOut])
def list_schemes(
    monitored_only: bool = Query(False),
    query: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(MFScheme)
    if monitored_only:
        q = q.filter(MFScheme.monitored.is_(True))
    if query:
        raw = " ".join(query.strip().split())
        tokens = _search_tokens(raw)

        # Friendly token search + deterministic relevance ranking.
        token_filters = []
        for t in tokens:
            like = f"%{t}%"
            token_filters.append(
                or_(
                    MFScheme.scheme_name.ilike(like),
                    MFScheme.amc_name.ilike(like),
                    MFScheme.family_name.ilike(like),
                    MFScheme.category.ilike(like),
                )
            )

        # Prefer strict AND while typing (gives "best match first"); fallback to broad OR.
        candidates: list[MFScheme]
        if token_filters:
            strict = q.filter(and_(*token_filters))
            candidates = strict.order_by(MFScheme.scheme_code.asc()).limit(2000).all()
            if not candidates:
                broad = q.filter(or_(*token_filters))
                candidates = broad.order_by(MFScheme.scheme_code.asc()).limit(2000).all()
        else:
            like = f"%{raw}%"
            candidates = q.filter(MFScheme.scheme_name.ilike(like)).order_by(MFScheme.scheme_code.asc()).limit(2000).all()

        scored = []
        for s in candidates:
            sc = _scheme_relevance_score(s, raw, tokens)
            # Additional guard for multi-token queries: require at least one meaningful token
            # to match the scheme/category (prevents "asset management" noise from AMC names).
            if len(tokens) >= 2:
                name = (s.scheme_name or "").lower()
                cat = (s.category or "").lower()
                hits = sum(1 for t in tokens if (t in name) or (t in cat))
                req = 2 if len(tokens) >= 3 else 1
                if hits < req:
                    continue
            scored.append((s, sc))
        # Drop near-non-matches (prevents "ICICI only" results crowding the top).
        min_score = 12 if len(tokens) >= 2 else 8
        scored = [(s, sc) for (s, sc) in scored if sc >= min_score]
        scored.sort(
            key=lambda it: (
                -it[1],
                -(it[0].latest_nav_date.toordinal() if it[0].latest_nav_date else 0),
                it[0].scheme_code,
            )
        )
        rows = [s for (s, _sc) in scored]
        rows = rows[offset : offset + limit]
    else:
        rows = q.order_by(MFScheme.updated_at.desc().nullslast()).limit(limit).offset(offset).all()

    for s in rows:
        if ensure_scheme_links(s):
            db.add(s)
    db.commit()
    return rows


@router.get("/schemes/{scheme_code}", response_model=MFSchemeDetailOut)
def get_scheme(scheme_code: int, db: Session = Depends(get_db)):
    s = db.query(MFScheme).filter_by(scheme_code=scheme_code).first()
    if not s:
        raise HTTPException(404, "Scheme not found")
    # Lazy enrichment for single-scheme detail views (safe + cached):
    # This prevents "No family_id" and unlocks holdings/returns tiles without forcing the user
    # to run a full pipeline just to view one scheme.
    try:
        needs_enrich = (s.family_id is None) or (s.mfdata_fetched_at is None) or (s.mfdata_fetched_at < datetime.utcnow() - timedelta(hours=24))
        if needs_enrich and settings.MF_INGESTION_ENABLED and not provider_is_paused(db, "mfdata"):
            with task(db, run_id=None, provider="mfdata", endpoint_class="scheme", scheme_code=scheme_code) as t:
                ext = fetch_scheme(scheme_code, task=t)
            if ext:
                s.family_id = ext.family_id
                s.family_name = ext.family_name or s.family_name
                s.amc_name = ext.amc_name or s.amc_name
                s.amc_slug = ext.amc_slug or s.amc_slug
                s.category = ext.category or s.category
                s.plan_type = ext.plan_type or s.plan_type
                s.option_type = ext.option_type or s.option_type
                s.risk_label = ext.risk_label or s.risk_label
                s.expense_ratio = ext.expense_ratio if ext.expense_ratio is not None else s.expense_ratio
                s.aum = ext.aum if ext.aum is not None else s.aum
                s.min_sip = ext.min_sip if ext.min_sip is not None else s.min_sip
                s.min_lumpsum = ext.min_lumpsum if ext.min_lumpsum is not None else s.min_lumpsum
                s.exit_load = ext.exit_load or s.exit_load
                s.benchmark = ext.benchmark or s.benchmark
                s.morningstar_sec_id = ext.morningstar_sec_id or s.morningstar_sec_id
                if ext.value_research_fund_id is not None and s.value_research_fund_id is None:
                    s.value_research_fund_id = ext.value_research_fund_id
                if ext.yahoo_finance_symbol and not s.yahoo_finance_symbol:
                    s.yahoo_finance_symbol = ext.yahoo_finance_symbol
                if ext.launch_date:
                    try:
                        s.launch_date = datetime.fromisoformat(ext.launch_date).date()
                    except Exception:
                        pass
                if ext.returns is not None:
                    s.returns_json = ext.returns
                if ext.ratios is not None:
                    s.ratios_json = ext.ratios
                s.mfdata_fetched_at = datetime.utcnow()
    except Exception:
        # Detail pages should still work even if enrichment fails.
        pass
    if ensure_scheme_links(s):
        pass
    db.add(s)
    db.commit()
    db.refresh(s)
    nav_stats = (
        db.query(func.count(MFNavDaily.nav_date), func.min(MFNavDaily.nav_date), func.max(MFNavDaily.nav_date))
        .filter(MFNavDaily.scheme_code == scheme_code)
        .one()
    )
    n_days, d_min, d_max = int(nav_stats[0] or 0), nav_stats[1], nav_stats[2]
    base = MFSchemeOut.model_validate(s).model_dump()
    return MFSchemeDetailOut(**base, nav_days_in_db=n_days, nav_date_min=d_min, nav_date_max=d_max)


@router.patch("/schemes/{scheme_code}", response_model=MFSchemeOut)
def update_scheme(scheme_code: int, body: MFSchemeUpdate, db: Session = Depends(get_db)):
    s = db.query(MFScheme).filter_by(scheme_code=scheme_code).first()
    if not s:
        raise HTTPException(404, "Scheme not found")
    for key, value in body.dict(exclude_unset=True).items():
        setattr(s, key, value)
    ensure_scheme_links(s)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.get("/schemes/{scheme_code}/nav", response_model=list[MFNavPoint])
def scheme_nav(
    scheme_code: int,
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    limit: int = Query(400, ge=10, le=5000),
    db: Session = Depends(get_db),
):
    q = db.query(MFNavDaily).filter_by(scheme_code=scheme_code)
    if from_date:
        q = q.filter(MFNavDaily.nav_date >= from_date)
    if to_date:
        q = q.filter(MFNavDaily.nav_date <= to_date)
    rows = q.order_by(MFNavDaily.nav_date.desc()).limit(limit).all()
    # Return ascending for charting.
    rows = list(reversed(rows))
    return [MFNavPoint(nav_date=r.nav_date, nav=float(r.nav)) for r in rows]


@router.get("/schemes/{scheme_code}/metrics")
def scheme_metrics(
    scheme_code: int,
    nav_date: date | None = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(MFNavMetricsDaily).filter_by(scheme_code=scheme_code)
    if nav_date:
        q = q.filter(MFNavMetricsDaily.nav_date == nav_date)
    row = q.order_by(MFNavMetricsDaily.nav_date.desc()).first()
    if not row:
        # On-demand compute for scheme detail views (writes an upserted metrics row).
        # This keeps the UI useful even before a user enables monitoring/pipelines.
        latest = nav_date
        if latest is None:
            latest = db.query(MFNavDaily.nav_date).filter_by(scheme_code=scheme_code).order_by(MFNavDaily.nav_date.desc()).limit(1).scalar()
        if latest:
            compute_nav_metrics(db, scheme_code, latest)
            row = db.query(MFNavMetricsDaily).filter_by(scheme_code=scheme_code, nav_date=latest).first()
    if not row:
        return None
    return {
        "scheme_code": scheme_code,
        "nav_date": row.nav_date,
        "day_change": row.day_change,
        "day_change_pct": row.day_change_pct,
        "ret_7d": row.ret_7d,
        "ret_30d": row.ret_30d,
        "ret_90d": row.ret_90d,
        "ret_365d": row.ret_365d,
        "rolling_52w_high_nav": row.rolling_52w_high_nav,
        "is_52w_high": row.is_52w_high,
    }


@router.get("/schemes/{scheme_code}/ohlc")
def scheme_ohlc(
    scheme_code: int,
    tf: str = Query("1d", pattern=r"^(1d|1w|1M)$"),
    style: str = Query("candle", pattern=r"^(candle|heikin|line)$"),
    limit: int = Query(2500, ge=10, le=10000),
    db: Session = Depends(get_db),
):
    """Aggregated OHLC from NAV (daily → optional W/M resample) for MF charting."""
    s = db.query(MFScheme).filter_by(scheme_code=scheme_code).first()
    if not s:
        raise HTTPException(404, "Scheme not found")

    from app.mf.nav_ohlc import heikin_ashi, line_ohlc, nav_rows_to_daily_ohlc_df, ohlc_to_series_payload, resample_nav_ohlc

    rows = (
        db.query(MFNavDaily)
        .filter_by(scheme_code=scheme_code)
        .order_by(MFNavDaily.nav_date.desc())
        .limit(limit)
        .all()
    )
    if not rows:
        return {"scheme_code": scheme_code, "tf": tf, "style": style, "series": []}
    rows = list(reversed(rows))
    df = nav_rows_to_daily_ohlc_df(rows)
    df = resample_nav_ohlc(df, tf)
    if df is None or df.empty:
        return {"scheme_code": scheme_code, "tf": tf, "style": style, "series": []}
    if style == "heikin":
        df = heikin_ashi(df)
    elif style == "line":
        df = line_ohlc(df)
    return {"scheme_code": scheme_code, "tf": tf, "style": style, "series": ohlc_to_series_payload(df)}


@router.get("/schemes/{scheme_code}/indicators")
def scheme_indicators(
    scheme_code: int,
    tf: str = Query("1d", pattern=r"^(1d|1w|1M)$"),
    limit: int = Query(420, ge=50, le=10000),
    db: Session = Depends(get_db),
):
    """
    Indicator records for MF NAV series.
    Uses the same indicator engine as Equity (`INDICATOR_ENGINE=auto|ta|talib`).
    """
    from app.mf.nav_ohlc import nav_rows_to_daily_ohlc_df, resample_nav_ohlc

    nav_limit = _mf_nav_limit_for_tf(tf, limit)
    rows = (
        db.query(MFNavDaily)
        .filter_by(scheme_code=scheme_code)
        .order_by(MFNavDaily.nav_date.desc())
        .limit(nav_limit)
        .all()
    )
    if not rows:
        return []
    rows = list(reversed(rows))
    df = nav_rows_to_daily_ohlc_df(rows)
    df = resample_nav_ohlc(df, tf)
    if df is None or df.empty:
        return []
    idf = compute_indicators(df)
    return indicators_to_records(idf)


@router.get("/schemes/{scheme_code}/patterns")
def scheme_patterns(
    scheme_code: int,
    tf: str = Query("1d", pattern=r"^(1d|1w|1M)$"),
    lookback: int = Query(180, ge=30, le=500),
    db: Session = Depends(get_db),
):
    """
    Pattern detection on MF NAV series using pseudo OHLC:
    - chart patterns (best-effort; may be less meaningful for NAV)
    - candlestick patterns + TA-Lib candlestick patterns (more robust for quick markers)
    """
    from app.mf.nav_ohlc import nav_rows_to_daily_ohlc_df, resample_nav_ohlc

    nav_limit = _mf_nav_limit_for_tf(tf, max(lookback, 60))
    rows = (
        db.query(MFNavDaily)
        .filter_by(scheme_code=scheme_code)
        .order_by(MFNavDaily.nav_date.desc())
        .limit(nav_limit)
        .all()
    )
    if not rows:
        return {"chart_patterns": [], "candlestick_patterns": [], "talib_candlestick_patterns": []}
    rows = list(reversed(rows))
    df = nav_rows_to_daily_ohlc_df(rows)
    df = resample_nav_ohlc(df, tf)
    if df is None or df.empty:
        return {"chart_patterns": [], "candlestick_patterns": [], "talib_candlestick_patterns": []}
    return {
        "chart_patterns": detect_chart_patterns(df, lookback=lookback),
        "candlestick_patterns": detect_candlestick_patterns(df, lookback=min(30, lookback)),
        "talib_candlestick_patterns": detect_talib_candlestick_patterns(df, lookback=min(30, lookback)),
    }


@router.post("/schemes/{scheme_code}/enable")
def enable_scheme_analysis(scheme_code: int, db: Session = Depends(get_db)):
    """
    Non-technical "make it work" button:
    - mark scheme as monitored
    - enrich scheme fields (mfdata)
    - compute latest metrics
    - generate NAV signals for latest date
    """
    s = db.query(MFScheme).filter_by(scheme_code=scheme_code).first()
    if not s:
        raise HTTPException(404, "Scheme not found")

    s.monitored = True
    ensure_default_mf_rulebook(db)

    enriched = False
    if settings.MF_INGESTION_ENABLED and not provider_is_paused(db, "mfdata"):
        with task(db, run_id=None, provider="mfdata", endpoint_class="scheme", scheme_code=scheme_code) as t:
            ext = fetch_scheme(scheme_code, task=t)
        if ext:
            s.family_id = ext.family_id
            s.family_name = ext.family_name or s.family_name
            s.amc_name = ext.amc_name or s.amc_name
            s.amc_slug = ext.amc_slug or s.amc_slug
            s.category = ext.category or s.category
            s.plan_type = ext.plan_type or s.plan_type
            s.option_type = ext.option_type or s.option_type
            s.risk_label = ext.risk_label or s.risk_label
            s.expense_ratio = ext.expense_ratio if ext.expense_ratio is not None else s.expense_ratio
            s.aum = ext.aum if ext.aum is not None else s.aum
            s.min_sip = ext.min_sip if ext.min_sip is not None else s.min_sip
            s.min_lumpsum = ext.min_lumpsum if ext.min_lumpsum is not None else s.min_lumpsum
            s.exit_load = ext.exit_load or s.exit_load
            s.benchmark = ext.benchmark or s.benchmark
            s.morningstar_sec_id = ext.morningstar_sec_id or s.morningstar_sec_id
            if ext.value_research_fund_id is not None and s.value_research_fund_id is None:
                s.value_research_fund_id = ext.value_research_fund_id
            if ext.yahoo_finance_symbol and not s.yahoo_finance_symbol:
                s.yahoo_finance_symbol = ext.yahoo_finance_symbol
            if ext.returns is not None:
                s.returns_json = ext.returns
            if ext.ratios is not None:
                s.ratios_json = ext.ratios
            s.mfdata_fetched_at = datetime.utcnow()
            enriched = True

    ensure_scheme_links(s)
    db.add(s)
    db.commit()
    db.refresh(s)

    nav_date = s.latest_nav_date
    if nav_date is None:
        nav_date = db.query(MFNavDaily.nav_date).filter_by(scheme_code=scheme_code).order_by(MFNavDaily.nav_date.desc()).limit(1).scalar()
    if nav_date is None:
        return {"ok": True, "monitored": True, "enriched": enriched, "metrics": 0, "signals": 0}

    m = compute_nav_metrics(db, scheme_code, nav_date)
    created = 0
    if m:
        created = generate_nav_signals(db, s, nav_date, m)
    return {"ok": True, "monitored": True, "enriched": enriched, "metrics": 1 if m else 0, "signals": created, "nav_date": nav_date.isoformat()}


@router.post("/families/{family_id}/holdings/refresh")
def refresh_family_holdings(
    family_id: int,
    db: Session = Depends(get_db),
):
    """
    Refresh the latest monthly holdings snapshot for a single family_id (idempotent).
    This is used by scheme detail pages to "just fetch holdings" without running the full monthly job.
    """
    try:
        if not settings.MF_INGESTION_ENABLED or not settings.MF_HOLDINGS_ENABLED:
            return _json_response({"ok": True, "skipped": True, "reason": "MF_HOLDINGS_ENABLED=false or MF_INGESTION_ENABLED=false"})
        if provider_is_paused(db, "mfdata"):
            return _json_response({"ok": True, "skipped": True, "reason": "mfdata provider paused"})

        today = datetime.now().date()
        m = date(today.year, today.month, 1)

        # UI-triggered fetch: never hard-fail the request with a 500.
        t: IngestionTask | None = None
        try:
            t = IngestionTask(db, run_id=None, provider="mfdata", endpoint_class="holdings", family_id=family_id)
            data = fetch_family_holdings(int(family_id), task=t)
            _safe_task_finish(t, ok=True)
        except Exception as e:
            _safe_task_finish(t, ok=False, error=str(e))
            return _json_response({"ok": True, "fetched": False, "error": str(e)})
        if not data:
            return _json_response({"ok": True, "fetched": False})

        snap = MFFamilyHoldingsSnapshot(
            family_id=int(family_id),
            month=m,
            total_aum=_to_float(data.get("total_aum")),
            equity_pct=_to_float(data.get("equity_pct")),
            debt_pct=_to_float(data.get("debt_pct")),
            other_pct=_to_float(data.get("other_pct")),
            fetched_at=_parse_dt_any(data.get("fetched_at")),
            raw_json=data,
        )
        db.merge(snap)
        db.commit()

        db.query(MFHolding).filter_by(family_id=int(family_id), month=m).delete()
        db.query(MFSectorAlloc).filter_by(family_id=int(family_id), month=m).delete()
        db.commit()

        seen_holdings: set[tuple[str, str]] = set()

        def add_list(items: list[dict[str, Any]], holding_type: str):
            for it in items:
                if not isinstance(it, dict):
                    continue
                name = str(it.get("name") or "").strip()
                if not name:
                    continue
                key = (holding_type, name.lower())
                if key in seen_holdings:
                    continue
                seen_holdings.add(key)
                maturity = _parse_date_any(it.get("maturity_date"))
                db.add(
                    MFHolding(
                        family_id=int(family_id),
                        month=m,
                        holding_type=holding_type,
                        name=name,
                        weight_pct=_to_float(it.get("weight_pct")),
                        market_value=_to_float(it.get("market_value")),
                        quantity=_to_float(it.get("quantity")),
                        month_change_qty=_to_float(it.get("month_change_qty")),
                        month_change_pct=_to_float(it.get("month_change_pct")),
                        credit_rating=it.get("credit_rating"),
                        maturity_date=maturity,
                        isin=it.get("isin"),
                        ticker=(it.get("ticker") or it.get("holding_type")),
                        sector=it.get("sector"),
                    )
                )

        add_list(data.get("equity_holdings") or [], "equity")
        add_list(data.get("debt_holdings") or [], "debt")
        add_list(data.get("other_holdings") or [], "other")
        db.commit()

        t2: IngestionTask | None = None
        try:
            t2 = IngestionTask(db, run_id=None, provider="mfdata", endpoint_class="sectors", family_id=family_id)
            sectors = fetch_family_sectors(int(family_id), task=t2) or []
            _safe_task_finish(t2, ok=True)
        except Exception as e:
            _safe_task_finish(t2, ok=False, error=str(e))
            sectors = []

        for it in sectors:
            if not isinstance(it, dict):
                continue
            sec = str(it.get("sector") or it.get("name") or "")
            w = _to_float(it.get("weight_pct"))
            if not sec or w is None:
                continue
            db.add(MFSectorAlloc(family_id=int(family_id), month=m, sector=sec, weight_pct=float(w)))
        db.commit()

        return _json_response({"ok": True, "fetched": True, "month": m.isoformat()})
    except Exception as e:
        # Absolute last-resort: this endpoint must never 500 in the UI.
        return _json_response({"ok": True, "fetched": False, "error": str(e)})


@router.get("/families/{family_id}/holdings")
def family_holdings(
    family_id: int,
    month: date | None = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(MFFamilyHoldingsSnapshot).filter_by(family_id=family_id)
    if month:
        q = q.filter(MFFamilyHoldingsSnapshot.month == month)
    snap = q.order_by(MFFamilyHoldingsSnapshot.month.desc()).first()
    if not snap:
        return None
    holdings = db.query(MFHolding).filter_by(family_id=family_id, month=snap.month).all()
    sectors = db.query(MFSectorAlloc).filter_by(family_id=family_id, month=snap.month).all()
    return {
        "family_id": family_id,
        "month": snap.month,
        "snapshot": {
            "total_aum": snap.total_aum,
            "equity_pct": snap.equity_pct,
            "debt_pct": snap.debt_pct,
            "other_pct": snap.other_pct,
            "fetched_at": snap.fetched_at,
        },
        "holdings": [
            {
                "holding_type": h.holding_type,
                "name": h.name,
                "weight_pct": h.weight_pct,
                "market_value": h.market_value,
                "quantity": h.quantity,
                "month_change_qty": h.month_change_qty,
                "month_change_pct": h.month_change_pct,
                "credit_rating": h.credit_rating,
                "maturity_date": h.maturity_date,
                "isin": h.isin,
                "ticker": h.ticker,
                "sector": h.sector,
            }
            for h in holdings
        ],
        "sectors": [{"sector": s.sector, "weight_pct": s.weight_pct} for s in sectors],
    }


@router.get("/signals", response_model=list[MFSignalOut])
def list_signals(
    status: str = Query("pending"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(MFSignal)
    if status != "all":
        q = q.filter(MFSignal.status == status)
    rows = q.order_by(MFSignal.triggered_at.desc()).limit(limit).all()
    # Attach scheme name for UI.
    out = []
    for r in rows:
        scheme = db.query(MFScheme).filter_by(scheme_code=r.scheme_code).first()
        out.append(
            MFSignalOut(
                id=str(r.id),
                scheme_code=r.scheme_code,
                scheme_name=(scheme.scheme_name if scheme else None),
                family_id=r.family_id,
                signal_type=r.signal_type,
                nav_date=r.nav_date,
                triggered_at=r.triggered_at,
                base_score=r.base_score,
                confidence_score=r.confidence_score,
                status=r.status,
                llm_analysis=r.llm_analysis,
                context_json=r.context_json,
                reviewed_at=r.reviewed_at,
                review_action=r.review_action,
                review_notes=r.review_notes,
            )
        )
    return out


@router.post("/signals/{signal_id}/review")
def review_signal(signal_id: str, body: MFSignalReviewRequest, db: Session = Depends(get_db)):
    s = db.query(MFSignal).filter_by(id=signal_id).first()
    if not s:
        raise HTTPException(404, "Signal not found")
    if body.action not in ("reviewed", "dismissed", "watching", "acted"):
        raise HTTPException(400, "Invalid action")
    s.status = "reviewed" if body.action != "dismissed" else "dismissed"
    s.reviewed_at = datetime.utcnow()
    s.review_action = body.action
    s.review_notes = body.notes
    db.add(s)
    db.commit()
    return {"ok": True}


@router.get("/rulebooks", response_model=list[MFRulebookOut])
def list_rulebooks(db: Session = Depends(get_db)):
    ensure_default_mf_rulebook(db)
    rows = db.query(MFRulebook).order_by(MFRulebook.updated_at.desc()).all()
    return rows


@router.post("/rulebooks", response_model=MFRulebookOut, status_code=201)
def create_rulebook(body: MFRulebookCreate, db: Session = Depends(get_db)):
    try:
        validate_rulebook_v1(body.rulebook_json)
    except ValueError as e:
        raise HTTPException(400, str(e))
    rb = MFRulebook(name=body.name, status=body.status, current_version=1)
    db.add(rb)
    db.flush()
    ver = MFRulebookVersion(rulebook_id=rb.id, version=1, rulebook_json=body.rulebook_json, change_summary=body.change_summary)
    db.add(ver)
    db.commit()
    db.refresh(rb)
    return rb


@router.put("/rulebooks/{rulebook_id}", response_model=MFRulebookOut)
def update_rulebook(rulebook_id: str, body: MFRulebookUpdate, db: Session = Depends(get_db)):
    rb = db.query(MFRulebook).filter_by(id=rulebook_id).first()
    if not rb:
        raise HTTPException(404, "Rulebook not found")
    if body.name is not None:
        rb.name = body.name
    if body.status is not None:
        if body.status not in ("active", "inactive", "archived"):
            raise HTTPException(400, "Invalid status")
        rb.status = body.status
    db.add(rb)
    db.commit()
    db.refresh(rb)
    return rb


@router.get("/rulebooks/{rulebook_id}/current", response_model=MFRulebookVersionOut)
def current_rulebook_version(rulebook_id: str, db: Session = Depends(get_db)):
    rb = db.query(MFRulebook).filter_by(id=rulebook_id).first()
    if not rb:
        raise HTTPException(404, "Rulebook not found")
    ver = (
        db.query(MFRulebookVersion)
        .filter_by(rulebook_id=rulebook_id, version=rb.current_version)
        .first()
    )
    if not ver:
        raise HTTPException(404, "Current version not found")
    return ver


@router.post("/rulebooks/{rulebook_id}/versions", response_model=MFRulebookVersionOut, status_code=201)
def create_rulebook_version(rulebook_id: str, body: MFRulebookNewVersion, db: Session = Depends(get_db)):
    rb = db.query(MFRulebook).filter_by(id=rulebook_id).first()
    if not rb:
        raise HTTPException(404, "Rulebook not found")
    try:
        validate_rulebook_v1(body.rulebook_json)
    except ValueError as e:
        raise HTTPException(400, str(e))

    latest = (
        db.query(MFRulebookVersion.version)
        .filter_by(rulebook_id=rulebook_id)
        .order_by(MFRulebookVersion.version.desc())
        .first()
    )
    next_ver = int(latest[0]) + 1 if latest else 1
    ver = MFRulebookVersion(
        rulebook_id=rulebook_id,
        version=next_ver,
        rulebook_json=body.rulebook_json,
        change_summary=body.change_summary,
    )
    db.add(ver)
    if body.set_current:
        rb.current_version = next_ver
        rb.status = "active"
        db.add(rb)
    db.commit()
    db.refresh(ver)
    return ver


@router.post("/rulebooks/{rulebook_id}/activate", response_model=MFRulebookOut)
def activate_rulebook_version(rulebook_id: str, body: MFRulebookActivateVersion, db: Session = Depends(get_db)):
    rb = db.query(MFRulebook).filter_by(id=rulebook_id).first()
    if not rb:
        raise HTTPException(404, "Rulebook not found")
    ver = db.query(MFRulebookVersion).filter_by(rulebook_id=rulebook_id, version=body.version).first()
    if not ver:
        raise HTTPException(404, "Version not found")
    rb.current_version = body.version
    rb.status = "active"
    db.add(rb)
    db.commit()
    db.refresh(rb)
    return rb


@router.get("/rulebooks/{rulebook_id}/versions", response_model=list[MFRulebookVersionOut])
def rulebook_versions(rulebook_id: str, db: Session = Depends(get_db)):
    rows = db.query(MFRulebookVersion).filter_by(rulebook_id=rulebook_id).order_by(MFRulebookVersion.version.desc()).all()
    return rows


@router.post("/pipeline/nav/run")
def run_nav_pipeline(db: Session = Depends(get_db)):
    stats = ingest_amfi_navall(db)
    return {"ok": True, "stats": stats}


@router.post("/pipeline/holdings/run")
def run_holdings_pipeline(db: Session = Depends(get_db)):
    stats = ingest_monthly_holdings(db)
    return {"ok": True, "stats": stats}


@router.post("/pipeline/holdings/bootstrap")
def run_holdings_bootstrap(
    db: Session = Depends(get_db),
    months: int = Query(240, ge=1, le=600, description="Months of holdings history to pull (capped by MF_HOLDINGS_BOOTSTRAP_MAX_MONTHS in .env)."),
):
    cap = min(int(months), int(get_settings().MF_HOLDINGS_BOOTSTRAP_MAX_MONTHS))
    stats = bootstrap_holdings_history(db, months=cap)
    return {"ok": True, "stats": stats}


@router.post("/pipeline/backfill/run")
def run_backfill_pipeline(
    db: Session = Depends(get_db),
    start_date: date | None = Query(None, description="Earliest date for MFAPI windowed backfill (default in code: 2000-01-01)."),
):
    sd = start_date or date(2006, 1, 1)
    stats = backfill_nav_history_mfapi(db, start_date=sd)
    return {"ok": True, "stats": stats}


@router.post("/pipeline/nav/gapfill")
def run_nav_gapfill_pipeline(
    db: Session = Depends(get_db),
    max_schemes: int | None = Query(None, ge=1, le=50_000, description="Override MF_GAPFILL_MAX_SCHEMES for this run."),
):
    stats = gap_fill_nav_history_mfdata(db, max_schemes=max_schemes)
    return {"ok": True, "stats": stats}


@router.post("/pipeline/enrich/batch")
def run_enrich_batch(
    db: Session = Depends(get_db),
    monitored_only: bool = Query(True, description="If false, enriches any scheme missing/stale mfdata (slower)."),
    max_schemes: int = Query(200, ge=1, le=5000),
):
    stats = enrich_schemes_mfdata_batch(db, monitored_only=monitored_only, max_per_run=max_schemes)
    return {"ok": True, "stats": stats}


@router.post("/pipeline/watchlist/mark-with-nav")
def run_mark_monitored_with_nav(
    db: Session = Depends(get_db),
    limit: int | None = Query(None, description="Max schemes to mark; null uses MF_MARK_MONITORED_NAV_LIMIT (0 = unlimited)."),
):
    stats = mark_monitored_for_schemes_with_nav(db, limit=limit)
    return {"ok": True, "stats": stats}


@router.post("/pipeline/watchlist/demote-non-equity-dg")
def run_demote_watchlist_outside_equity_dg(db: Session = Depends(get_db)):
    """Clear monitored flags for schemes outside ICICI/HDFC/Axis/Mirae equity Direct Growth (excl. Regular/IDCW). Prefer `sync-priority-amc` for a full realign."""
    stats = demote_monitored_outside_equity_direct_growth(db)
    return {"ok": True, "stats": stats}


@router.post("/pipeline/watchlist/sync-priority-amc")
def run_sync_priority_amc_watchlist(db: Session = Depends(get_db)):
    """
    Demote everything outside ICICI/HDFC/Axis/Mirae equity Direct Growth (excl. Regular & IDCW),
    then promote all schemes that match that scope. Use after changing scope rules or seeding NAV.
    """
    stats = sync_priority_amc_equity_direct_growth_monitored(db)
    return {"ok": True, "stats": stats}


@router.post("/pipeline/links/check")
def run_links_check(db: Session = Depends(get_db)):
    stats = check_external_links(db)
    return {"ok": True, "stats": stats}


@router.get("/pipeline/status", response_model=MFIngestionStatus)
def pipeline_status(db: Session = Depends(get_db)):
    ensure_curated_watchlist(db)
    latest_nav = db.query(MFIngestionRun).filter_by(run_type="daily_nav").order_by(MFIngestionRun.started_at.desc()).first()
    latest_holdings = db.query(MFIngestionRun).filter_by(run_type="monthly_holdings").order_by(MFIngestionRun.started_at.desc()).first()
    def dump_run(r: MFIngestionRun | None):
        if not r:
            return None
        return {
            "id": str(r.id),
            "run_type": r.run_type,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
            "status": r.status,
            "stats_json": r.stats_json,
            "error_text": r.error_text,
        }
    return MFIngestionStatus(
        latest_nav_run=dump_run(latest_nav),
        latest_holdings_run=dump_run(latest_holdings),
        monitored_schemes=db.query(MFScheme).filter_by(monitored=True).count(),
        schemes_total=db.query(MFScheme).count(),
        nav_rows_total=db.query(MFNavDaily).count(),
        signals_pending=db.query(MFSignal).filter_by(status="pending").count(),
        providers=[
            {
                "provider": r.provider,
                "paused_until": r.paused_until,
                "consecutive_failures": r.consecutive_failures,
                "last_error": r.last_error,
                "updated_at": r.updated_at,
            }
            for r in db.query(MFProviderState).order_by(MFProviderState.provider.asc()).all()
        ],
    )


@router.get("/nav/coverage")
def nav_coverage(
    from_year: int = Query(2000, ge=1900, le=2100),
    to_year: int = Query(2100, ge=1900, le=2100),
    monitored_only: bool = Query(False),
    amc_query: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """
    Returns year-wise NAV coverage so you can spot gaps (schemes covered per year, row counts, date bounds).
    """
    clauses = ["EXTRACT(YEAR FROM n.nav_date) BETWEEN :from_year AND :to_year"]
    params: dict[str, Any] = {"from_year": from_year, "to_year": to_year}
    join = ""
    where_extra = ""

    if monitored_only or amc_query:
        join = "JOIN mf_schemes s ON s.scheme_code = n.scheme_code"
    if monitored_only:
        clauses.append("s.monitored = TRUE")
    if amc_query:
        clauses.append("s.amc_name ILIKE :amc_like")
        params["amc_like"] = f"%{amc_query.strip()}%"

    where_extra = " AND ".join(clauses)

    q = text(
        f"""
        SELECT
          EXTRACT(YEAR FROM n.nav_date)::int AS year,
          COUNT(DISTINCT n.scheme_code)::int AS schemes_with_nav,
          COUNT(*)::bigint AS nav_rows,
          MIN(n.nav_date) AS min_date,
          MAX(n.nav_date) AS max_date
        FROM mf_nav_daily n
        {join}
        WHERE {where_extra}
        GROUP BY 1
        ORDER BY 1
        """
    )
    rows = db.execute(q, params).mappings().all()
    return {"from_year": from_year, "to_year": to_year, "rows": [dict(r) for r in rows]}


@router.get("/nav/quality")
def nav_quality(
    monitored_only: bool = Query(True),
    amc_query: str | None = Query(None),
    gap_days: int = Query(10, ge=2, le=60),
    limit: int = Query(200, ge=10, le=2000),
    db: Session = Depends(get_db),
):
    """
    Coverage & quality report for NAV series in mf_nav_daily.

    Returns:
    - latest AMFI date
    - % schemes updated on latest AMFI date
    - per-scheme earliest/latest + max gap days + gap count > threshold
    """
    params: dict[str, Any] = {"gap_days": gap_days, "limit": limit}

    scheme_filter = []
    if monitored_only:
        scheme_filter.append("s.monitored = TRUE")
    if amc_query:
        scheme_filter.append("s.amc_name ILIKE :amc_like")
        params["amc_like"] = f"%{amc_query.strip()}%"
    scheme_where = ("WHERE " + " AND ".join(scheme_filter)) if scheme_filter else ""

    latest_amfi = db.execute(text("SELECT MAX(nav_date) AS d FROM mf_nav_daily WHERE source='amfi'")).mappings().first()
    latest_amfi_date = latest_amfi["d"] if latest_amfi else None

    q = text(
        f"""
        WITH scoped AS (
          SELECT s.scheme_code
          FROM mf_schemes s
          {scheme_where}
        ),
        series AS (
          SELECT n.scheme_code, n.nav_date,
                 LAG(n.nav_date) OVER (PARTITION BY n.scheme_code ORDER BY n.nav_date) AS prev_date
          FROM mf_nav_daily n
          JOIN scoped sc ON sc.scheme_code = n.scheme_code
        ),
        agg AS (
          SELECT
            scheme_code,
            MIN(nav_date) AS min_date,
            MAX(nav_date) AS max_date,
            COUNT(*)::bigint AS rows,
            MAX((nav_date - prev_date)) FILTER (WHERE prev_date IS NOT NULL) AS max_gap_days,
            SUM(CASE WHEN prev_date IS NOT NULL AND (nav_date - prev_date) > :gap_days THEN 1 ELSE 0 END)::int AS gaps_gt
          FROM series
          GROUP BY scheme_code
        )
        SELECT
          a.scheme_code,
          s.scheme_name,
          s.amc_name,
          a.min_date,
          a.max_date,
          a.rows,
          COALESCE(a.max_gap_days, 0)::int AS max_gap_days,
          a.gaps_gt
        FROM agg a
        JOIN mf_schemes s ON s.scheme_code = a.scheme_code
        ORDER BY a.max_gap_days DESC, a.gaps_gt DESC, a.rows ASC
        LIMIT :limit
        """
    )
    rows = db.execute(q, params).mappings().all()

    # Count schemes with zero NAV rows in scope.
    q0 = text(
        f"""
        SELECT COUNT(*)::int AS zero_nav
        FROM mf_schemes s
        {scheme_where}
        AND NOT EXISTS (SELECT 1 FROM mf_nav_daily n WHERE n.scheme_code = s.scheme_code)
        """
    ) if scheme_where else text(
        """
        SELECT COUNT(*)::int AS zero_nav
        FROM mf_schemes s
        WHERE NOT EXISTS (SELECT 1 FROM mf_nav_daily n WHERE n.scheme_code = s.scheme_code)
        """
    )
    zero_nav = db.execute(q0, params).mappings().first()
    zero_nav_count = int(zero_nav["zero_nav"]) if zero_nav else 0

    pct_updated = None
    if latest_amfi_date:
        qpct = text(
            f"""
            WITH scoped AS (
              SELECT s.scheme_code
              FROM mf_schemes s
              {scheme_where}
            ),
            latest_per AS (
              SELECT n.scheme_code, MAX(n.nav_date) AS max_date
              FROM mf_nav_daily n
              JOIN scoped sc ON sc.scheme_code = n.scheme_code
              GROUP BY 1
            )
            SELECT
              COUNT(*) FILTER (WHERE max_date = :latest)::int AS ok,
              COUNT(*)::int AS total
            FROM latest_per
            """
        )
        r = db.execute(qpct, {**params, "latest": latest_amfi_date}).mappings().first()
        if r and r["total"]:
            pct_updated = float((int(r["ok"]) / int(r["total"])) * 100.0)

    return {
        "latest_amfi_date": latest_amfi_date,
        "gap_days": gap_days,
        "pct_schemes_updated_on_latest_amfi": pct_updated,
        "zero_nav_schemes": zero_nav_count,
        "rows": [dict(r) for r in rows],
    }


@router.get("/providers", response_model=list[MFProviderStateOut])
def list_providers(db: Session = Depends(get_db)):
    for p in ("amfi", "mfdata", "mfapi", "valueresearch", "morningstar", "yahoo"):
        if not db.query(MFProviderState).filter_by(provider=p).first():
            db.add(MFProviderState(provider=p))
    db.commit()
    return db.query(MFProviderState).order_by(MFProviderState.provider.asc()).all()


@router.post("/providers/{provider}/pause", response_model=MFProviderStateOut)
def pause_provider_route(provider: str, body: MFProviderPauseRequest, db: Session = Depends(get_db)):
    if provider not in ("amfi", "mfdata", "mfapi", "valueresearch", "morningstar", "yahoo"):
        raise HTTPException(400, "Unknown provider")
    return pause_provider(db, provider, minutes=body.minutes, reason=body.reason)


@router.post("/providers/{provider}/resume", response_model=MFProviderStateOut)
def resume_provider_route(provider: str, db: Session = Depends(get_db)):
    if provider not in ("amfi", "mfdata", "mfapi", "valueresearch", "morningstar", "yahoo"):
        raise HTTPException(400, "Unknown provider")
    return resume_provider(db, provider)


@router.get("/report/{scheme_code}", response_class=Response)
def mf_report_pdf(scheme_code: int, db: Session = Depends(get_db)):
    scheme = db.query(MFScheme).filter_by(scheme_code=scheme_code).first()
    if not scheme:
        raise HTTPException(404, "Scheme not found")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=0.5*inch, leftMargin=0.5*inch,
                            topMargin=0.75*inch, bottomMargin=0.75*inch)
    story = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('CustomTitle', parent=styles['Title'], fontSize=18, spaceAfter=12, alignment=TA_CENTER)
    heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'], fontSize=12, spaceAfter=6, alignment=TA_CENTER)
    normal_style = ParagraphStyle('Normal', parent=styles['Normal'], fontSize=9, spaceAfter=4, leading=11)
    small_style = ParagraphStyle('Small', parent=styles['Normal'], fontSize=8, spaceAfter=3, leading=10)

    # Title
    story.append(Paragraph(f"<b>{scheme.scheme_name or f'Scheme {scheme.scheme_code}'}</b>", title_style))
    story.append(Paragraph(f"AMFI: {scheme.scheme_code} | AMC: {scheme.amc_name or '—'} | Category: {scheme.category or '—'}", normal_style))
    story.append(Spacer(1, 6))

    # NAV Chart PNG
    try:
        png_buffer = io.BytesIO()
        render_mf_nav_chart_png(scheme_code, png_buffer, days_back=365, indicators='rsi,macd')
        png_buffer.seek(0)
        img = Image(png_buffer, width=6.5*inch, height=3.5*inch)
        story.append(img)
        story.append(Spacer(1, 12))
    except Exception as e:
        story.append(Paragraph(f"<i>Chart unavailable: {str(e)}</i>", small_style))

    # Latest NAV & Metrics
    latest_nav = scheme.latest_nav
    if latest_nav:
        story.append(Paragraph(f"<b>Latest NAV:</b> ₹{latest_nav:.4f} ({scheme.latest_nav_date or '—'})", normal_style))
    metrics = db.query(MFNavMetricsDaily).filter_by(scheme_code=scheme_code).order_by(MFNavMetricsDaily.nav_date.desc()).first()
    if metrics:
        story.append(Paragraph(f"1W: {metrics.ret_7d:.1f}% | 1M: {metrics.ret_30d:.1f}% | 3M: {metrics.ret_90d:.1f}% | 1Y: {metrics.ret_365d:.1f}%", normal_style))
    story.append(Spacer(1, 12))

    # Risk & Expense
    story.append(Paragraph("<b>Risk & Costs</b>", heading_style))
    data = [
        ['Riskometer', scheme.risk_label or '—'],
        ['Expense Ratio', f"{scheme.expense_ratio:.2f}%" if scheme.expense_ratio else '—'],
        ['Min SIP', f"₹{scheme.min_sip:,.0f}" if scheme.min_sip else '—'],
    ]
    t = Table(data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 9),
        ('FONTSIZE', (0,1), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('BACKGROUND', (0,1), (-1,-1), colors.beige),
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))
    story.append(t)
    story.append(Spacer(1, 12))

    # Top Holdings
    if scheme.family_id:
        holdings_snap = db.query(MFFamilyHoldingsSnapshot).filter_by(family_id=scheme.family_id).order_by(MFFamilyHoldingsSnapshot.month.desc()).first()
        if holdings_snap:
            holdings = db.query(MFHolding).filter_by(snapshot_id=holdings_snap.id).order_by(MFHolding.weight_pct.desc()).limit(10).all()
            story.append(Paragraph(f"<b>Top Holdings ({holdings_snap.month})</b>", heading_style))
            hdata = [['Name', 'Type', 'Weight']]
            for h in holdings:
                hdata.append([h.name or '—', h.holding_type or '—', f"{h.weight_pct:.1f}%" if h.weight_pct else '—'])
            ht = Table(hdata, colWidths=[3*inch, 1.2*inch, 0.8*inch])
            ht.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.grey),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,0), 9),
                ('FONTSIZE', (0,1), (-1,-1), 8),
                ('GRID', (0,0), (-1,-1), 1, colors.black)
            ]))
            story.append(ht)
            story.append(Spacer(1, 12))

    # Recent Signals
    recent_signals = db.query(MFSignal).filter_by(scheme_code=scheme_code, status='pending').order_by(MFSignal.nav_date.desc()).limit(5).all()
    if recent_signals:
        story.append(Paragraph("<b>Recent Signals</b>", heading_style))
        sdata = [['Type', 'Confidence', 'NAV Date']]
        for s in recent_signals:
            sdata.append([s.signal_type or '—', f"{s.confidence_score:.0f}%", s.nav_date or '—'])
        st = Table(sdata)
        st.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.green),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 9),
            ('FONTSIZE', (0,1), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 1, colors.black)
        ]))
        story.append(st)

    # Links
    story.append(Spacer(1, 12))
    story.append(Paragraph("<b>Links</b>", heading_style))
    links_data = []
    if scheme.valueresearch_url:
        links_data.append(['ValueResearch', scheme.valueresearch_url])
    if scheme.morningstar_url:
        links_data.append(['Morningstar', scheme.morningstar_url])
    if links_data:
        lt = Table(links_data, colWidths=[1.5*inch, 5.5*inch])
        lt.setStyle(TableStyle([('ALIGN', (1,0), (1,-1), 'LEFT'), ('FONTSIZE', (0,0), (-1,-1), 8)]))
        story.append(lt)
    else:
        story.append(Paragraph("No external links configured", small_style))

    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return Response(content=buffer.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=scheme_{scheme_code}_1pager.pdf"})
