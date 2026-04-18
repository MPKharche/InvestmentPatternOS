from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable


@dataclass(frozen=True)
class AmfiNavRow:
    scheme_code: int
    isin_growth: str | None
    isin_reinvest: str | None
    scheme_name: str
    nav: float
    nav_date: date


def _parse_date(s: str) -> date:
    # Example: "16-Apr-2026"
    return datetime.strptime(s.strip(), "%d-%b-%Y").date()


def parse_navall(lines: Iterable[str]) -> list[AmfiNavRow]:
    """
    Parse AMFI NAVAll.txt.

    We accept both:
      code;isin1;isin2;name;nav;date
      code;isin1;isin2;name;nav;repurchase;sale;date

    Header/blank/category lines are skipped.
    """
    rows: list[AmfiNavRow] = []
    for raw in lines:
        line = raw.strip().strip("\ufeff")
        if not line:
            continue
        if line.lower().startswith("scheme code;"):
            continue
        # Category/AMC headings have no semicolons or start with known markers.
        if ";" not in line:
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) not in (6, 8):
            continue
        # Some headings include semicolons but non-numeric scheme code.
        try:
            code = int(parts[0])
        except Exception:
            continue

        isin_growth = parts[1] or None
        isin_reinvest = parts[2] or None
        name = parts[3] or ""
        nav_str = parts[4]
        date_str = parts[5] if len(parts) == 6 else parts[7]
        try:
            nav = float(nav_str)
        except Exception:
            continue
        try:
            d = _parse_date(date_str)
        except Exception:
            continue

        rows.append(
            AmfiNavRow(
                scheme_code=code,
                isin_growth=isin_growth if isin_growth != "-" else None,
                isin_reinvest=isin_reinvest if isin_reinvest != "-" else None,
                scheme_name=name,
                nav=nav,
                nav_date=d,
            )
        )
    return rows

