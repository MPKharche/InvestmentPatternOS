"""
Seed a deterministic minimal dataset for standard test runs.

This is intentionally small and offline-friendly.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.db.session import SessionLocal
from app.db.models import MFScheme, MFNavDaily, Universe


def main() -> None:
    db = SessionLocal()
    try:
        # Universe: minimal symbols used in demos/tests
        if db.query(Universe).count() == 0:
            for sym, name, idx in [
                ("AXISBANK.NS", "Axis Bank", "Nifty 50"),
                ("RELIANCE.NS", "Reliance Industries", "Nifty 50"),
            ]:
                db.add(
                    Universe(
                        symbol=sym,
                        exchange="NSE",
                        asset_class="equity",
                        name=name,
                        active=True,
                        index_name=idx,
                        sector="Banking" if "BANK" in sym else "Conglomerate",
                    )
                )

        # MF scheme + NAV series (simple ramp) for charts/metrics in E2E.
        code = 135106
        s = db.query(MFScheme).filter_by(scheme_code=code).first()
        if not s:
            s = MFScheme(
                scheme_code=code,
                scheme_name="StdTest Equity Fund - Direct Growth",
                amc_name="StdTest AMC",
                category="Equity",
                plan_type="direct",
                option_type="growth",
                monitored=True,
            )
            db.add(s)

        # Seed 400 daily NAV points ending today-1 (avoid "future" confusion).
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=500)
        nav = 10.0
        d = start
        while d <= end:
            # Only add if missing (idempotent).
            exists = db.query(MFNavDaily).filter_by(scheme_code=code, nav_date=d).first()
            if not exists:
                db.add(MFNavDaily(scheme_code=code, nav_date=d, nav=nav, source="seed_stdtest"))
            nav += 0.01
            d += timedelta(days=1)

        db.commit()
        print("[stdtest_seed] OK")
    finally:
        db.close()


if __name__ == "__main__":
    main()

