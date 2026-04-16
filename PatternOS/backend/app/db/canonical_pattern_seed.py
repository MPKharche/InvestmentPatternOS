"""Idempotent seed of canonical Nifty 50 divergence patterns (MACD + RSI).

Used by FastAPI startup so a fresh `git clone` + launch has production patterns
without a manual script step. CLI: `python scripts/seed_production_pattern_pack.py`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Pattern, PatternVersion

_BACKEND_ROOT = Path(__file__).resolve().parents[2]

CANONICAL_DIVERGENCE_PACK: list[tuple[str, str]] = [
    ("Nifty50 Bearish MACD Divergence v1", "nifty50_bearish_macd_divergence_v1.rulebook.json"),
    ("Nifty50 Bullish MACD Divergence v1", "nifty50_bullish_macd_divergence_v1.rulebook.json"),
    ("Nifty50 Bearish RSI Divergence v1", "nifty50_bearish_rsi_divergence_v1.rulebook.json"),
]


def _upsert_pattern(db: Session, name: str, rulebook: dict[str, Any]) -> str:
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


def ensure_canonical_divergence_patterns(db: Session) -> list[str]:
    """Ensure MACD/RSI Nifty50 divergence patterns exist and are active. Idempotent."""
    lines: list[str] = []
    for name, fname in CANONICAL_DIVERGENCE_PACK:
        path = _BACKEND_ROOT / "seed_data" / fname
        rulebook = json.loads(path.read_text(encoding="utf-8"))
        lines.append(_upsert_pattern(db, name, rulebook))
    return lines
