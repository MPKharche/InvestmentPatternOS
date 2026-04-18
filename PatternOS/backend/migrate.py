"""
Run DB migrations. Usage: python migrate.py
Reads credentials from .env in the PatternOS root.
"""
import os
import sys
from pathlib import Path

# Load .env from parent directory (PatternOS root)
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

host     = os.environ["POSTGRES_HOST"]
port     = os.environ["POSTGRES_PORT"]
db       = os.environ["POSTGRES_DB"]
user     = os.environ["POSTGRES_USER"]
password = os.environ["POSTGRES_PASSWORD"]

# 1. Create database if it doesn't exist
print(f"Connecting to PostgreSQL at {host}:{port} as {user}...")
conn = psycopg2.connect(host=host, port=port, dbname="postgres",
                        user=user, password=password)
conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cur = conn.cursor()
cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db,))
if not cur.fetchone():
    cur.execute(f'CREATE DATABASE "{db}"')
    print(f"  Created database: {db}")
else:
    print(f"  Database already exists: {db}")
cur.close()
conn.close()

# 2. Run migration files in order
migrations_dir = Path(__file__).parent / "migrations"
migration_files = sorted(migrations_dir.glob("*.sql"))

conn = psycopg2.connect(host=host, port=port, dbname=db,
                        user=user, password=password)
conn.autocommit = True
cur = conn.cursor()

for mf in migration_files:
    print(f"  Running migration: {mf.name}")
    sql = mf.read_text(encoding="utf-8")
    try:
        cur.execute(sql)
        print(f"    OK")
    except Exception as e:
        print(f"    ERROR: {e}")

cur.close()
conn.close()
print("\nMigrations complete.")

# Optional: ensure the canonical divergence patterns exist in the DB.
# This keeps a fresh local DB usable immediately after running migrations.
seed_flag = os.environ.get("SEED_PRODUCTION_PATTERN_PACK", "1").strip().lower()
if seed_flag not in ("0", "false", "no", "off"):
    try:
        # Import late so migrate.py still works even if SQLAlchemy deps change.
        from app.db.seed_production_pack import seed_production_pattern_pack  # type: ignore

        for line in seed_production_pattern_pack():
            print(line)
    except Exception as e:
        print(f"[seed] ERROR: {e}")
