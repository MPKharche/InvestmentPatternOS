#!/usr/bin/env python3
"""
Remove dummy / test patterns; keep the canonical Nifty50 bearish MACD divergence pattern.

- Keeps: pattern named exactly `Nifty50 Bearish MACD Divergence v1` (seed name).
- Deletes all other patterns after removing blocking rows (signals, candidate links).
- Sets the kept pattern to status `active` so daily scheduler + POST /scanner/run (no pattern_id)
  continue tracking all active patterns (currently only this one).

Run from backend/:
  python scripts/cleanup_patterns_keep_production_divergence.py

If the kept pattern is missing, run first:
  python scripts/seed_nifty50_bearish_macd_divergence.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.db.models import Pattern, PatternCandidate, Signal  # noqa: E402

KEEP_NAME = "Nifty50 Bearish MACD Divergence v1"


def _unlink_candidates(db: Session, pattern_id: str) -> int:
    n = (
        db.query(PatternCandidate)
        .filter(PatternCandidate.linked_pattern_id == pattern_id)
        .update({PatternCandidate.linked_pattern_id: None}, synchronize_session=False)
    )
    return int(n or 0)


def _delete_signals_for_pattern(db: Session, pattern_id: str) -> int:
    return db.query(Signal).filter(Signal.pattern_id == pattern_id).delete(synchronize_session=False)


def main() -> None:
    db = SessionLocal()
    try:
        keep = db.query(Pattern).filter(Pattern.name == KEEP_NAME).first()
        if not keep:
            print(f"[error] No pattern named {KEEP_NAME!r}. Run scripts/seed_nifty50_bearish_macd_divergence.py first.")
            sys.exit(1)

        all_rows = db.query(Pattern).all()
        remove_ids = [p.id for p in all_rows if p.id != keep.id]

        if not remove_ids:
            print(f"[ok] Only production pattern present ({KEEP_NAME}). id={keep.id}")
        else:
            for pid in remove_ids:
                cu = _unlink_candidates(db, pid)
                if cu:
                    print(f"  unlinked {cu} candidate(s) from pattern {pid}")
                ns = _delete_signals_for_pattern(db, pid)
                if ns:
                    print(f"  deleted {ns} signal(s) for pattern {pid}")
                row = db.query(Pattern).filter(Pattern.id == pid).first()
                if row:
                    db.delete(row)
                    print(f"  deleted pattern {pid} ({row.name!r})")
            db.commit()

        keep = db.query(Pattern).filter(Pattern.id == keep.id).first()
        if keep and keep.status != "active":
            keep.status = "active"
            db.add(keep)
            db.commit()
            print(f"[ok] Set {KEEP_NAME!r} to status=active")
        else:
            print(f"[ok] {KEEP_NAME!r} already active. id={keep.id}")

        remaining = db.query(Pattern).all()
        print(f"[done] patterns remaining: {len(remaining)} — {[p.name for p in remaining]}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
