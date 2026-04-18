from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.mf.safety import IngestionTask


MFAPI_SCHEME_URL = "https://api.mfapi.in/mf/{scheme_code}"


@dataclass(frozen=True)
class MFAPISchemeHistory:
    scheme_code: int
    scheme_name: str | None
    fund_house: str | None
    scheme_category: str | None
    scheme_type: str | None
    nav_points: list[tuple[str, float]]  # nav_date (YYYY-MM-DD), nav


def _parse_mfapi_date(s: str) -> str | None:
    s = (s or "").strip()
    if not s:
        return None
    # MFAPI commonly returns dd-mm-yyyy.
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except Exception:
            continue
    return None


def fetch_scheme_history(
    *,
    scheme_code: int,
    task: IngestionTask,
    start_date: str | None = None,
    end_date: str | None = None,
) -> MFAPISchemeHistory | None:
    """
    Fetch full NAV history for a scheme from MFAPI (single request).
    Uses safety IngestionTask (rate limiting + backoff + circuit breaker).
    """
    url = MFAPI_SCHEME_URL.format(scheme_code=scheme_code)
    params: dict[str, Any] | None = None
    if start_date and end_date:
        params = {"startDate": start_date, "endDate": end_date}
    res = task.request(method="GET", url=url, bucket="standard", max_retries=3, params=params)
    js = res.json
    if not isinstance(js, dict):
        return None

    meta = js.get("meta") or {}
    scheme_name = meta.get("scheme_name")
    fund_house = meta.get("fund_house")
    scheme_category = meta.get("scheme_category")
    scheme_type = meta.get("scheme_type")

    points: list[tuple[str, float]] = []
    data = js.get("data") or []
    if isinstance(data, list):
        for row in data:
            if not isinstance(row, dict):
                continue
            d = _parse_mfapi_date(str(row.get("date") or ""))
            nav_raw = row.get("nav")
            if not d or nav_raw is None:
                continue
            try:
                nav = float(nav_raw)
            except Exception:
                continue
            points.append((d, nav))

    return MFAPISchemeHistory(
        scheme_code=int(scheme_code),
        scheme_name=str(scheme_name) if scheme_name else None,
        fund_house=str(fund_house) if fund_house else None,
        scheme_category=str(scheme_category) if scheme_category else None,
        scheme_type=str(scheme_type) if scheme_type else None,
        nav_points=points,
    )
