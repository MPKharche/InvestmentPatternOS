from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import httpx

from app.config import get_settings
from app.db.models import MFScheme
from app.mf.safety import get_limiter, provider_is_paused, record_provider_failure, record_provider_success


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

settings = get_settings()

_MS_SEC_ID_RE = re.compile(r"/mutualfunds/([a-z0-9]{6,})/", re.IGNORECASE)
_MS_SLUG_RE = re.compile(r"/mutualfunds/[a-z0-9]{6,}/([^/]+)/", re.IGNORECASE)


def extract_morningstar_sec_id(url: str | None) -> str | None:
    """
    Extract Morningstar security id from a Morningstar URL, e.g.
    https://morningstar.in/mutualfunds/f00000pfli/.../fund-factsheet.aspx
    -> F00000PFLI
    """
    if not url:
        return None
    m = _MS_SEC_ID_RE.search(url)
    if not m:
        return None
    return m.group(1).strip().upper()


def extract_morningstar_slug(url: str | None) -> str | None:
    if not url:
        return None
    m = _MS_SLUG_RE.search(url)
    if not m:
        return None
    slug = _slugify(m.group(1))
    return slug or None


def morningstar_search_url(*, scheme_name: str | None, amc_name: str | None = None) -> str:
    q = _clean_query(scheme_name or "")
    if amc_name:
        q = _clean_query(f"{q} {amc_name}")
    qp = quote_plus(q) if q else ""
    return f"https://www.google.com/search?q=site%3Amorningstar.in+{qp}" if qp else "https://www.morningstar.in/"


def morningstar_factsheet_url(*, sec_id: str, scheme_name: str | None = None, slug: str | None = None) -> str:
    sec = (sec_id or "").strip().upper()
    if not sec:
        return "https://www.morningstar.in/"
    # Morningstar appears to accept arbitrary slugs as long as the security id is correct.
    # Use a stable constant slug to avoid mismatches between our scheme name and Morningstar's slug.
    use_slug = slug or "fund"
    # Morningstar URLs commonly use lowercase ids; keep that for consistency.
    return f"https://www.morningstar.in/mutualfunds/{sec.lower()}/{use_slug}/fund-factsheet.aspx"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _deep_link_recently_failed(s: MFScheme, *, cooldown_hours: int = 24) -> bool:
    if not s.links_last_checked_at or not s.links_last_check_status:
        return False
    if int(s.links_last_check_status) < 400:
        return False
    age = _now_utc() - s.links_last_checked_at
    return age < timedelta(hours=int(cooldown_hours))


