#!/usr/bin/env python3
"""Ensure core Nifty 50 divergence patterns exist and are active (live scans)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.db.models import Pattern, PatternVersion  # noqa: E402

PACK = [
    ("Nifty50 Bearish MACD Divergence v1", "nifty50_bearish_macd_divergence_v1.rulebook.json"),
    ("Nifty50 Bullish MACD Divergence v1", "nifty50_bullish_macd_divergence_v1.rulebook.json"),
    ("Nifty50 Bearish RSI Divergence v1", "nifty50_bearish_rsi_divergence_v1.rulebook.json"),
]


def upsert(db, name: str, rulebook: dict) -> str:
    p = db.query(Pattern).filter_by(name=name).first()
    if p:
        p.status = "active"
        p.description = (rulebook.get("description") or p.description or "")[:500]
        db.add(p)
        db.commit()
        return f"[reactivate] {name} id={p.id}"
    pat = Pattern(
        name=name,
        description=(rulebook.get("description") or "")[:500],
        status="active",
        timeframes=rulebook.get("timeframes") or ["1d"],
    )
    db.add(pat)
    db.flush()
    pv = PatternVersion(
        pattern_id=pat.id,
        version=1,
        rulebook_json=rulebook,
        change_summary=f"Seed production pack: {name}",
    )
    db.add(pv)
    db.commit()
    return f"[created] {name} id={pat.id}"


def main() -> None:
    db = SessionLocal()
    try:
        for name, fname in PACK:
            path = ROOT / "seed_data" / fname
            rb = json.loads(path.read_text())
            print(upsert(db, name, rb))
    finally:
        db.close()


if __name__ == "__main__":
    main()
