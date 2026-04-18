"""
Idempotent seed for the core divergence pattern pack.

Keeps local/dev databases usable right after migrations without manual steps.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.db.session import SessionLocal
from app.db.models import Pattern, PatternVersion

ROOT = Path(__file__).resolve().parents[2]  # backend/
SEED_DATA = ROOT / "seed_data"

PACK = [
    ("Nifty50 Bearish MACD Divergence v1", "nifty50_bearish_macd_divergence_v1.rulebook.json"),
    ("Nifty50 Bullish MACD Divergence v1", "nifty50_bullish_macd_divergence_v1.rulebook.json"),
    ("Nifty50 Bearish RSI Divergence v1", "nifty50_bearish_rsi_divergence_v1.rulebook.json"),
]


def seed_production_pattern_pack() -> list[str]:
    logs: list[str] = []
    db = SessionLocal()
    try:
        for name, fname in PACK:
            path = SEED_DATA / fname
            rulebook = json.loads(path.read_text(encoding="utf-8"))

            p = db.query(Pattern).filter_by(name=name).first()
            if p:
                p.status = "active"
                p.description = (rulebook.get("description") or p.description or "")[:500]
                db.add(p)
                db.commit()
                logs.append(f"[reactivate] {name} id={p.id}")
                continue

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
            logs.append(f"[created] {name} id={pat.id}")
    finally:
        db.close()

    return logs