def generate_external_links(
    *,
    scheme_name: str | None,
    amc_name: str | None = None,
    morningstar_sec_id: str | None = None,
) -> ExternalLinks:
    """
    Generate safe, non-scraping external links.

    Default behavior prefers "search" entry points (stable + low mapping risk).
    If a reliable mapping key is available (Morningstar security id), we prefer
    a direct Factsheet deep-link.
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

    if morningstar_sec_id:
        ms_status = "deep_factsheet"
        ms = morningstar_factsheet_url(sec_id=morningstar_sec_id, scheme_name=scheme_name)
    else:
        ms_status = "search_google" if qp else "home"
        ms = morningstar_search_url(scheme_name=scheme_name, amc_name=amc_name)

    return ExternalLinks(valueresearch_url=vr, morningstar_url=ms, valueresearch_status=vr_status, morningstar_status=ms_status)


def ensure_scheme_links(scheme: MFScheme) -> bool:
    """
    Ensure `scheme.valueresearch_url` and `scheme.morningstar_url` are set.
    Returns True if the scheme was modified.
    """
    if scheme.valueresearch_url and (
        scheme.valueresearch_link_status in {"search"}
        and "google.com/search" not in (scheme.valueresearch_url or "")
    ):
        scheme.valueresearch_url = None
        scheme.valueresearch_link_status = None

    changed = False

    # Prefer Morningstar Factsheet deep-link when we have a stable mapping key.
    sec_id = getattr(scheme, "morningstar_sec_id", None)
    if sec_id:
        norm = str(sec_id).strip().upper()
        if norm and norm != sec_id:
            scheme.morningstar_sec_id = norm
            sec_id = norm
            changed = True
    if sec_id and not _deep_link_recently_failed(scheme):
        want = morningstar_factsheet_url(sec_id=sec_id, scheme_name=scheme.scheme_name)
        if scheme.morningstar_url != want or scheme.morningstar_link_status != "deep_factsheet":
            scheme.morningstar_url = want
            scheme.morningstar_link_status = "deep_factsheet"
            changed = True

    if scheme.valueresearch_url and scheme.morningstar_url:
        return changed
    links = generate_external_links(
        scheme_name=scheme.scheme_name,
        amc_name=scheme.amc_name,
        morningstar_sec_id=sec_id,
    )
    if not scheme.valueresearch_url:
        scheme.valueresearch_url = links.valueresearch_url
        scheme.valueresearch_link_status = links.valueresearch_status
        changed = True
    if not scheme.morningstar_url:
        scheme.morningstar_url = links.morningstar_url
        scheme.morningstar_link_status = links.morningstar_status
        changed = True
    return changed


def validate_morningstar_factsheet_link(db, scheme: MFScheme, *, force: bool = False) -> bool:
    """
    Best-effort, single-attempt validation of the generated Morningstar Factsheet link.
    - On success (200-399): keeps deep link.
    - On definitive not-found (404/410): falls back to search link.
    - On soft failures (403/429/5xx/timeout): keep deep link (Morningstar often blocks botty checks
      even when the link works fine in a normal browser).

    Returns True if scheme was modified.
    """
    if not settings.MF_LINK_CHECK_ENABLED:
        return False
    if not scheme.morningstar_sec_id:
        return False
    if provider_is_paused(db, "morningstar"):
        return False

    if not force and scheme.links_last_checked_at and (_now_utc() - scheme.links_last_checked_at) < timedelta(hours=24):
        return False

    deep = morningstar_factsheet_url(sec_id=scheme.morningstar_sec_id, scheme_name=scheme.scheme_name)
    limiter = get_limiter("morningstar", "standard")
    limiter.wait()

    timeout = httpx.Timeout(
        connect=settings.MF_HTTP_CONNECT_TIMEOUT_S,
        read=min(10.0, settings.MF_HTTP_READ_TIMEOUT_S),
        write=min(10.0, settings.MF_HTTP_READ_TIMEOUT_S),
        pool=min(10.0, settings.MF_HTTP_READ_TIMEOUT_S),
    )
    client = httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": settings.MF_HTTP_USER_AGENT},
    )
    status: int | None = None
    try:
        r = client.head(deep)
        status = int(r.status_code)
        # Some sites block HEAD; retry with GET when HEAD isn't allowed.
        if status in {403, 405}:
            r2 = client.get(deep)
            status = int(r2.status_code)
    except Exception as e:
        record_provider_failure(db, "morningstar", str(e))
        status = None
    finally:
        client.close()

    scheme.links_last_checked_at = _now_utc()
    scheme.links_last_check_status = int(status) if status is not None else 0

    if status is not None and 200 <= status < 400:
        record_provider_success(db, "morningstar")
        if scheme.morningstar_url != deep or scheme.morningstar_link_status != "deep_factsheet":
            scheme.morningstar_url = deep
            scheme.morningstar_link_status = "deep_factsheet"
        return True

    if status is not None and status in {404, 410}:
        record_provider_failure(db, "morningstar", f"HTTP {status} for {deep}")
        scheme.morningstar_url = morningstar_search_url(scheme_name=scheme.scheme_name, amc_name=scheme.amc_name)
        scheme.morningstar_link_status = "search_google"
        return True

    # Soft failures (or unknown): keep deep link to avoid degrading UX.
    if status is not None and status in {403, 429, 500, 502, 503, 504}:
        record_provider_failure(db, "morningstar", f"HTTP {status} for {deep}")
    return False
