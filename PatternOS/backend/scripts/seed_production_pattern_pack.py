#!/usr/bin/env python3
"""Ensure core Nifty 50 divergence patterns exist and are active (live scans).

Same logic as FastAPI startup (`canonical_pattern_seed`). Run manually if you
start workers without the API process.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.db.canonical_pattern_seed import ensure_canonical_divergence_patterns  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        for line in ensure_canonical_divergence_patterns(db):
            print(line)
    finally:
        db.close()


if __name__ == "__main__":
    main()
