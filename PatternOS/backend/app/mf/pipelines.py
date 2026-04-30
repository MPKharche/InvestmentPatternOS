from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import and_, or_, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import (
    MFScheme,
    MFNavDaily,
    MFNavMetricsDaily,
    MFFamilyHoldingsSnapshot,
    MFHolding,
    MFSectorAlloc,
    MFRulebook,
    MFRulebookVersion,
    MFSignal,
    MFIngestionRun,
    MFIngestionCursor,
)
from app.mf.amfi import parse_navall
from app.mf.mfdata import fetch_family_holdings, fetch_family_sectors, fetch_scheme, fetch_nav_history
from app.mf.mfapi import fetch_scheme_history
from app.mf.links import ensure_scheme_links
from app.mf.rules import default_rulebook, eval_holdings_signals, eval_nav_signals
from app.mf.safety import task
from app.scanner.indicators import compute_indicators


AMFI_NAVALL_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"
settings = get_settings()

# Curated starter watchlist (popular + category representative). Idempotent.
CURATED_SCHEMES: list[int] = [
    135106,  # SBI Nifty 50 ETF
    122639,  # Parag Parikh Flexi Cap (Direct Growth)
    119550,  # ABSL Banking & PSU Debt (Direct Growth)
    120438,  # Axis Banking & PSU Debt (Direct Growth)
]

CURATED_NAME_PATTERNS: list[str] = [
    "%NIFTY 50%",
    "%NIFTY NEXT 50%",
    "%NIFTY 100%",
    "%SENSEX%",
    "%FLEXI CAP%",
    "%LARGE CAP%",
    "%MID CAP%",
    "%SMALL CAP%",
    "%BANK%",
    "%LIQUID%",
    "%GILT%",
    "%GOLD%",
]

# Initial scope (user-requested): focus ingestion/holdings on selected AMCs.
# Defaults: Direct + Growth; equity-only for most, all (Direct/Growth) for ICICI.
AMC_SCOPE_EQUITY_NAME_PATTERNS: list[str] = [
    "%Aditya Birla%",
    "%HDFC%",
    "%Nippon%",
    "%UTI%",
    "%Mirae%",
    "%Axis%",
    "%SBI%",
]
AMC_SCOPE_ALL_NAME_PATTERNS: list[str] = [
    "%ICICI%Prudential%",
]


def _get_cursor(
    db: Session,
    *,
    provider: str,
    endpoint_class: str,
    scheme_code: int | None = None,
    family_id: int | None = None,
) -> MFIngestionCursor | None:
    # IMPORTANT: Postgres UNIQUE constraints treat NULLs as distinct, so any cursor
    # key with NULL parts can be duplicated. Use 0 as a stable sentinel for each
    # missing key component and accept both (NULL) and (0) when reading.
    sc = 0 if scheme_code is None else int(scheme_code)
    fid = 0 if family_id is None else int(family_id)

    q = (
        db.query(MFIngestionCursor)
        .filter(MFIngestionCursor.provider == provider, MFIngestionCursor.endpoint_class == endpoint_class)
    )
    if sc == 0:
        q = q.filter(or_(MFIngestionCursor.scheme_code == 0, MFIngestionCursor.scheme_code.is_(None)))
    else:
        q = q.filter(MFIngestionCursor.scheme_code == sc)
    if fid == 0:
        q = q.filter(or_(MFIngestionCursor.family_id == 0, MFIngestionCursor.family_id.is_(None)))
    else:
        q = q.filter(MFIngestionCursor.family_id == fid)
    return q.order_by(MFIngestionCursor.updated_at.desc()).first()


def _set_cursor(
    db: Session,
    *,
    provider: str,
    endpoint_class: str,
    cursor_json: dict[str, Any],
    scheme_code: int | None = None,
    family_id: int | None = None,
) -> None:
    sc = 0 if scheme_code is None else int(scheme_code)
    fid = 0 if family_id is None else int(family_id)

    row = _get_cursor(db, provider=provider, endpoint_class=endpoint_class, scheme_code=sc, family_id=fid)
    if row:
        row.cursor_json = cursor_json
        db.add(row)
        db.commit()
        return
    db.add(
        MFIngestionCursor(
            provider=provider,
            endpoint_class=endpoint_class,
            scheme_code=sc,
            family_id=fid,
            cursor_json=cursor_json,
        )
    )
    db.commit()


def ensure_amc_scoped_watchlist(db: Session) -> dict[str, Any]:
    """
    Idempotently seed a monitored universe for the initial AMC scope.

    - Equity-only for ABSL/HDFC/Nippon/UTI/Mirae/Axis/SBI (Direct+Growth)
    - All (Direct+Growth) for ICICI Prudential

    This runs only when there are currently zero monitored schemes.
    """
    monitored_count = db.query(MFScheme).filter_by(monitored=True).count()
    if monitored_count > 0:
        return {"skipped": True, "reason": "monitored already configured", "updated": 0}

    if db.query(MFScheme).count() == 0:
        return {"skipped": True, "reason": "scheme master empty", "updated": 0}

    direct_growth = or_(
        and_(MFScheme.plan_type.ilike("%direct%"), MFScheme.option_type.ilike("%growth%")),
        and_(MFScheme.scheme_name.ilike("%direct%"), MFScheme.scheme_name.ilike("%growth%")),
    )

    equity_like = or_(
        MFScheme.category.ilike("%equity%"),
        MFScheme.category.ilike("%elss%"),
        MFScheme.scheme_name.ilike("%equity%"),
        MFScheme.scheme_name.ilike("%elss%"),
    )

    updated = 0

    eq_amc = or_(*[MFScheme.amc_name.ilike(p) for p in AMC_SCOPE_EQUITY_NAME_PATTERNS])
    q1 = db.query(MFScheme).filter(MFScheme.is_active.is_(True), direct_growth, eq_amc, equity_like)
    updated += int(q1.update({MFScheme.monitored: True}, synchronize_session=False) or 0)

    all_amc = or_(*[MFScheme.amc_name.ilike(p) for p in AMC_SCOPE_ALL_NAME_PATTERNS])
    q2 = db.query(MFScheme).filter(MFScheme.is_active.is_(True), direct_growth, all_amc)
    updated += int(q2.update({MFScheme.monitored: True}, synchronize_session=False) or 0)

    db.commit()
    return {"skipped": False, "updated": updated}


def _run_start(db: Session, run_type: str) -> MFIngestionRun:
    run = MFIngestionRun(run_type=run_type, status="running", started_at=datetime.utcnow())
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _run_finish(db: Session, run: MFIngestionRun, *, ok: bool, stats: dict[str, Any] | None = None, error: str | None = None) -> None:
    run.status = "success" if ok else "failed"
    run.finished_at = datetime.utcnow()
    run.stats_json = stats
    run.error_text = error
    db.add(run)
    db.commit()


