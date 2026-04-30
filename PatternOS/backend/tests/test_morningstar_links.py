from __future__ import annotations

from datetime import datetime, timezone

import app.mf.links as links


class _Scheme:
    def __init__(self):
        self.scheme_name = "ICICI Prudential Dynamic Asset Allocation Active FOF Direct Plan Growth"
        self.amc_name = "ICICI Prudential"
        self.morningstar_sec_id = None
        self.morningstar_url = None
        self.morningstar_link_status = None
        self.valueresearch_url = None
        self.valueresearch_link_status = None
        self.links_last_checked_at = None
        self.links_last_check_status = None


def test_extract_morningstar_sec_id_from_url():
    url = "https://morningstar.in/mutualfunds/f00000pfli/icici-pru/fund-factsheet.aspx"
    assert links.extract_morningstar_sec_id(url) == "F00000PFLI"


def test_extract_morningstar_slug_from_url():
    url = "https://www.morningstar.in/mutualfunds/f00000pfli/ICICI-Prudential-Dynamic-Asset/fund-factsheet.aspx"
    assert links.extract_morningstar_slug(url) == "icici-prudential-dynamic-asset"


def test_generate_external_links_prefers_deep_when_sec_id_present():
    out = links.generate_external_links(
        scheme_name="Foo Fund",
        amc_name="Bar AMC",
        morningstar_sec_id="F00000PFLI",
    )
    assert out.morningstar_status == "deep_factsheet"
    assert "morningstar.in/mutualfunds/f00000pfli/" in out.morningstar_url
    assert out.morningstar_url.endswith("/fund-factsheet.aspx")


def test_ensure_scheme_links_sets_deep_for_sec_id():
    s = _Scheme()
    s.morningstar_sec_id = "F00000PFLI"
    changed = links.ensure_scheme_links(s)
    assert changed is True
    assert s.morningstar_link_status == "deep_factsheet"
    assert "morningstar.in/mutualfunds/f00000pfli/" in (s.morningstar_url or "")


def test_ensure_scheme_links_respects_recent_validation_failure():
    s = _Scheme()
    s.morningstar_sec_id = "F00000PFLI"
    s.morningstar_url = "https://www.google.com/search?q=site%3Amorningstar.in+foo"
    s.morningstar_link_status = "search_google"
    s.links_last_check_status = 404
    s.links_last_checked_at = datetime.now(timezone.utc)
    links.ensure_scheme_links(s)
    # Do not overwrite search with deep again during cooldown window (VR link may still be filled).
    assert s.morningstar_link_status == "search_google"


def test_validate_morningstar_factsheet_link_falls_back_on_404(monkeypatch):
    s = _Scheme()
    s.morningstar_sec_id = "F00000PFLI"

    monkeypatch.setattr(links.settings, "MF_LINK_CHECK_ENABLED", True)
    monkeypatch.setattr(links, "provider_is_paused", lambda _db, _prov: False)
    monkeypatch.setattr(links, "get_limiter", lambda _prov, _bucket: type("L", (), {"wait": lambda self: 0.0})())
    monkeypatch.setattr(links, "record_provider_failure", lambda _db, _prov, _err: None)
    monkeypatch.setattr(links, "record_provider_success", lambda _db, _prov: None)

    class _Resp:
        def __init__(self, status_code: int):
            self.status_code = status_code

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def head(self, _url):
            return _Resp(404)

        def get(self, _url):
            return _Resp(404)

        def close(self):
            return None

    monkeypatch.setattr(links.httpx, "Client", _Client)

    changed = links.validate_morningstar_factsheet_link(db=None, scheme=s, force=True)
    assert changed is True
    assert s.morningstar_link_status == "search_google"
    assert "google.com/search" in (s.morningstar_url or "")


def test_validate_morningstar_factsheet_link_keeps_deep_on_redirect(monkeypatch):
    s = _Scheme()
    s.morningstar_sec_id = "F00000PFLI"

    monkeypatch.setattr(links.settings, "MF_LINK_CHECK_ENABLED", True)
    monkeypatch.setattr(links, "provider_is_paused", lambda _db, _prov: False)
    monkeypatch.setattr(links, "get_limiter", lambda _prov, _bucket: type("L", (), {"wait": lambda self: 0.0})())
    monkeypatch.setattr(links, "record_provider_failure", lambda _db, _prov, _err: None)
    monkeypatch.setattr(links, "record_provider_success", lambda _db, _prov: None)

    class _Resp:
        def __init__(self, status_code: int):
            self.status_code = status_code

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def head(self, _url):
            return _Resp(301)

        def get(self, _url):
            return _Resp(200)

        def close(self):
            return None

    monkeypatch.setattr(links.httpx, "Client", _Client)

    changed = links.validate_morningstar_factsheet_link(db=None, scheme=s, force=True)
    assert changed is True
    assert s.morningstar_link_status == "deep_factsheet"
    assert (s.morningstar_url or "").endswith("/fund-factsheet.aspx")
