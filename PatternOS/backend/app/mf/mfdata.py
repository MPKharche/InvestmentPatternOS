from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.mf.safety import RequestResult, IngestionTask


BASE = "https://mfdata.in/api/v1"


@dataclass(frozen=True)
class MfdataScheme:
    amfi_code: int
    family_id: int | None
    isin: str | None
    name: str | None
    plan_type: str | None
    option_type: str | None
    nav: float | None
    nav_date: str | None
    morningstar_sec_id: str | None
    expense_ratio: float | None
    risk_label: str | None
    aum: float | None
    min_sip: float | None
    min_lumpsum: float | None
    exit_load: str | None
    benchmark: str | None
    launch_date: str | None
    family_name: str | None
    category: str | None
    amc_name: str | None
    amc_slug: str | None
    returns: dict[str, Any] | None
    ratios: dict[str, Any] | None


def _get_data(obj: Any) -> Any:
    if isinstance(obj, dict) and obj.get("status") == "success":
        return obj.get("data")
    return None


def _request_json(url: str, *, timeout_s: float, t: IngestionTask | None, bucket: str, params: dict[str, Any] | None = None) -> Any:
    if t is not None:
        res: RequestResult = t.request(method="GET", url=url, params=params, bucket=bucket)
        return res.json
    with httpx.Client(timeout=timeout_s, follow_redirects=True) as client:
        r = client.get(url, params=params)
        r.raise_for_status()
        return r.json()


def fetch_scheme(amfi_code: int, *, timeout_s: float = 20, task: IngestionTask | None = None) -> MfdataScheme | None:
    raw = _request_json(f"{BASE}/schemes/{amfi_code}", timeout_s=timeout_s, t=task, bucket="nav")
    data = _get_data(raw)
    if not isinstance(data, dict):
        return None
    return MfdataScheme(
        amfi_code=int(data.get("amfi_code")),
        family_id=(int(data["family_id"]) if data.get("family_id") is not None else None),
        isin=(str(data.get("isin")) if data.get("isin") is not None else None),
        name=data.get("name"),
        plan_type=data.get("plan_type"),
        option_type=data.get("option_type"),
        nav=(float(data["nav"]) if data.get("nav") is not None else None),
        nav_date=data.get("nav_date"),
        morningstar_sec_id=(str(data.get("morningstar_sec_id")) if data.get("morningstar_sec_id") else None),
        expense_ratio=(float(data["expense_ratio"]) if data.get("expense_ratio") is not None else None),
        risk_label=data.get("risk_label"),
        aum=(float(data["aum"]) if data.get("aum") is not None else None),
        min_sip=(float(data["min_sip"]) if data.get("min_sip") is not None else None),
        min_lumpsum=(float(data["min_lumpsum"]) if data.get("min_lumpsum") is not None else None),
        exit_load=data.get("exit_load"),
        benchmark=data.get("benchmark"),
        launch_date=data.get("launch_date"),
        family_name=data.get("family_name"),
        category=data.get("category"),
        amc_name=data.get("amc_name"),
        amc_slug=data.get("amc_slug"),
        returns=(data.get("returns") if isinstance(data.get("returns"), dict) else None),
        ratios=(data.get("ratios") if isinstance(data.get("ratios"), dict) else None),
    )


def fetch_family_holdings(family_id: int, *, timeout_s: float = 30, task: IngestionTask | None = None, month: str | None = None) -> dict[str, Any] | None:
    params = {"month": month} if month else None
    raw = _request_json(f"{BASE}/families/{family_id}/holdings", timeout_s=timeout_s, t=task, bucket="standard", params=params)
    data = _get_data(raw)
    if not isinstance(data, dict):
        return None
    return data


def fetch_family_sectors(family_id: int, *, timeout_s: float = 20, task: IngestionTask | None = None, month: str | None = None) -> list[dict[str, Any]] | None:
    params = {"month": month} if month else None
    raw = _request_json(f"{BASE}/families/{family_id}/sectors", timeout_s=timeout_s, t=task, bucket="standard", params=params)
    data = _get_data(raw)
    if not isinstance(data, list):
        return None
    return data


def fetch_nav_history(
    amfi_code: int,
    *,
    period: str = "max",
    group_by: str = "daily",
    timeout_s: float = 30,
    task: IngestionTask | None = None,
) -> list[dict[str, Any]]:
    params = {"period": period, "group_by": group_by}
    raw = _request_json(f"{BASE}/schemes/{amfi_code}/nav/history", timeout_s=timeout_s, t=task, bucket="nav", params=params)
    data = _get_data(raw)
    if not isinstance(data, dict):
        return []
    pts = data.get("data")
    if not isinstance(pts, list):
        return []
    out: list[dict[str, Any]] = []
    for it in pts:
        if not isinstance(it, dict):
            continue
        d = it.get("date")
        nav = it.get("nav")
        if not d or nav is None:
            continue
        out.append({"date": str(d), "nav": nav})
    return out


def list_schemes(
    *,
    task: IngestionTask | None = None,
    timeout_s: float = 20,
    amc: str | None = None,
    category: str | None = None,
    plan_type: str | None = None,
    search: str | None = None,
    active_only: bool = True,
    exclude_fmp: bool = True,
    limit: int = 1000,
    offset: int = 0,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "active_only": active_only,
        "exclude_fmp": exclude_fmp,
        "limit": limit,
        "offset": offset,
    }
    if amc:
        params["amc"] = amc
    if category:
        params["category"] = category
    if plan_type:
        params["plan_type"] = plan_type
    if search:
        params["search"] = search

    raw = _request_json(f"{BASE}/schemes", timeout_s=timeout_s, t=task, bucket="standard", params=params)
    data = _get_data(raw)
    if not isinstance(data, list):
        return []
    return data