def ensure_default_mf_rulebook(db: Session) -> str:
    existing = db.query(MFRulebook).filter_by(name="MF Default v1").first()
    if existing:
        # Auto-upgrade the built-in rulebook when code adds new supported signal types.
        try:
            cur_ver = (
                db.query(MFRulebookVersion)
                .filter_by(rulebook_id=existing.id, version=existing.current_version)
                .first()
            )
            cur_json = (cur_ver.rulebook_json if cur_ver else None) or {}
            cur_defs = cur_json.get("signal_definitions") or []
            cur_types = {d.get("signal_type") for d in cur_defs if isinstance(d, dict)}
            wanted_defs = default_rulebook().get("signal_definitions") or []
            wanted_types = {d.get("signal_type") for d in wanted_defs if isinstance(d, dict)}
            missing = wanted_types - cur_types
            if missing:
                next_ver = int(existing.current_version or 1) + 1
                db.add(
                    MFRulebookVersion(
                        rulebook_id=existing.id,
                        version=next_ver,
                        rulebook_json=default_rulebook(),
                        change_summary=f"Auto-upgrade: add {', '.join(sorted([str(x) for x in missing]))}",
                    )
                )
                existing.current_version = next_ver
                db.add(existing)
                db.commit()
        except Exception:
            db.rollback()
        return str(existing.id)
    rb = MFRulebook(name="MF Default v1", status="active", current_version=1)
    db.add(rb)
    db.flush()
    ver = MFRulebookVersion(
        rulebook_id=rb.id,
        version=1,
        rulebook_json=default_rulebook(),
        change_summary="Seed: MF default v1",
    )
    db.add(ver)
    db.commit()
    return str(rb.id)


def ensure_curated_watchlist(db: Session) -> dict[str, Any]:
    monitored_count = db.query(MFScheme).filter_by(monitored=True).count()
    created = 0
    updated = 0
    if monitored_count > 0:
        return {"skipped": True, "reason": "watchlist already configured", "created": 0, "updated": 0}

    total_schemes = db.query(MFScheme).count()

    # Prefer AMC-scoped universe for the initial rollout (fast, no outbound calls).
    if total_schemes > 0:
        scope_stats = ensure_amc_scoped_watchlist(db)
        if not scope_stats.get("skipped") and int(scope_stats.get("updated") or 0) > 0:
            return {"skipped": False, "created": 0, "updated": int(scope_stats["updated"]), "scope": "amc"}

    target = 30

    # If scheme master exists (e.g., after first AMFI ingestion), prefer selecting by name patterns (no rate limits).
    if total_schemes > 0:
        codes: set[int] = set()
        for code in CURATED_SCHEMES:
            if db.query(MFScheme.scheme_code).filter_by(scheme_code=code).first():
                codes.add(code)
        for pat in CURATED_NAME_PATTERNS:
            if len(codes) >= target:
                break
            rows = (
                db.query(MFScheme.scheme_code)
                .filter(MFScheme.scheme_name.ilike(pat))
                .order_by(MFScheme.scheme_code.asc())
                .limit(max(0, target - len(codes)))
                .all()
            )
            for r in rows:
                codes.add(int(r[0]))
                if len(codes) >= target:
                    break

        if codes:
            res = (
                db.query(MFScheme)
                .filter(MFScheme.scheme_code.in_(sorted(codes)))
                .update({MFScheme.monitored: True}, synchronize_session=False)
            )
            updated += int(res or 0)
            db.commit()
            return {"skipped": False, "created": created, "updated": updated, "target": target, "selected": len(codes)}

    # Fallback: if DB is empty, create a minimal curated list using mfdata.in scheme endpoint.
    for code in CURATED_SCHEMES:
        s = db.query(MFScheme).filter_by(scheme_code=code).first()
        if not s:
            with task(db, run_id=None, provider="mfdata", endpoint_class="scheme", scheme_code=code) as t:
                ext = fetch_scheme(code, task=t)
            if ext:
                s = MFScheme(
                    scheme_code=code,
                    scheme_name=ext.name,
                    family_id=ext.family_id,
                    family_name=ext.family_name,
                    amc_name=ext.amc_name,
                    amc_slug=ext.amc_slug,
                    category=ext.category,
                    plan_type=ext.plan_type,
                    option_type=ext.option_type,
                    risk_label=ext.risk_label,
                    expense_ratio=ext.expense_ratio,
                    aum=ext.aum,
                    min_sip=ext.min_sip,
                    min_lumpsum=ext.min_lumpsum,
                    exit_load=ext.exit_load,
                    benchmark=ext.benchmark,
                    latest_nav=ext.nav,
                    latest_nav_date=(datetime.fromisoformat(ext.nav_date).date() if ext.nav_date else None),
                    monitored=True,
                )
                db.add(s)
                created += 1
            else:
                s = MFScheme(scheme_code=code, scheme_name=f"Scheme {code}", monitored=True)
                db.add(s)
                created += 1
        else:
            s.monitored = True
            updated += 1
        db.commit()

    return {"skipped": False, "created": created, "updated": updated, "target": target}


def enrich_monitored_schemes_mfdata(db: Session, *, max_per_run: int = 200) -> dict[str, Any]:
    """
    Enrich monitored scheme master data using mfdata.in, with a 24h cache per scheme.

    Pulls:
    - risk_label, expense_ratio, AUM, benchmark, launch_date
    - morningstar_sec_id
    - returns + ratios JSON blobs (for UI tiles)
    """
    if not settings.MF_INGESTION_ENABLED:
        return {"skipped": True, "reason": "MF_INGESTION_ENABLED=false"}

    now = datetime.utcnow()
    cutoff = now - timedelta(hours=24)
    q = (
        db.query(MFScheme)
        .filter(MFScheme.monitored.is_(True))
        .filter(or_(MFScheme.mfdata_fetched_at.is_(None), MFScheme.mfdata_fetched_at < cutoff))
        .order_by(MFScheme.mfdata_fetched_at.asc().nullsfirst(), MFScheme.scheme_code.asc())
        .limit(max(1, min(int(max_per_run), 2000)))
    )
    rows = q.all()
    updated = 0
    failed = 0

    for s in rows:
        with task(db, run_id=None, provider="mfdata", endpoint_class="scheme", scheme_code=s.scheme_code) as t:
            ext = fetch_scheme(int(s.scheme_code), task=t)
        if not ext:
            failed += 1
            continue

        changed = False
        s.scheme_name = ext.name or s.scheme_name
        s.family_id = ext.family_id or s.family_id
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
        if ext.launch_date and not s.launch_date:
            try:
                s.launch_date = datetime.fromisoformat(ext.launch_date).date()
            except Exception:
                pass
        if ext.morningstar_sec_id and not s.morningstar_sec_id:
            s.morningstar_sec_id = ext.morningstar_sec_id
        if ext.returns is not None:
            s.returns_json = ext.returns
        if ext.ratios is not None:
            s.ratios_json = ext.ratios

        s.mfdata_fetched_at = now
        if ensure_scheme_links(s):
            changed = True
        db.add(s)
        db.commit()
        updated += 1

    return {"schemes_considered": len(rows), "updated": updated, "failed": failed}


