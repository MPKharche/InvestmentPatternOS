from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote_plus

from app.db.models import MFScheme


@dataclass(frozen=True)
class ExternalLinks:
    valueresearch_url: str
    morningstar_url: str
    valueresearch_status: str
    morningstar_status: str


def _clean_query(s: str) -> str:
    return " ".join((s or "").strip().split())


def _slugify(s: str) -> str:
    s = (s or "").strip().lower()
    out = []
    last_dash = False
    for ch in s:
        if ch.isalnum():
            out.append(ch)
            last_dash = False
        else:
            if not last_dash:
                out.append("-")
                last_dash = True
    slug = "".join(out).strip("-")
    return slug[:120] if slug else "fund"


def generate_external_links(
    *,
    scheme_name: str | None,
    amc_name: str | None = None,
    morningstar_sec_id: str | None = None,
) -> ExternalLinks:
    """
    Generate safe, non-scraping external links.

    We intentionally prefer "search" entry points (stable + low mapping risk).
    Deep-linking to an exact scheme page requires a reliable mapping key, which
    is often not available from free sources.
    """
    q = _clean_query(scheme_name or "")
    if amc_name:
        q = _clean_query(f"{q} {amc_name}")

    qp = quote_plus(q) if q else ""

    # NOTE:
    # ValueResearch & Morningstar India deep links and even site search endpoints can be brittle (redirect/403/404).
    # For non-technical reliability, prefer Google site-search links that consistently load in a browser and
    # still take the user to the right destination site.
    vr_status = "search_google" if qp else "home"
    vr = (
        f"https://www.google.com/search?q=site%3Avalueresearchonline.com+{qp}"
        if qp
        else "https://www.valueresearchonline.com/"
    )

    ms_status = "search_google" if qp else "home"
    ms = f"https://www.google.com/search?q=site%3Amorningstar.in+{qp}" if qp else "https://www.morningstar.in/"

    return ExternalLinks(valueresearch_url=vr, morningstar_url=ms, valueresearch_status=vr_status, morningstar_status=ms_status)


def ensure_scheme_links(scheme: MFScheme) -> bool:
    """
    Ensure `scheme.valueresearch_url` and `scheme.morningstar_url` are set.
    Returns True if the scheme was modified.
    """
    # If we previously saved an unreliable deep-link or non-Google link, prefer the stable Google site-search link.
    if scheme.morningstar_url and (
        scheme.morningstar_link_status in {"deep", "search"}
        or "/mutualfunds/" in (scheme.morningstar_url or "")
        or "google.com/search" not in (scheme.morningstar_url or "")
    ):
        scheme.morningstar_url = None
        scheme.morningstar_link_status = None

    if scheme.valueresearch_url and (
        scheme.valueresearch_link_status in {"search"}
        and "google.com/search" not in (scheme.valueresearch_url or "")
    ):
        scheme.valueresearch_url = None
        scheme.valueresearch_link_status = None

    if scheme.valueresearch_url and scheme.morningstar_url:
        return False
    links = generate_external_links(
        scheme_name=scheme.scheme_name,
        amc_name=scheme.amc_name,
        morningstar_sec_id=getattr(scheme, "morningstar_sec_id", None),
    )
    changed = False
    if not scheme.valueresearch_url:
        scheme.valueresearch_url = links.valueresearch_url
        scheme.valueresearch_link_status = links.valueresearch_status
        changed = True
    if not scheme.morningstar_url:
        scheme.morningstar_url = links.morningstar_url
        scheme.morningstar_link_status = links.morningstar_status
        changed = True
    return changed
