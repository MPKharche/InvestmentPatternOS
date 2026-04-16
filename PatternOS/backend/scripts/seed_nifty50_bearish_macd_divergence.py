#!/usr/bin/env python3
"""Insert the canonical Nifty50 bearish MACD divergence pattern if missing."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.db.models import Pattern, PatternVersion  # noqa: E402

NAME = "Nifty50 Bearish MACD Divergence v1"
RULEBOOK_PATH = ROOT / "seed_data" / "nifty50_bearish_macd_divergence_v1.rulebook.json"


def main() -> None:
    rulebook = json.loads(RULEBOOK_PATH.read_text())
    db = SessionLocal()
    try:
        existing = db.query(Pattern).filter_by(name=NAME).first()
        if existing:
            print(f"[skip] Pattern already exists: {existing.id}")
            return
        pat = Pattern(
            name=NAME,
            description=rulebook.get("description", "")[:500],
            status="active",
            timeframes=["1d"],
        )
        db.add(pat)
        db.flush()
        pv = PatternVersion(
            pattern_id=pat.id,
            version=1,
            rulebook_json=rulebook,
            change_summary="Seed: Nifty50 bearish MACD divergence v1",
        )
        db.add(pv)
        db.commit()
        print(f"[ok] Created pattern_id={pat.id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