def _chunk(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def ingest_amfi_navall(db: Session) -> dict[str, Any]:
    run = _run_start(db, "daily_nav")
    try:
        if not settings.MF_INGESTION_ENABLED:
            stats = {"skipped": True, "reason": "MF_INGESTION_ENABLED=false"}
            _run_finish(db, run, ok=True, stats=stats)
            return stats

        ensure_default_mf_rulebook(db)

        with task(db, run_id=str(run.id), provider="amfi", endpoint_class="navall") as t:
            res = t.request(method="GET", url=AMFI_NAVALL_URL, bucket="nav")
            txt = res.text or ""
        rows = parse_navall(txt.splitlines())

        # Upsert schemes (minimal fields) + latest NAV pointers.
        scheme_params: list[dict[str, Any]] = []
        nav_params: list[dict[str, Any]] = []
        for r in rows:
            scheme_params.append(
                {
                    "scheme_code": r.scheme_code,
                    "isin_growth": r.isin_growth,
                    "isin_reinvest": r.isin_reinvest,
                    "scheme_name": r.scheme_name,
                    "latest_nav": r.nav,
                    "latest_nav_date": r.nav_date,
                }
            )
            nav_params.append(
                {
                    "scheme_code": r.scheme_code,
                    "nav_date": r.nav_date,
                    "nav": r.nav,
                    "source": "amfi",
                }
            )

        upsert_scheme_sql = text(
            """
            INSERT INTO mf_schemes (scheme_code, isin_growth, isin_reinvest, scheme_name, latest_nav, latest_nav_date, updated_at)
            VALUES (:scheme_code, :isin_growth, :isin_reinvest, :scheme_name, :latest_nav, :latest_nav_date, NOW())
            ON CONFLICT (scheme_code) DO UPDATE SET
              isin_growth = COALESCE(EXCLUDED.isin_growth, mf_schemes.isin_growth),
              isin_reinvest = COALESCE(EXCLUDED.isin_reinvest, mf_schemes.isin_reinvest),
              scheme_name = COALESCE(EXCLUDED.scheme_name, mf_schemes.scheme_name),
              latest_nav = EXCLUDED.latest_nav,
              latest_nav_date = EXCLUDED.latest_nav_date,
              updated_at = NOW()
            """
        )
        upsert_nav_sql = text(
            """
            INSERT INTO mf_nav_daily (scheme_code, nav_date, nav, source, ingested_at)
            VALUES (:scheme_code, :nav_date, :nav, :source, NOW())
            ON CONFLICT (scheme_code, nav_date) DO UPDATE SET
              nav = EXCLUDED.nav,
              source = EXCLUDED.source,
              ingested_at = NOW()
            """
        )

        for ch in _chunk(scheme_params, 1000):
            db.execute(upsert_scheme_sql, ch)
        for ch in _chunk(nav_params, 2000):
            db.execute(upsert_nav_sql, ch)
        db.commit()

        # If watchlist isn't configured yet, seed a curated list from the freshly-upserted scheme master.
        ensure_curated_watchlist(db)

        # Opportunistic enrichment for monitored schemes (cached 24h; safe/rate-limited).
        enrich_stats = enrich_monitored_schemes_mfdata(db, max_per_run=200)

        # Compute metrics + signals only for monitored schemes on the latest date present.
        latest_date: date | None = None
        if rows:
            latest_date = max(r.nav_date for r in rows)
        metrics_count = 0
        signals_count = 0
        if latest_date:
            monitored = db.query(MFScheme).filter_by(monitored=True).all()
            peer_cache: dict[str, float | None] = {}
            for s in monitored:
                m = compute_nav_metrics(db, s.scheme_code, latest_date)
                if m:
                    # Peer-relative signals (best effort): requires category populated (e.g., from seed CSV).
                    if s.category:
                        key = f"{s.category}::{latest_date.isoformat()}"
                        if key not in peer_cache:
                            peer_cache[key] = compute_category_median_ret_90d(db, s.category, latest_date)
                        if peer_cache[key] is not None:
                            m["peer_category"] = s.category
                            m["peer_ret_90d_median"] = peer_cache[key]

                    metrics_count += 1
                    signals_count += generate_nav_signals(db, s, latest_date, m)

        stats = {
            "rows_parsed": len(rows),
            "latest_date": str(latest_date) if latest_date else None,
            "metrics": metrics_count,
            "signals": signals_count,
            "enrich": enrich_stats,
        }
        _run_finish(db, run, ok=True, stats=stats)
        return stats
    except Exception as e:
        db.rollback()
        _run_finish(db, run, ok=False, error=str(e))
        raise


def backfill_nav_history_mfapi(
    db: Session,
    *,
    start_date: date = date(2000, 1, 1),
    max_schemes: int | None = None,
) -> dict[str, Any]:
    """
    Safe historical backfill using MFAPI (windowed, resumable).

    - Strictly scoped to monitored schemes (avoid heavy crawling).
    - Idempotent inserts via PK (scheme_code, nav_date) + ON CONFLICT DO NOTHING.
    - Resumable using mf_ingestion_cursors (no "storm" on restart).

    Notes:
    - MFAPI may ignore window params; we always filter dates on our side.
    """
    run = _run_start(db, "backfill_nav_mfapi")
    try:
        if not settings.MF_INGESTION_ENABLED or not settings.MF_BACKFILL_ENABLED:
            stats = {"skipped": True, "reason": "MF_BACKFILL_ENABLED=false or MF_INGESTION_ENABLED=false"}
            _run_finish(db, run, ok=True, stats=stats)
            return stats

        ensure_curated_watchlist(db)

        scheme_codes = [int(r[0]) for r in db.query(MFScheme.scheme_code).filter_by(monitored=True).order_by(MFScheme.scheme_code.asc()).all()]
        if max_schemes is not None:
            scheme_codes = scheme_codes[: max(0, int(max_schemes))]

        global_cur = _get_cursor(db, provider="mfapi", endpoint_class="nav_history_global")
        global_json = dict(global_cur.cursor_json) if global_cur else {}
        if global_json.get("start_date") != start_date.isoformat():
            global_json = {"next_index": 0, "start_date": start_date.isoformat()}

        next_index = int(global_json.get("next_index") or 0)
        created_rows = 0
        processed_schemes = 0
        processed_windows = 0
        skipped_retry_after = 0

        max_windows_per_scheme_per_run = 5

        for idx in range(next_index, len(scheme_codes)):
            code = scheme_codes[idx]

            # Determine the earliest NAV we already have; we backfill strictly before that date.
            earliest = (
                db.query(MFNavDaily.nav_date)
                .filter(MFNavDaily.scheme_code == code)
                .order_by(MFNavDaily.nav_date.asc())
                .first()
            )
            stop_before = earliest[0] if earliest else date(2100, 1, 1)

            scheme_cur = _get_cursor(db, provider="mfapi", endpoint_class="nav_history_scheme", scheme_code=code)
            scheme_json = dict(scheme_cur.cursor_json) if scheme_cur else {}

            # Reset scheme cursor if configuration changed.
            if scheme_json.get("start_date") != start_date.isoformat() or scheme_json.get("stop_before") != stop_before.isoformat():
                scheme_json = {
                    "start_date": start_date.isoformat(),
                    "stop_before": stop_before.isoformat(),
                    "next_window_start": start_date.isoformat(),
                }

            retry_after = scheme_json.get("retry_after")
            if retry_after:
                try:
                    ra = datetime.fromisoformat(str(retry_after))
                    if ra > datetime.utcnow():
                        skipped_retry_after += 1
                        _set_cursor(db, provider="mfapi", endpoint_class="nav_history_global", cursor_json={"next_index": idx + 1, "start_date": start_date.isoformat()})
                        continue
                except Exception:
                    pass

            next_start = start_date
            try:
                next_start = datetime.fromisoformat(str(scheme_json.get("next_window_start") or start_date.isoformat())).date()
            except Exception:
                next_start = start_date

            if next_start >= stop_before:
                processed_schemes += 1
                _set_cursor(db, provider="mfapi", endpoint_class="nav_history_global", cursor_json={"next_index": idx + 1, "start_date": start_date.isoformat()})
                continue

            windows_done = 0
            while windows_done < max_windows_per_scheme_per_run and next_start < stop_before:
                # Window: 1 calendar year chunks.
                window_end = date(next_start.year, 12, 31)
                if window_end >= stop_before:
                    window_end = stop_before - timedelta(days=1)
                if window_end < next_start:
                    break

                try:
                    with task(db, run_id=str(run.id), provider="mfapi", endpoint_class="nav_history", scheme_code=code) as t:
                        hist = fetch_scheme_history(
                            scheme_code=code,
                            task=t,
                            start_date=next_start.isoformat(),
                            end_date=window_end.isoformat(),
                        )
                except Exception as e:
                    # Persist a per-scheme retry-after to avoid repeated immediate failures.
                    scheme_json["retry_after"] = (datetime.utcnow() + timedelta(minutes=30)).isoformat()
                    scheme_json["last_error"] = str(e)[:500]
                    _set_cursor(db, provider="mfapi", endpoint_class="nav_history_scheme", scheme_code=code, cursor_json=scheme_json)
                    break

                if hist and hist.nav_points:
                    pts: list[dict[str, Any]] = []
                    for d_str, nav in hist.nav_points:
                        try:
                            d = datetime.fromisoformat(d_str).date()
                        except Exception:
                            continue
                        if d < next_start or d > window_end:
                            continue
                        if d < start_date or d >= stop_before:
                            continue
                        pts.append({"scheme_code": code, "nav_date": d, "nav": float(nav), "source": "mfapi"})

                    if pts:
                        ins = text(
                            """
                            INSERT INTO mf_nav_daily (scheme_code, nav_date, nav, source, ingested_at)
                            VALUES (:scheme_code, :nav_date, :nav, :source, NOW())
                            ON CONFLICT (scheme_code, nav_date) DO NOTHING
                            """
                        )
                        for ch in _chunk(pts, 5000):
                            res = db.execute(ins, ch)
                            created_rows += int(res.rowcount or 0)
                        db.commit()

                    # Light enrichment for missing master fields (no scraping).
                    s = db.query(MFScheme).filter_by(scheme_code=code).first()
                    if s:
                        changed = False
                        if hist.scheme_name and not s.scheme_name:
                            s.scheme_name = hist.scheme_name
                            changed = True
                        if hist.fund_house and not s.amc_name:
                            s.amc_name = hist.fund_house
                            changed = True
                        if hist.scheme_category and not s.category:
                            s.category = hist.scheme_category
                            changed = True
                        if ensure_scheme_links(s):
                            changed = True
                        if changed:
                            db.add(s)
                            db.commit()

                processed_windows += 1
                windows_done += 1

                next_start = window_end + timedelta(days=1)
                scheme_json["next_window_start"] = next_start.isoformat()
                scheme_json["retry_after"] = None
                _set_cursor(db, provider="mfapi", endpoint_class="nav_history_scheme", scheme_code=code, cursor_json=scheme_json)

            processed_schemes += 1
            _set_cursor(db, provider="mfapi", endpoint_class="nav_history_global", cursor_json={"next_index": idx + 1, "start_date": start_date.isoformat()})

        stats = {
            "schemes": len(scheme_codes),
            "processed_schemes": processed_schemes,
            "processed_windows": processed_windows,
            "rows_inserted": created_rows,
            "start_date": start_date.isoformat(),
            "skipped_retry_after": skipped_retry_after,
        }
        _run_finish(db, run, ok=True, stats=stats)
        return stats
    except Exception as e:
        db.rollback()
        _run_finish(db, run, ok=False, error=str(e))
        raise


def gap_fill_nav_history_mfdata(db: Session, *, period: str = "max", max_schemes: int = 100) -> dict[str, Any]:
    """
    Fill missing NAV history points using mfdata.in /nav/history?period=max (approx last ~18y).

    - Scoped to monitored schemes.
    - Idempotent inserts with ON CONFLICT DO NOTHING (do not overwrite AMFI/seed values).
    - Resumable via mf_ingestion_cursors (per scheme).
    """
    run = _run_start(db, "gapfill_nav_mfdata")
    try:
        if not settings.MF_INGESTION_ENABLED:
            stats = {"skipped": True, "reason": "MF_INGESTION_ENABLED=false"}
            _run_finish(db, run, ok=True, stats=stats)
            return stats

        ensure_curated_watchlist(db)

        schemes = (
            db.query(MFScheme)
            .filter(MFScheme.monitored.is_(True))
            .order_by(MFScheme.scheme_code.asc())
            .limit(max(1, min(int(max_schemes), 2000)))
            .all()
        )

        inserted = 0
        processed = 0
        skipped_cached = 0

        cutoff = datetime.utcnow() - timedelta(hours=24)

        for s in schemes:
            cur = _get_cursor(db, provider="mfdata", endpoint_class="nav_history_max", scheme_code=int(s.scheme_code))
            if cur and isinstance(cur.cursor_json, dict) and cur.cursor_json.get("fetched_at"):
                try:
                    fetched_at = datetime.fromisoformat(str(cur.cursor_json["fetched_at"]))
                    if fetched_at > cutoff:
                        skipped_cached += 1
                        continue
                except Exception:
                    pass

            with task(db, run_id=str(run.id), provider="mfdata", endpoint_class="nav_history", scheme_code=int(s.scheme_code)) as t:
                pts = fetch_nav_history(int(s.scheme_code), period=period, task=t)

            params: list[dict[str, Any]] = []
            for it in pts:
                try:
                    d = datetime.fromisoformat(str(it["date"])).date()
                    nav = float(it["nav"])
                except Exception:
                    continue
                params.append({"scheme_code": int(s.scheme_code), "nav_date": d, "nav": nav, "source": "mfdata"})

            if params:
                ins = text(
                    """
                    INSERT INTO mf_nav_daily (scheme_code, nav_date, nav, source, ingested_at)
                    VALUES (:scheme_code, :nav_date, :nav, :source, NOW())
                    ON CONFLICT (scheme_code, nav_date) DO NOTHING
                    """
                )
                for ch in _chunk(params, 5000):
                    res = db.execute(ins, ch)
                    inserted += int(res.rowcount or 0)
                db.commit()

            _set_cursor(
                db,
                provider="mfdata",
                endpoint_class="nav_history_max",
                scheme_code=int(s.scheme_code),
                cursor_json={"fetched_at": datetime.utcnow().isoformat(), "period": period, "points": len(params)},
            )
            processed += 1

        stats = {"processed": processed, "inserted": inserted, "skipped_cached": skipped_cached, "period": period}
        _run_finish(db, run, ok=True, stats=stats)
        return stats
    except Exception as e:
        db.rollback()
        _run_finish(db, run, ok=False, error=str(e))
        raise


def check_external_links(db: Session, *, limit: int | None = None) -> dict[str, Any]:
    """
    Optional, low-frequency connectivity check for external links.

    This is intentionally conservative and disabled by default via
    MF_LINK_CHECK_ENABLED to avoid accidental blocks from third-party sites.

    Notes:
    - No scraping. We only do a minimal GET with a small byte-range hint.
    - Many sites may return 403 to non-browser clients; we record status but do
      not treat it as a data-ingestion failure.
    """
    run = _run_start(db, "link_check")
    try:
        if not settings.MF_INGESTION_ENABLED or not settings.MF_LINK_CHECK_ENABLED:
            stats = {"skipped": True, "reason": "MF_LINK_CHECK_ENABLED=false or MF_INGESTION_ENABLED=false"}
            _run_finish(db, run, ok=True, stats=stats)
            return stats

        ensure_curated_watchlist(db)

        cap = int(limit or settings.MF_LINK_CHECK_DAILY_CAP)
        cap = max(1, min(cap, 2000))

        q = db.query(MFScheme).filter(MFScheme.monitored.is_(True))
        q = q.order_by(MFScheme.updated_at.desc().nullslast())
        schemes = q.limit(cap).all()

        checked = 0
        for s in schemes:
            ensure_scheme_links(s)
            urls = []
            if s.valueresearch_url:
                urls.append(("valueresearch", s.valueresearch_url))
            if s.morningstar_url:
                urls.append(("morningstar", s.morningstar_url))
            if not urls:
                continue

            statuses: list[int] = []
            for provider, url in urls:
                with task(db, run_id=str(run.id), provider=provider, endpoint_class="link_check", scheme_code=s.scheme_code) as t:
                    res = t.request(
                        method="GET",
                        url=url,
                        bucket="standard",
                        headers={
                            "Accept": "text/html,application/xhtml+xml",
                            "Range": "bytes=0-2048",
                        },
                        max_retries=1,
                    )
                    if res.status_code is not None:
                        statuses.append(int(res.status_code))

            s.links_last_checked_at = datetime.utcnow()
            s.links_last_check_status = max(statuses) if statuses else None
            db.add(s)
            db.commit()
            checked += 1

        stats = {"checked": checked, "limit": cap}
        _run_finish(db, run, ok=True, stats=stats)
        return stats
    except Exception as e:
        db.rollback()
        _run_finish(db, run, ok=False, error=str(e))
        raise


def _nav_at_or_before(db: Session, scheme_code: int, target: date) -> float | None:
    row = (
        db.query(MFNavDaily.nav)
        .filter(MFNavDaily.scheme_code == scheme_code, MFNavDaily.nav_date <= target)
        .order_by(MFNavDaily.nav_date.desc())
        .first()
    )
    return float(row[0]) if row else None


def compute_nav_metrics(db: Session, scheme_code: int, nav_date: date) -> dict[str, Any] | None:
    nav_today = _nav_at_or_before(db, scheme_code, nav_date)
    if nav_today is None:
        return None

    prev_nav = (
        db.query(MFNavDaily.nav, MFNavDaily.nav_date)
        .filter(MFNavDaily.scheme_code == scheme_code, MFNavDaily.nav_date < nav_date)
        .order_by(MFNavDaily.nav_date.desc())
        .first()
    )
    day_change = None
    day_change_pct = None
    if prev_nav:
        p = float(prev_nav[0])
        day_change = float(nav_today - p)
        day_change_pct = float((day_change / p) * 100) if p else None

    def ret(days: int) -> float | None:
        base = _nav_at_or_before(db, scheme_code, nav_date - timedelta(days=days))
        if base is None or base == 0:
            return None
        return float(((nav_today - base) / base) * 100)

    ret_7d = ret(7)
    ret_30d = ret(30)
    ret_90d = ret(90)
    ret_365d = ret(365)

    # 52w high: max nav in last 365 calendar days
    window_start = nav_date - timedelta(days=365)
    max_row = (
        db.query(text("MAX(nav)"))
        .select_from(MFNavDaily)
        .filter(MFNavDaily.scheme_code == scheme_code, MFNavDaily.nav_date >= window_start, MFNavDaily.nav_date <= nav_date)
        .first()
    )
    rolling_high = float(max_row[0]) if max_row and max_row[0] is not None else None
    is_52w = bool(rolling_high is not None and abs(nav_today - rolling_high) < 1e-9)

    upsert = text(
        """
        INSERT INTO mf_nav_metrics_daily (
          scheme_code, nav_date, day_change, day_change_pct,
          ret_7d, ret_30d, ret_90d, ret_365d,
          rolling_52w_high_nav, is_52w_high, updated_at
        )
        VALUES (
          :scheme_code, :nav_date, :day_change, :day_change_pct,
          :ret_7d, :ret_30d, :ret_90d, :ret_365d,
          :rolling_52w_high_nav, :is_52w_high, NOW()
        )
        ON CONFLICT (scheme_code, nav_date) DO UPDATE SET
          day_change = EXCLUDED.day_change,
          day_change_pct = EXCLUDED.day_change_pct,
          ret_7d = EXCLUDED.ret_7d,
          ret_30d = EXCLUDED.ret_30d,
          ret_90d = EXCLUDED.ret_90d,
          ret_365d = EXCLUDED.ret_365d,
          rolling_52w_high_nav = EXCLUDED.rolling_52w_high_nav,
          is_52w_high = EXCLUDED.is_52w_high,
          updated_at = NOW()
        """
    )
    db.execute(
        upsert,
        {
            "scheme_code": scheme_code,
            "nav_date": nav_date,
            "day_change": day_change,
            "day_change_pct": day_change_pct,
            "ret_7d": ret_7d,
            "ret_30d": ret_30d,
            "ret_90d": ret_90d,
            "ret_365d": ret_365d,
            "rolling_52w_high_nav": rolling_high,
            "is_52w_high": is_52w,
        },
    )
    db.commit()

    return {
        "scheme_code": scheme_code,
        "nav_date": str(nav_date),
        "nav": nav_today,
        "day_change": day_change,
        "day_change_pct": day_change_pct,
        "ret_7d": ret_7d,
        "ret_30d": ret_30d,
        "ret_90d": ret_90d,
        "ret_365d": ret_365d,
        "rolling_52w_high_nav": rolling_high,
        "is_52w_high": is_52w,
    }


def compute_category_median_ret_90d(db: Session, category: str, nav_date: date) -> float | None:
    """
    Median 90d return for a category on a given nav_date, computed from mf_nav_daily.

    Notes:
    - Best-effort: requires historical NAV to exist (seed recommended).
    - Uses NAV at-or-before nav_date and (nav_date - 90d) per scheme.
    """
    base_date = nav_date - timedelta(days=90)
    q = text(
        """
        SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY ((t.nav - b.nav) / NULLIF(b.nav, 0)) * 100.0) AS median_ret_90d
        FROM mf_schemes s
        JOIN LATERAL (
          SELECT nav
          FROM mf_nav_daily n
          WHERE n.scheme_code = s.scheme_code AND n.nav_date <= :nav_date
          ORDER BY n.nav_date DESC
          LIMIT 1
        ) t ON TRUE
        JOIN LATERAL (
          SELECT nav
          FROM mf_nav_daily n
          WHERE n.scheme_code = s.scheme_code AND n.nav_date <= :base_date
          ORDER BY n.nav_date DESC
          LIMIT 1
        ) b ON TRUE
        WHERE s.category = :category
        """
    )
    row = db.execute(q, {"nav_date": nav_date, "base_date": base_date, "category": category}).first()
    if not row or row[0] is None:
        return None
    return float(row[0])


def _active_rulebook(db: Session) -> dict[str, Any]:
    rb = db.query(MFRulebook).filter_by(status="active").order_by(MFRulebook.updated_at.desc()).first()
    if not rb:
        ensure_default_mf_rulebook(db)
        rb = db.query(MFRulebook).filter_by(status="active").order_by(MFRulebook.updated_at.desc()).first()
    if not rb:
        return default_rulebook()
    ver = (
        db.query(MFRulebookVersion)
        .filter_by(rulebook_id=rb.id, version=rb.current_version)
        .first()
    )
    return (ver.rulebook_json if ver else default_rulebook()) or default_rulebook()


def generate_nav_signals(db: Session, scheme: MFScheme, nav_date: date, metrics: dict[str, Any]) -> int:
    rulebook = _active_rulebook(db)
    # Enrich NAV metrics with a lightweight indicator snapshot so rulebooks can trigger
    # RSI/MACD/EMA signals without requiring extra tables/migrations.
    try:
        ind = _nav_indicator_snapshot(db, scheme.scheme_code, nav_date)
        if ind:
            metrics = {**(metrics or {}), **ind}
    except Exception:
        pass
    cands = eval_nav_signals(
        scheme_code=scheme.scheme_code,
        family_id=scheme.family_id,
        nav_date=nav_date,
        metrics=metrics,
        rulebook=rulebook,
    )
    created = 0
    for c in cands:
        ins = text(
            """
            INSERT INTO mf_signals (
              scheme_code, family_id, signal_type, nav_date, triggered_at,
              base_score, confidence_score, context_json, status
            )
            VALUES (
              :scheme_code, :family_id, :signal_type, :nav_date, NOW(),
              :base_score, :confidence_score, :context_json, 'pending'
            )
            ON CONFLICT (scheme_code, signal_type, nav_date) DO NOTHING
            """
        )
        res = db.execute(
            ins,
            {
                "scheme_code": c.scheme_code,
                "family_id": c.family_id,
                "signal_type": c.signal_type,
                "nav_date": c.nav_date,
                "base_score": c.base_score,
                "confidence_score": c.confidence_score,
                "context_json": json.dumps(c.context),
            },
        )
        created += int(res.rowcount or 0)
    db.commit()
    if created > 0:
        from app.integrations.events import emit_patternos_event_sync

        emit_patternos_event_sync(
            "mf_signals_created",
            {
                "scheme_code": scheme.scheme_code,
                "scheme_name": (scheme.scheme_name or "")[:200],
                "nav_date": nav_date.isoformat(),
                "created": created,
            },
        )
    return created


def _nav_indicator_snapshot(db: Session, scheme_code: int, nav_date: date) -> dict[str, Any] | None:
    """
    Compute latest indicator snapshot for a MF NAV series around `nav_date`.
    Returns:
      { rsi, macd, macd_signal, macd_hist, macd_cross?, ema_fast, ema_slow, ema_cross? }
    """
    rows = (
        db.query(MFNavDaily)
        .filter(MFNavDaily.scheme_code == scheme_code, MFNavDaily.nav_date <= nav_date)
        .order_by(MFNavDaily.nav_date.desc())
        .limit(220)
        .all()
    )
    if not rows or len(rows) < 40:
        return None
    rows = list(reversed(rows))
    import pandas as pd

    closes = [float(r.nav) for r in rows]
    dates = [r.nav_date for r in rows]
    opens = [closes[0]] + closes[:-1]
    highs = [max(o, c) for o, c in zip(opens, closes)]
    lows = [min(o, c) for o, c in zip(opens, closes)]
    df = pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": [0] * len(closes)},
        index=pd.to_datetime(dates),
    )
    idf = compute_indicators(df)
    last = idf.iloc[-1]
    prev = idf.iloc[-2] if len(idf) >= 2 else None

    out: dict[str, Any] = {
        "rsi": (float(last.get("rsi")) if last.get("rsi") is not None else None),
        "macd": (float(last.get("macd")) if last.get("macd") is not None else None),
        "macd_signal": (float(last.get("macd_signal")) if last.get("macd_signal") is not None else None),
        "macd_hist": (float(last.get("macd_hist")) if last.get("macd_hist") is not None else None),
        "ema_fast": (float(last.get("ema_20")) if last.get("ema_20") is not None else None),
        "ema_slow": (float(last.get("ema_50")) if last.get("ema_50") is not None else None),
    }

    # Cross detection (hist crossing zero).
    if prev is not None and last.get("macd_hist") is not None and prev.get("macd_hist") is not None:
        try:
            if float(prev.get("macd_hist")) <= 0 and float(last.get("macd_hist")) > 0:
                out["macd_cross"] = "bullish"
            elif float(prev.get("macd_hist")) >= 0 and float(last.get("macd_hist")) < 0:
                out["macd_cross"] = "bearish"
        except Exception:
            pass

    # EMA(20/50) cross detection.
    if prev is not None and last.get("ema_20") is not None and last.get("ema_50") is not None and prev.get("ema_20") is not None and prev.get("ema_50") is not None:
        try:
            if float(prev.get("ema_20")) <= float(prev.get("ema_50")) and float(last.get("ema_20")) > float(last.get("ema_50")):
                out["ema_cross"] = "bullish"
            elif float(prev.get("ema_20")) >= float(prev.get("ema_50")) and float(last.get("ema_20")) < float(last.get("ema_50")):
                out["ema_cross"] = "bearish"
        except Exception:
            pass

    return out


