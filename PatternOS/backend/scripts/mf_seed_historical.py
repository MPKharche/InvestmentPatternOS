#!/usr/bin/env python3
"""
One-time bootstrap: seed historical MF NAV (Parquet) + scheme master (CSV).

Design goals:
  - Idempotent: mf_nav_daily PK (scheme_code, nav_date) prevents duplicates.
  - Fast: bulk COPY, no row-by-row inserts.
  - Safe: seed once, then daily AMFI pipeline continues.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator

import httpx
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


PARQUET_DEFAULT = "https://github.com/InertExpert2911/Mutual_Fund_Data/raw/main/mutual_fund_nav_history.parquet"
SCHEMES_CSV_DEFAULT = "https://github.com/InertExpert2911/Mutual_Fund_Data/raw/main/mutual_fund_data.csv"
AMFI_NAVALL_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"


def load_env() -> None:
    env_path = ROOT.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def db_dsn(dbname: str | None = None) -> dict[str, str]:
    return dict(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        dbname=dbname or os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def ensure_db_exists() -> None:
    load_env()
    target_db = os.environ["POSTGRES_DB"]
    conn = psycopg2.connect(**db_dsn("postgres"))
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_db,))
    if not cur.fetchone():
        cur.execute(f'CREATE DATABASE "{target_db}"')
        print(f"[db] created {target_db}")
    cur.close()
    conn.close()


def download(url: str, dst: Path) -> None:
    print(f"[download] {url} -> {dst}")
    with httpx.Client(timeout=300, follow_redirects=True) as client:
        with client.stream("GET", url) as r:
            r.raise_for_status()
            with dst.open("wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)


def seed_schemes(conn) -> None:
    # Load scheme master CSV into mf_schemes (upsert by scheme_code).
    import pandas as pd  # pandas already in requirements

    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "schemes.csv"
        download(SCHEMES_CSV_DEFAULT, csv_path)
        df = pd.read_csv(csv_path)

    # Normalize expected columns from source.
    cols = {c.lower(): c for c in df.columns}
    code_col = cols.get("scheme_code") or cols.get("scheme code") or cols.get("amfi_code")
    name_col = cols.get("scheme_name") or cols.get("scheme name") or cols.get("name")
    amc_col = cols.get("amc")
    cat_col = cols.get("scheme_category") or cols.get("category")
    if not code_col:
        raise RuntimeError("Could not find Scheme_Code column in scheme master CSV")

    cur = conn.cursor()
    tmp = tempfile.NamedTemporaryFile("w", delete=False, newline="", encoding="utf-8")
    try:
        w = csv.writer(tmp)
        w.writerow(["scheme_code", "scheme_name", "amc_name", "category"])
        for _, r in df.iterrows():
            try:
                code = int(r[code_col])
            except Exception:
                continue
            w.writerow([code, (r.get(name_col) if name_col else None), (r.get(amc_col) if amc_col else None), (r.get(cat_col) if cat_col else None)])
        tmp.flush()
        tmp.close()

        cur.execute("CREATE TEMP TABLE tmp_mf_schemes (scheme_code INT, scheme_name TEXT, amc_name TEXT, category TEXT)")
        with open(tmp.name, "r", encoding="utf-8") as f:
            cur.copy_expert("COPY tmp_mf_schemes FROM STDIN WITH CSV HEADER", f)
        cur.execute(
            """
            INSERT INTO mf_schemes (scheme_code, scheme_name, amc_name, category, updated_at)
            SELECT scheme_code, scheme_name, amc_name, category, NOW() FROM tmp_mf_schemes
            ON CONFLICT (scheme_code) DO UPDATE SET
              scheme_name = COALESCE(EXCLUDED.scheme_name, mf_schemes.scheme_name),
              amc_name = COALESCE(EXCLUDED.amc_name, mf_schemes.amc_name),
              category = COALESCE(EXCLUDED.category, mf_schemes.category),
              updated_at = NOW()
            """
        )
        conn.commit()
        print("[ok] seeded scheme master")
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass
        cur.close()


def iter_parquet_rows(parquet_path: Path) -> Iterator[tuple[int, str, float]]:
    """
    Stream (scheme_code, nav_date_iso, nav) from parquet row groups to avoid loading into RAM.
    Parquet columns expected: Scheme_Code, Date, NAV
    """
    import pyarrow.parquet as pq

    pf = pq.ParquetFile(parquet_path)
    for i in range(pf.num_row_groups):
        t = pf.read_row_group(i, columns=["Scheme_Code", "Date", "NAV"]).to_pydict()
        codes = t["Scheme_Code"]
        dates = t["Date"]
        navs = t["NAV"]
        for c, d, n in zip(codes, dates, navs):
            if c is None or d is None or n is None:
                continue
            try:
                code = int(c)
                # Date might be datetime/date/string; normalize to ISO yyyy-mm-dd.
                if isinstance(d, str):
                    nav_date = d[:10]
                else:
                    nav_date = d.date().isoformat() if hasattr(d, "date") else str(d)
                nav = float(n)
            except Exception:
                continue
            yield (code, nav_date, nav)


def seed_nav_history(conn, parquet_url: str) -> None:
    with tempfile.TemporaryDirectory() as td:
        parquet_path = Path(td) / "nav_history.parquet"
        download(parquet_url, parquet_path)

        cur = conn.cursor()
        cur.execute("CREATE TEMP TABLE tmp_mf_nav (scheme_code INT, nav_date DATE, nav NUMERIC(18,6))")

        # Write a CSV stream chunk-wise and COPY into temp table in batches.
        # This keeps Python memory bounded, while Postgres handles dedupe at insert time.
        batch = 200_000
        buf_rows: list[tuple[int, str, float]] = []
        total = 0

        def flush(rows: list[tuple[int, str, float]]) -> None:
            nonlocal total
            if not rows:
                return
            with tempfile.NamedTemporaryFile("w", delete=False, newline="", encoding="utf-8") as tmp:
                w = csv.writer(tmp)
                for code, d, nav in rows:
                    w.writerow([code, d, nav])
                tmp_path = tmp.name
            with open(tmp_path, "r", encoding="utf-8") as f:
                cur.copy_expert("COPY tmp_mf_nav (scheme_code, nav_date, nav) FROM STDIN WITH CSV", f)
            os.unlink(tmp_path)
            total += len(rows)
            print(f"[copy] +{len(rows)} rows (total buffered copied={total})")

        for row in iter_parquet_rows(parquet_path):
            buf_rows.append(row)
            if len(buf_rows) >= batch:
                flush(buf_rows)
                buf_rows = []

        flush(buf_rows)

        # Ensure schemes exist for FK: insert missing scheme codes as stubs.
        cur.execute(
            """
            INSERT INTO mf_schemes (scheme_code, scheme_name, updated_at)
            SELECT DISTINCT scheme_code, CONCAT('Scheme ', scheme_code), NOW() FROM tmp_mf_nav
            ON CONFLICT (scheme_code) DO NOTHING
            """
        )

        # Upsert NAV warehouse, dedup by PK.
        cur.execute(
            """
            INSERT INTO mf_nav_daily (scheme_code, nav_date, nav, source, ingested_at)
            SELECT scheme_code, nav_date, nav, 'seed_parquet', NOW() FROM tmp_mf_nav
            ON CONFLICT (scheme_code, nav_date) DO NOTHING
            """
        )
        conn.commit()
        print("[ok] seeded NAV history into mf_nav_daily")
        cur.close()


def backfill_from_amfi(conn) -> None:
    """
    Pull AMFI NAVAll.txt once to fill any gap between the parquet seed and "today".

    Safe to run multiple times due to mf_nav_daily PK (scheme_code, nav_date).
    """
    from app.mf.amfi import parse_navall  # local import to keep script dependency-light

    cur = conn.cursor()
    try:
        cur.execute("SELECT MAX(nav_date) FROM mf_nav_daily")
        max_date = cur.fetchone()[0]
    except Exception:
        conn.rollback()
        cur.close()
        print("[amfi] skipped (mf_nav_daily missing?)")
        return

    if not max_date:
        print("[amfi] skipped (no existing nav rows)")
        cur.close()
        return

    print(f"[amfi] backfill newer than {max_date}...")
    with httpx.Client(timeout=120) as client:
        r = client.get(AMFI_NAVALL_URL)
        r.raise_for_status()
        txt = r.text

    rows = [rr for rr in parse_navall(txt.splitlines()) if rr.nav_date and rr.nav_date > max_date]
    if not rows:
        print("[amfi] nothing new to backfill")
        cur.close()
        return

    tmp = tempfile.NamedTemporaryFile("w", delete=False, newline="", encoding="utf-8")
    try:
        w = csv.writer(tmp)
        w.writerow(["scheme_code", "nav_date", "nav"])
        for rr in rows:
            w.writerow([rr.scheme_code, rr.nav_date.isoformat(), rr.nav])
        tmp.flush()
        tmp.close()

        cur.execute("CREATE TEMP TABLE tmp_mf_nav_backfill (scheme_code INT, nav_date DATE, nav NUMERIC)")
        with open(tmp.name, "r", encoding="utf-8") as f:
            cur.copy_expert("COPY tmp_mf_nav_backfill FROM STDIN WITH CSV HEADER", f)
        cur.execute(
            """
            INSERT INTO mf_nav_daily (scheme_code, nav_date, nav, source, ingested_at)
            SELECT scheme_code, nav_date, nav, 'amfi', NOW() FROM tmp_mf_nav_backfill
            ON CONFLICT (scheme_code, nav_date) DO NOTHING
            """
        )
        conn.commit()
        print(f"[ok] backfilled {len(rows)} NAV rows from AMFI")
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass
        cur.close()


def _run_start(conn) -> str | None:
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO mf_ingestion_runs (run_type, started_at, status) VALUES ('historical_seed', NOW(), 'running') RETURNING id"
        )
        rid = cur.fetchone()[0]
        conn.commit()
        return str(rid)
    except Exception:
        conn.rollback()
        return None
    finally:
        cur.close()


def _run_finish(conn, run_id: str | None, *, ok: bool, stats: dict | None = None, error: str | None = None) -> None:
    if not run_id:
        return
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE mf_ingestion_runs
            SET finished_at = NOW(), status = %s, stats_json = %s::jsonb, error_text = %s
            WHERE id = %s
            """,
            ("success" if ok else "failed", json.dumps(stats or {}), error, run_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        cur.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet-url", default=PARQUET_DEFAULT)
    ap.add_argument("--skip-parquet", action="store_true")
    ap.add_argument("--skip-schemes", action="store_true")
    args = ap.parse_args()

    ensure_db_exists()
    conn = psycopg2.connect(**db_dsn())
    conn.autocommit = False
    run_id = None
    try:
        run_id = _run_start(conn)
        if not args.skip_schemes:
            seed_schemes(conn)
        if not args.skip_parquet:
            seed_nav_history(conn, args.parquet_url)
        backfill_from_amfi(conn)
        _run_finish(conn, run_id, ok=True, stats={"parquet_url": args.parquet_url, "skip_schemes": args.skip_schemes, "skip_parquet": args.skip_parquet})
    except Exception as e:
        _run_finish(conn, run_id, ok=False, stats={"parquet_url": args.parquet_url}, error=str(e))
        raise
    finally:
        conn.close()

    print("[done] historical seed complete")


if __name__ == "__main__":
    main()
