from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, quote_plus

from app.db.models import MFScheme


@dataclass(frozen=True)
class TrustedExternalUrls:
    """Resolved outbound URLs for the three trusted sources + status labels."""

    valueresearch_url: str
    morningstar_url: str
    yahoo_finance_url: str
    valueresearch_status: str
    morningstar_status: str
    yahoo_status: str


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


def _isin_for_lookup(scheme: MFScheme) -> str | None:
    for k in (scheme.isin_growth, scheme.isin_reinvest):
        if k and str(k).strip() and str(k).strip() != "-":
            return str(k).strip().upper()
    return None


def canonical_morningstar_india_url(sec_id: str, scheme_name: str | None) -> str:
    sid = (sec_id or "").strip().lower()
    slug = _slugify(scheme_name or "fund")
    return f"https://www.morningstar.in/mutualfunds/{sid}/{slug}/overview.aspx"


def canonical_valueresearch_url(vr_fund_id: int, scheme_name: str | None) -> str:
    slug = _slugify(scheme_name or "fund")
    return f"https://www.valueresearchonline.com/funds/{int(vr_fund_id)}/{slug}/"


def canonical_yahoo_quote_url(symbol: str) -> str:
    sym = (symbol or "").strip()
    return f"https://finance.yahoo.com/quote/{quote(sym, safe='.-')}/"


def yahoo_lookup_by_isin_url(isin: str) -> str:
    return f"https://finance.yahoo.com/lookup?s={quote_plus(isin)}"


def _google_site_search(site_host: str, scheme: MFScheme) -> str:
    q = _clean_query(scheme.scheme_name or "")
    if scheme.amc_name:
        q = _clean_query(f"{q} {scheme.amc_name}")
    qp = quote_plus(q) if q else ""
    if not qp:
        return f"https://www.google.com/search?q=site%3A{site_host}"
    return f"https://www.google.com/search?q=site%3A{site_host}+{qp}"


def resolve_trusted_external_urls(scheme: MFScheme) -> TrustedExternalUrls:
    """
    Build best-effort URLs for Value Research, Morningstar India, and Yahoo Finance.

    Precedence:
    1) Stored canonical keys (VR fund id, Morningstar sec id, Yahoo symbol) → stable deep links
    2) Yahoo: ISIN → finance.yahoo.com lookup (good hit rate for Indian MFs)
    3) Google site: search as last resort (always loads; user can pick the right hit)
    """
    name = scheme.scheme_name

    # --- Morningstar ---
    ms_status = "search_google"
    ms_url = _google_site_search("morningstar.in", scheme)
    if scheme.morningstar_sec_id and str(scheme.morningstar_sec_id).strip():
        ms_url = canonical_morningstar_india_url(str(scheme.morningstar_sec_id), name)
        ms_status = "deep"
    elif scheme.morningstar_url and "morningstar.in/mutualfunds/" in (scheme.morningstar_url or ""):
        ms_url = scheme.morningstar_url
        ms_status = "manual"

    # --- Value Research ---
    vr_status = "search_google"
    vr_url = _google_site_search("valueresearchonline.com", scheme)
    vid = getattr(scheme, "value_research_fund_id", None)
    if vid is not None and int(vid) > 0:
        vr_url = canonical_valueresearch_url(int(vid), name)
        vr_status = "deep"
    elif scheme.valueresearch_url and "valueresearchonline.com/funds/" in (scheme.valueresearch_url or ""):
        vr_url = scheme.valueresearch_url
        vr_status = "manual"

    # --- Yahoo Finance ---
    y_status = "search_google"
    y_url = _google_site_search("finance.yahoo.com", scheme)
    ysym = getattr(scheme, "yahoo_finance_symbol", None)
    if ysym and str(ysym).strip():
        y_url = canonical_yahoo_quote_url(str(ysym))
        y_status = "quote"
    elif scheme.yahoo_finance_url and "finance.yahoo.com/quote/" in (scheme.yahoo_finance_url or ""):
        y_url = scheme.yahoo_finance_url
        y_status = "manual"
    else:
        isin = _isin_for_lookup(scheme)
        if isin:
            y_url = yahoo_lookup_by_isin_url(isin)
            y_status = "lookup_isin"

    return TrustedExternalUrls(
        valueresearch_url=vr_url,
        morningstar_url=ms_url,
        yahoo_finance_url=y_url,
        valueresearch_status=vr_status,
        morningstar_status=ms_status,
        yahoo_status=y_status,
    )


def ensure_scheme_links(scheme: MFScheme) -> bool:
    """
    Refresh outbound URLs from canonical rules (IDs / ISIN) and write link_status fields.

    Manual overrides: if `valueresearch_url` / `morningstar_url` / `yahoo_finance_url` were hand-edited
    to a full https URL, we only overwrite when the corresponding id/symbol field is set (so edits stick
    until an id is supplied — then canonical wins). For simplicity we always recompute from ids;
    hand-edited URLs should go into the id fields via PATCH, or we overwrite each run.

    Policy: always assign computed URLs so list views stay consistent after enrichment.
    """
    t = resolve_trusted_external_urls(scheme)
    changed = False

    if scheme.valueresearch_url != t.valueresearch_url:
        scheme.valueresearch_url = t.valueresearch_url
        scheme.valueresearch_link_status = t.valueresearch_status
        changed = True

    if scheme.morningstar_url != t.morningstar_url:
        scheme.morningstar_url = t.morningstar_url
        scheme.morningstar_link_status = t.morningstar_status
        changed = True

    if scheme.yahoo_finance_url != t.yahoo_finance_url:
        scheme.yahoo_finance_url = t.yahoo_finance_url
        changed = True
    if getattr(scheme, "yahoo_link_status", None) != t.yahoo_status:
        scheme.yahoo_link_status = t.yahoo_status
        changed = True

    return changed