def ingest_monthly_holdings(db: Session, *, month: date | None = None, rate_limit_s: float = 1.0) -> dict[str, Any]:
    run = _run_start(db, "monthly_holdings")
    try:
        if not settings.MF_INGESTION_ENABLED or not settings.MF_HOLDINGS_ENABLED:
            stats = {"skipped": True, "reason": "MF_HOLDINGS_ENABLED=false or MF_INGESTION_ENABLED=false"}
            _run_finish(db, run, ok=True, stats=stats)
            return stats

        ensure_default_mf_rulebook(db)
        ensure_curated_watchlist(db)

        # First day of current month by default.
        today = datetime.now().date()
        m = month or date(today.year, today.month, 1)

        monitored = db.query(MFScheme).filter_by(monitored=True).all()
        family_ids = sorted({s.family_id for s in monitored if s.family_id is not None})

        snaps = 0
        holdings_rows = 0
        signals = 0

        # Previous month (first day)
        prev_last = m - timedelta(days=1)
        prev_m = date(prev_last.year, prev_last.month, 1)

        family_summaries: dict[int, dict[str, Any]] = {}

        cur = _get_cursor(db, provider="mfdata", endpoint_class="monthly_holdings")
        cur_json = dict(cur.cursor_json) if cur else {}
        if cur_json.get("month") != m.isoformat():
            cur_json = {"month": m.isoformat(), "next_index": 0}
        start_idx = int(cur_json.get("next_index") or 0)

        for i in range(start_idx, len(family_ids)):
            fid = family_ids[i]
            with task(db, run_id=str(run.id), provider="mfdata", endpoint_class="holdings", family_id=fid) as t:
                data = fetch_family_holdings(fid, task=t)
            if not data:
                _set_cursor(db, provider="mfdata", endpoint_class="monthly_holdings", cursor_json={"month": m.isoformat(), "next_index": i + 1})
                continue

            snap = MFFamilyHoldingsSnapshot(
                family_id=fid,
                month=m,
                total_aum=(float(data.get("total_aum")) if data.get("total_aum") is not None else None),
                equity_pct=(float(data.get("equity_pct")) if data.get("equity_pct") is not None else None),
                debt_pct=(float(data.get("debt_pct")) if data.get("debt_pct") is not None else None),
                other_pct=(float(data.get("other_pct")) if data.get("other_pct") is not None else None),
                fetched_at=(datetime.fromisoformat(data["fetched_at"]) if data.get("fetched_at") else None),
                raw_json=data,
            )
            # Upsert snapshot
            db.merge(snap)
            db.commit()
            snaps += 1

            # Clear existing parsed rows for this family+month (idempotent refresh).
            db.query(MFHolding).filter_by(family_id=fid, month=m).delete()
            db.query(MFSectorAlloc).filter_by(family_id=fid, month=m).delete()
            db.commit()

            def add_list(items: list[dict[str, Any]], holding_type: str):
                nonlocal holdings_rows
                seen: set[str] = set()
                for it in items:
                    name = str(it.get("name") or "").strip()
                    if not name:
                        continue
                    # Some snapshots include duplicate entries; keep the first occurrence.
                    if name in seen:
                        continue
                    seen.add(name)
                    h = MFHolding(
                        family_id=fid,
                        month=m,
                        holding_type=holding_type,
                        name=name,
                        weight_pct=(float(it["weight_pct"]) if it.get("weight_pct") is not None else None),
                        market_value=(float(it["market_value"]) if it.get("market_value") is not None else None),
                        quantity=(float(it["quantity"]) if it.get("quantity") is not None else None),
                        month_change_qty=(float(it["month_change_qty"]) if it.get("month_change_qty") is not None else None),
                        month_change_pct=(float(it["month_change_pct"]) if it.get("month_change_pct") is not None else None),
                        credit_rating=it.get("credit_rating"),
                        maturity_date=(datetime.fromisoformat(it["maturity_date"]).date() if it.get("maturity_date") else None),
                        isin=it.get("isin"),
                        ticker=(it.get("ticker") or it.get("holding_type")),
                        sector=it.get("sector"),
                    )
                    db.add(h)
                    holdings_rows += 1

            add_list(data.get("equity_holdings") or [], "equity")
            add_list(data.get("debt_holdings") or [], "debt")
            add_list(data.get("other_holdings") or [], "other")
            db.commit()

            with task(db, run_id=str(run.id), provider="mfdata", endpoint_class="sectors", family_id=fid) as t2:
                sectors = fetch_family_sectors(fid, task=t2) or []
            for it in sectors:
                if not isinstance(it, dict):
                    continue
                sec = str(it.get("sector") or it.get("name") or "")
                w = it.get("weight_pct")
                if not sec or w is None:
                    continue
                db.add(MFSectorAlloc(family_id=fid, month=m, sector=sec, weight_pct=float(w)))
            db.commit()

            # Build per-family summary (used for per-scheme signals later).
            eq = db.query(MFHolding).filter_by(family_id=fid, month=m, holding_type="equity").all()
            weights = sorted([float(h.weight_pct or 0.0) for h in eq], reverse=True)
            top5 = sum(weights[:5]) if weights else 0.0
            single = weights[0] if weights else 0.0

            # Sector shift vs previous month.
            cur_sec = {r.sector: float(r.weight_pct or 0.0) for r in db.query(MFSectorAlloc).filter_by(family_id=fid, month=m).all()}
            prev_sec = {r.sector: float(r.weight_pct or 0.0) for r in db.query(MFSectorAlloc).filter_by(family_id=fid, month=prev_m).all()}
            shift_max = 0.0
            if cur_sec and prev_sec:
                for k in set(cur_sec.keys()) | set(prev_sec.keys()):
                    shift_max = max(shift_max, abs(cur_sec.get(k, 0.0) - prev_sec.get(k, 0.0)))

            # Holdings adds/removes vs previous month.
            cur_names = {h.name for h in eq}
            prev_names = {h.name for h in db.query(MFHolding).filter_by(family_id=fid, month=prev_m, holding_type="equity").all()}
            added = len(cur_names - prev_names) if prev_names else 0
            removed = len(prev_names - cur_names) if prev_names else 0

            family_summaries[fid] = {
                "top5_weight_pct": top5,
                "max_single_weight_pct": single,
                "equity_count": len(eq),
                "sector_shift_max_abs_pct": shift_max,
                "holdings_added_count": added,
                "holdings_removed_count": removed,
            }

            # Keep a tiny extra pause to avoid burst patterns on holdings fetches.
            time.sleep(max(rate_limit_s, 0.25))

            # Persist cursor so restarts do not cause a refetch storm.
            _set_cursor(db, provider="mfdata", endpoint_class="monthly_holdings", cursor_json={"month": m.isoformat(), "next_index": i + 1})

        # Reset cursor on successful completion.
        _set_cursor(
            db,
            provider="mfdata",
            endpoint_class="monthly_holdings",
            cursor_json={"month": m.isoformat(), "next_index": 0, "completed_at": datetime.utcnow().isoformat()},
        )

        # Compute family overlap among monitored funds for this month (equity holdings only).
        hold_map: dict[int, dict[str, float]] = {}
        for fid in family_summaries.keys():
            rows_h = db.query(MFHolding).filter_by(family_id=fid, month=m, holding_type="equity").all()
            hold_map[fid] = {h.name: float(h.weight_pct or 0.0) for h in rows_h if h.name and h.weight_pct is not None}

        # Representative scheme (for display) per family.
        rep_scheme: dict[int, dict[str, Any]] = {}
        for s in monitored:
            if s.family_id is None:
                continue
            if s.family_id not in rep_scheme:
                rep_scheme[s.family_id] = {"scheme_code": s.scheme_code, "scheme_name": s.scheme_name}

        overlaps_for: dict[int, list[dict[str, Any]]] = {fid: [] for fid in hold_map.keys()}
        fids = list(hold_map.keys())
        for i in range(len(fids)):
            a = fids[i]
            wa = hold_map[a]
            if not wa:
                continue
            for j in range(i + 1, len(fids)):
                b = fids[j]
                wb = hold_map[b]
                if not wb:
                    continue
                # Overlap % = sum(min(weight_i)) across common holdings
                common = set(wa.keys()) & set(wb.keys())
                ov = sum(min(wa[n], wb[n]) for n in common)
                if ov <= 0:
                    continue
                overlaps_for[a].append({"other_family_id": b, "overlap_pct": ov, **(rep_scheme.get(b) or {})})
                overlaps_for[b].append({"other_family_id": a, "overlap_pct": ov, **(rep_scheme.get(a) or {})})

        for fid, lst in overlaps_for.items():
            lst_sorted = sorted(lst, key=lambda x: float(x.get("overlap_pct") or 0.0), reverse=True)[:10]
            family_summaries[fid]["overlaps"] = lst_sorted
            family_summaries[fid]["overlap_max_pct"] = float(lst_sorted[0]["overlap_pct"]) if lst_sorted else 0.0

        # Evaluate and store holdings signals per monitored scheme.
        rb = _active_rulebook(db)
        for s in monitored:
            if s.family_id is None:
                continue
            summary = family_summaries.get(s.family_id)
            if not summary:
                continue
            cands = eval_holdings_signals(
                scheme_code=s.scheme_code,
                family_id=s.family_id,
                month=m,
                holdings_summary=summary,
                rulebook=rb,
            )
            for c in cands:
                ins = text(
                    """
                    INSERT INTO mf_signals (
                      scheme_code, family_id, signal_type, nav_date, triggered_at,
                      base_score, confidence_score, context_json, status
                    )
                    VALUES (
                      :scheme_code, :family_id, :signal_type, :nav_date, NOW(),
                      :base_score, :confidence_score, :context_json, 'pending'
                    )
                    ON CONFLICT (scheme_code, signal_type, nav_date) DO NOTHING
                    """
                )
                res = db.execute(
                    ins,
                    {
                        "scheme_code": c.scheme_code,
                        "family_id": c.family_id,
                        "signal_type": c.signal_type,
                        "nav_date": c.nav_date,
                        "base_score": c.base_score,
                        "confidence_score": c.confidence_score,
                        "context_json": json.dumps(c.context),
                    },
                )
                signals += int(res.rowcount or 0)
            db.commit()

        stats = {"month": str(m), "families": len(family_ids), "snapshots": snaps, "holdings_rows": holdings_rows, "signals": signals}
        _run_finish(db, run, ok=True, stats=stats)
        return stats
    except Exception as e:
        db.rollback()
        _run_finish(db, run, ok=False, error=str(e))
        raise


