#!/usr/bin/env python3
"""
One-time bootstrap: seed historical MF NAV (Parquet) + scheme master (CSV).

Primary dataset (Kaggle): https://www.kaggle.com/datasets/tharunreddy2911/mutual-fund-data

Ways to load it
----------------

1) **Kaggle zip on your machine** (large download + long DB load; exact dataset bits)::

    pip install kaggle
    # Put API credentials in ~/.kaggle/kaggle.json

    # From the PatternOS repo root (folder that contains ``backend/`` and ``frontend/``):
    mkdir -p ./data/mf-kaggle
    kaggle datasets download -d tharunreddy2911/mutual-fund-data -p ./data/mf-kaggle
    unzip -o ./data/mf-kaggle/mutual-fund-data.zip -d ./data/mf-kaggle

    cd backend
    ../.venv/bin/python scripts/mf_seed_historical.py --kaggle-dir ../../data/mf-kaggle

   Or set ``MF_KAGGLE_DATA_DIR`` in ``PatternOS/.env`` to the **extracted** folder and run::

    ../.venv/bin/python scripts/mf_seed_historical.py

   Optional: ``--since-date YYYY-MM-DD`` skips older NAV rows while scanning the parquet
   (smaller test run; scheme CSV still loads unless ``--skip-schemes``).

2) **Public mirror** (same filenames) via HTTPS — defaults in this file; override with
   ``MF_HISTORICAL_PARQUET_URL`` / ``MF_HISTORICAL_SCHEMES_CSV_URL`` or ``--parquet-path`` / ``--csv-path``.

After a full historical seed
----------------------------

Realign the priority-AMC equity Direct Growth watchlist and pull the latest NAV day::

    curl -X POST http://127.0.0.1:8000/api/v1/mf/pipeline/watchlist/sync-priority-amc
    curl -X POST http://127.0.0.1:8000/api/v1/mf/pipeline/nav/run

(Adjust host/port to your API, or use **MF → Pipeline runs** in the app:
**Sync priority AMC watchlist** then **Run NAV now**.)

Production database
-------------------

The script writes to whatever Postgres ``POSTGRES_*`` points at (``PatternOS/.env`` or the shell).
For production, run it **on the prod network** (app host, bastion, or ``ssh -L`` tunnel to Postgres)
so ``mf_nav_daily`` fills on the **same** DB the API uses. Then run the two POSTs above (or the
two MF pipeline buttons). Scheme detail pages show ``nav_days_in_db`` / date range from
``mf_nav_daily`` — if a scheme still has ~1 day after seed, that AMFI code may be missing from
the parquet snapshot you used, or the seed did not hit this database.

Design goals
------------

- Idempotent: ``mf_nav_daily`` primary key ``(scheme_code, nav_date)`` + ``ON CONFLICT DO NOTHING``.
  Source duplicates (same scheme + date) are collapsed with ``MAX(nav)`` before insert so one NAV per day.
- Fast: bulk COPY, no row-by-row inserts.
- Safe: seed once, then the daily AMFI pipeline continues.

SQL checks (psql / any SQL client)
----------------------------------

Global duplicate keys (expect **0 rows**)::

    SELECT scheme_code, nav_date, COUNT(*) AS c
    FROM mf_nav_daily
    GROUP BY scheme_code, nav_date
    HAVING COUNT(*) > 1;

Per-scheme duplicates — replace ``147541`` with your AMFI ``scheme_code`` (expect **0 rows**)::

    SELECT scheme_code, nav_date, COUNT(*) AS c
    FROM mf_nav_daily
    WHERE scheme_code = 147541
    GROUP BY scheme_code, nav_date
    HAVING COUNT(*) > 1;

Per-scheme NAV coverage for that scheme::

    SELECT COUNT(*) AS days, MIN(nav_date) AS first_nav, MAX(nav_date) AS last_nav
    FROM mf_nav_daily
    WHERE scheme_code = 147541;
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

import httpx
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Public mirror of the Kaggle bundle (see module docstring).
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


def default_parquet_url() -> str:
    load_env()
    return os.environ.get("MF_HISTORICAL_PARQUET_URL", PARQUET_DEFAULT).strip() or PARQUET_DEFAULT


def default_csv_url() -> str:
    load_env()
    return os.environ.get("MF_HISTORICAL_SCHEMES_CSV_URL", SCHEMES_CSV_DEFAULT).strip() or SCHEMES_CSV_DEFAULT


def discover_kaggle_dataset_files(root: Path) -> tuple[Path | None, Path | None]:
    """
    Locate parquet + CSV inside an extracted Kaggle bundle (any nesting depth).
    Prefers filenames from tharunreddy2911/mutual-fund-data.
    """
    root = root.expanduser().resolve()
    if not root.is_dir():
        return None, None

    parquets = sorted(root.rglob("*.parquet"))
    csvs = sorted(root.rglob("*.csv"))

    def pick_parquet(paths: list[Path]) -> Path | None:
        for key in ("nav_history", "nav", "history"):
            for p in paths:
                if key in p.name.lower():
                    return p
        return paths[0] if paths else None

    def pick_csv(paths: list[Path]) -> Path | None:
        for key in ("mutual_fund_data", "scheme", "master"):
            for p in paths:
                if key in p.name.lower():
                    return p
        return paths[0] if paths else None

    return pick_parquet(parquets), pick_csv(csvs)


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


def _prepare_file(*, url: str | None, local_path: str | None, dst: Path) -> None:
    if local_path:
        src = Path(local_path).expanduser().resolve()
        if not src.is_file():
            raise FileNotFoundError(f"Local file not found: {src}")
        print(f"[copy] {src} -> {dst}")
        shutil.copyfile(src, dst)
        return
    if not url:
        raise ValueError("Need url or local path")
    print(f"[download] {url} -> {dst}")
    with httpx.Client(timeout=600, follow_redirects=True) as client:
        with client.stream("GET", url) as r:
            r.raise_for_status()
            with dst.open("wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)


def seed_schemes(conn, *, csv_url: str | None = None, csv_path: str | None = None) -> None:
    import pandas as pd  # pandas already in requirements

    with tempfile.TemporaryDirectory() as td:
        csv_path_dst = Path(td) / "schemes.csv"
        _prepare_file(url=csv_url or default_csv_url(), local_path=csv_path, dst=csv_path_dst)
        df = pd.read_csv(csv_path_dst)

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


def _parquet_nav_column_names(pf) -> tuple[str, str, str]:
    import pyarrow.parquet as pq  # noqa: F401

    names = list(pf.schema_arrow.names)
    norm = {n.lower().replace(" ", "_"): n for n in names}

    def pick(*candidates: str) -> str:
        for raw in candidates:
            k = raw.lower().replace(" ", "_")
            if k in norm:
                return norm[k]
        raise RuntimeError(f"Could not resolve column among {candidates} — parquet has: {names}")

    code = pick("Scheme_Code", "scheme_code", "SCHEME_CODE", "amfi_code", "Amfi_Code")
    dcol = pick("Date", "date", "nav_date", "Nav_Date", "DATE")
    ncol = pick("NAV", "nav", "Net_Asset_Value", "net_asset_value")
    return code, dcol, ncol


def iter_parquet_rows(parquet_path: Path, *, since: date | None = None) -> Iterator[tuple[int, str, float]]:
    import pyarrow.parquet as pq

    pf = pq.ParquetFile(parquet_path)
    code_c, date_c, nav_c = _parquet_nav_column_names(pf)
    cols = [code_c, date_c, nav_c]

    for i in range(pf.num_row_groups):
        t = pf.read_row_group(i, columns=cols).to_pydict()
        codes = t[code_c]
        dates = t[date_c]
        navs = t[nav_c]
        for c, d, n in zip(codes, dates, navs):
            if c is None or d is None or n is None:
                continue
            try:
                code = int(c)
                if isinstance(d, str):
                    nav_date = d[:10]
                else:
                    nav_date = d.date().isoformat() if hasattr(d, "date") else str(d)
                nav = float(n)
                if since is not None:
                    nd = date.fromisoformat(nav_date[:10])
                    if nd < since:
                        continue
            except Exception:
                continue
            yield (code, nav_date, nav)


def seed_nav_history(
    conn,
    *,
    parquet_url: str | None = None,
    parquet_path: str | None = None,
    since: date | None = None,
) -> None:
    with tempfile.TemporaryDirectory() as td:
        parquet_dst = Path(td) / "nav_history.parquet"
        _prepare_file(url=parquet_url or default_parquet_url(), local_path=parquet_path, dst=parquet_dst)

        cur = conn.cursor()
        cur.execute("CREATE TEMP TABLE tmp_mf_nav (scheme_code INT, nav_date DATE, nav NUMERIC(18,6))")

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

        for row in iter_parquet_rows(parquet_dst, since=since):
            buf_rows.append(row)
            if len(buf_rows) >= batch:
                flush(buf_rows)
                buf_rows = []

        flush(buf_rows)

        cur.execute(
            """
            INSERT INTO mf_schemes (scheme_code, scheme_name, updated_at)
            SELECT DISTINCT scheme_code, CONCAT('Scheme ', scheme_code), NOW() FROM tmp_mf_nav
            ON CONFLICT (scheme_code) DO NOTHING
            """
        )

        # Parquet can repeat (scheme_code, nav_date). Postgres rejects multiple proposed rows
        # with the same PK in one INSERT even with ON CONFLICT DO NOTHING — collapse first.
        cur.execute(
            """
            SELECT COUNT(*)::bigint AS raw_rows,
                   COUNT(DISTINCT (scheme_code, nav_date))::bigint AS distinct_keys
            FROM tmp_mf_nav
            """
        )
        raw_rows, distinct_keys = cur.fetchone()
        dup_nav = int(raw_rows or 0) - int(distinct_keys or 0)
        if dup_nav > 0:
            print(f"[nav] dedupe: {dup_nav} duplicate (scheme_code, nav_date) rows in source → one NAV each (max(nav))")

        cur.execute(
            """
            INSERT INTO mf_nav_daily (scheme_code, nav_date, nav, source, ingested_at)
            SELECT scheme_code, nav_date, nav, 'seed_parquet', NOW()
            FROM (
                SELECT scheme_code, nav_date, MAX(nav) AS nav
                FROM tmp_mf_nav
                GROUP BY scheme_code, nav_date
            ) AS u
            ON CONFLICT (scheme_code, nav_date) DO NOTHING
            """
        )
        ins_count = cur.rowcount
        conn.commit()
        print(f"[ok] seeded NAV history into mf_nav_daily ({ins_count} rows inserted, {distinct_keys} unique keys from parquet)")
        cur.close()


def backfill_from_amfi(conn) -> None:
    from app.mf.amfi import parse_navall

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
            SELECT scheme_code, nav_date, nav, 'amfi', NOW()
            FROM (
                SELECT scheme_code, nav_date, MAX(nav) AS nav
                FROM tmp_mf_nav_backfill
                GROUP BY scheme_code, nav_date
            ) AS u
            ON CONFLICT (scheme_code, nav_date) DO NOTHING
            """
        )
        amfi_ins = cur.rowcount
        conn.commit()
        print(f"[ok] backfilled AMFI: {len(rows)} parsed points → {amfi_ins} rows inserted (after dedupe + conflict skip)")
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
    ap.add_argument(
        "--kaggle-dir",
        default=None,
        help="Folder with extracted Kaggle tharunreddy2911/mutual-fund-data (uses *.parquet + *.csv inside). "
        "Also reads MF_KAGGLE_DATA_DIR from .env when set.",
    )
    ap.add_argument("--parquet-url", default=None, help="Override MF_HISTORICAL_PARQUET_URL (Kaggle mirror default).")
    ap.add_argument("--parquet-path", default=None, help="Local parquet file (e.g. after kaggle datasets download).")
    ap.add_argument("--csv-url", default=None, help="Override MF_HISTORICAL_SCHEMES_CSV_URL.")
    ap.add_argument("--csv-path", default=None, help="Local scheme master CSV.")
    ap.add_argument("--skip-parquet", action="store_true")
    ap.add_argument("--skip-schemes", action="store_true")
    ap.add_argument(
        "--since-date",
        default=None,
        help="If set (YYYY-MM-DD), only import NAV rows on/after this date (e.g. 2006-01-01).",
    )
    args = ap.parse_args()
    since_dt: date | None = None
    if args.since_date:
        since_dt = date.fromisoformat(str(args.since_date).strip()[:10])

    load_env()
    kaggle_dir = args.kaggle_dir or os.environ.get("MF_KAGGLE_DATA_DIR", "").strip() or None
    pq_path = args.parquet_path
    csv_path = args.csv_path
    if kaggle_dir:
        pq_guess, csv_guess = discover_kaggle_dataset_files(Path(kaggle_dir))
        if not pq_path and pq_guess:
            pq_path = str(pq_guess)
            print(f"[kaggle-dir] parquet: {pq_path}")
        if not csv_path and csv_guess:
            csv_path = str(csv_guess)
            print(f"[kaggle-dir] csv: {csv_path}")

    ensure_db_exists()
    conn = psycopg2.connect(**db_dsn())
    conn.autocommit = False
    run_id = None
    purl = args.parquet_url or default_parquet_url()
    curl = args.csv_url or default_csv_url()
    try:
        run_id = _run_start(conn)
        if not args.skip_schemes:
            seed_schemes(conn, csv_url=curl if not csv_path else None, csv_path=csv_path)
        if not args.skip_parquet:
            seed_nav_history(
                conn,
                parquet_url=purl if not pq_path else None,
                parquet_path=pq_path,
                since=since_dt,
            )
        backfill_from_amfi(conn)
        _run_finish(
            conn,
            run_id,
            ok=True,
            stats={
                "parquet_url": purl,
                "csv_url": curl,
                "kaggle_dir": kaggle_dir,
                "parquet_path": pq_path,
                "csv_path": csv_path,
                "skip_schemes": args.skip_schemes,
                "skip_parquet": args.skip_parquet,
                "since_date": args.since_date,
            },
        )
    except Exception as e:
        _run_finish(conn, run_id, ok=False, stats={"parquet_url": purl}, error=str(e))
        raise
    finally:
        conn.close()

    print("[done] historical seed complete")


if __name__ == "__main__":
    main()