def bootstrap_holdings_history(db: Session, *, months: int = 12, rate_limit_s: float = 1.0) -> dict[str, Any]:
    """
    Backfill holdings snapshots for the last N months (monitored universe only).

    - Uses mfdata family holdings endpoint with `month=YYYY-MM`.
    - Idempotent refresh: replaces parsed rows for each (family_id, month).
    - Resumable per-family cursor in mf_ingestion_cursors.
    """
    run = _run_start(db, "holdings_bootstrap")
    try:
        if not settings.MF_INGESTION_ENABLED or not settings.MF_HOLDINGS_ENABLED:
            stats = {"skipped": True, "reason": "MF_HOLDINGS_ENABLED=false or MF_INGESTION_ENABLED=false"}
            _run_finish(db, run, ok=True, stats=stats)
            return stats

        ensure_curated_watchlist(db)

        months = max(1, min(int(months), 36))
        today = datetime.now().date()
        m0 = date(today.year, today.month, 1)
        month_list: list[date] = []
        cur_m = m0
        for _ in range(months):
            month_list.append(cur_m)
            prev_last = cur_m - timedelta(days=1)
            cur_m = date(prev_last.year, prev_last.month, 1)

        monitored = db.query(MFScheme).filter_by(monitored=True).all()
        family_ids = sorted({s.family_id for s in monitored if s.family_id is not None})

        snapshots = 0
        holdings_rows = 0
        families_done = 0
        months_done = 0
        skipped_retry_after = 0

        for fid in family_ids:
            cur = _get_cursor(db, provider="mfdata", endpoint_class="holdings_history", family_id=int(fid))
            cur_json = dict(cur.cursor_json) if cur else {}
            if cur_json.get("months") != months:
                cur_json = {"months": months, "next_index": 0}

            retry_after = cur_json.get("retry_after")
            if retry_after:
                try:
                    ra = datetime.fromisoformat(str(retry_after))
                    if ra > datetime.utcnow():
                        skipped_retry_after += 1
                        continue
                except Exception:
                    pass

            start_idx = int(cur_json.get("next_index") or 0)
            for mi in range(start_idx, len(month_list)):
                m = month_list[mi]
                month_param = f"{m.year:04d}-{m.month:02d}"

                try:
                    with task(db, run_id=str(run.id), provider="mfdata", endpoint_class="holdings", family_id=int(fid)) as t:
                        data = fetch_family_holdings(int(fid), task=t, month=month_param)
                    if not data:
                        cur_json["next_index"] = mi + 1
                        _set_cursor(db, provider="mfdata", endpoint_class="holdings_history", family_id=int(fid), cursor_json=cur_json)
                        continue

                    snap = MFFamilyHoldingsSnapshot(
                        family_id=int(fid),
                        month=m,
                        total_aum=(float(data.get("total_aum")) if data.get("total_aum") is not None else None),
                        equity_pct=(float(data.get("equity_pct")) if data.get("equity_pct") is not None else None),
                        debt_pct=(float(data.get("debt_pct")) if data.get("debt_pct") is not None else None),
                        other_pct=(float(data.get("other_pct")) if data.get("other_pct") is not None else None),
                        fetched_at=(datetime.fromisoformat(data["fetched_at"]) if data.get("fetched_at") else None),
                        raw_json=data,
                    )
                    db.merge(snap)
                    db.commit()
                    snapshots += 1

                    db.query(MFHolding).filter_by(family_id=int(fid), month=m).delete()
                    db.query(MFSectorAlloc).filter_by(family_id=int(fid), month=m).delete()
                    db.commit()

                    def add_list(items: list[dict[str, Any]], holding_type: str):
                        nonlocal holdings_rows
                        seen: set[str] = set()
                        for it in items:
                            name = str(it.get("name") or "").strip()
                            if not name:
                                continue
                            if name in seen:
                                continue
                            seen.add(name)
                            db.add(
                                MFHolding(
                                    family_id=int(fid),
                                    month=m,
                                    holding_type=holding_type,
                                    name=name,
                                    weight_pct=(float(it["weight_pct"]) if it.get("weight_pct") is not None else None),
                                    market_value=(float(it["market_value"]) if it.get("market_value") is not None else None),
                                    quantity=(float(it["quantity"]) if it.get("quantity") is not None else None),
                                    month_change_qty=(float(it["month_change_qty"]) if it.get("month_change_qty") is not None else None),
                                    month_change_pct=(float(it["month_change_pct"]) if it.get("month_change_pct") is not None else None),
                                    credit_rating=it.get("credit_rating"),
                                    maturity_date=(datetime.fromisoformat(it["maturity_date"]).date() if it.get("maturity_date") else None),
                                    isin=it.get("isin"),
                                    ticker=it.get("ticker"),
                                    sector=it.get("sector"),
                                )
                            )
                            holdings_rows += 1

                    add_list(data.get("equity_holdings") or [], "equity")
                    add_list(data.get("debt_holdings") or [], "debt")
                    add_list(data.get("other_holdings") or [], "other")
                    db.commit()

                    with task(db, run_id=str(run.id), provider="mfdata", endpoint_class="sectors", family_id=int(fid)) as t2:
                        sectors = fetch_family_sectors(int(fid), task=t2, month=month_param) or []
                    for it in sectors:
                        if not isinstance(it, dict):
                            continue
                        sec = str(it.get("sector") or it.get("name") or "")
                        w = it.get("weight_pct")
                        if not sec or w is None:
                            continue
                        db.add(MFSectorAlloc(family_id=int(fid), month=m, sector=sec, weight_pct=float(w)))
                    db.commit()

                    months_done += 1
                    cur_json["next_index"] = mi + 1
                    cur_json["retry_after"] = None
                    _set_cursor(db, provider="mfdata", endpoint_class="holdings_history", family_id=int(fid), cursor_json=cur_json)

                    time.sleep(max(rate_limit_s, 0.25))
                except Exception as e:
                    cur_json["retry_after"] = (datetime.utcnow() + timedelta(minutes=60)).isoformat()
                    cur_json["last_error"] = str(e)[:500]
                    _set_cursor(db, provider="mfdata", endpoint_class="holdings_history", family_id=int(fid), cursor_json=cur_json)
                    break

            families_done += 1
            _set_cursor(
                db,
                provider="mfdata",
                endpoint_class="holdings_history",
                family_id=int(fid),
                cursor_json={"months": months, "next_index": 0, "completed_at": datetime.utcnow().isoformat()},
            )

        stats = {
            "families": len(family_ids),
            "families_done": families_done,
            "months_done": months_done,
            "snapshots": snapshots,
            "holdings_rows": holdings_rows,
            "months": months,
            "skipped_retry_after": skipped_retry_after,
        }
        _run_finish(db, run, ok=True, stats=stats)
        return stats
    except Exception as e:
        db.rollback()
        _run_finish(db, run, ok=False, error=str(e))
        raise
