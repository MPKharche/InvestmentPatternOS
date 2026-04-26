"""Unit tests for MF trusted external URL resolution."""

from __future__ import annotations

from app.db.models import MFScheme
from app.mf.links import (
    canonical_morningstar_india_url,
    canonical_valueresearch_url,
    canonical_yahoo_quote_url,
    resolve_trusted_external_urls,
)


def test_canonical_morningstar_india_url_slugifies_name():
    url = canonical_morningstar_india_url("0P000123", "ICICI Prudential Fund — Growth")
    assert "0p000123" in url
    assert "morningstar.in/mutualfunds/" in url
    assert "overview.aspx" in url


def test_resolve_trusted_external_urls_deep_links_when_ids_present():
    s = MFScheme(
        scheme_code=1,
        scheme_name="Test Fund Direct Growth",
        amc_name="Test AMC",
        morningstar_sec_id="0P0000TEST",
        value_research_fund_id=12345,
        yahoo_finance_symbol="TESTFUND.BO",
    )
    t = resolve_trusted_external_urls(s)
    assert t.morningstar_status == "deep"
    assert "morningstar.in/mutualfunds/0p0000test" in t.morningstar_url.lower()
    assert t.valueresearch_status == "deep"
    assert "/funds/12345/" in t.valueresearch_url
    assert t.yahoo_status == "quote"
    assert "finance.yahoo.com/quote/" in t.yahoo_finance_url


def test_resolve_trusted_external_urls_yahoo_falls_back_to_isin_lookup():
    s = MFScheme(scheme_code=999001, scheme_name="Some MF", amc_name="Some AMC")
    s.morningstar_sec_id = None
    s.morningstar_url = None
    s.value_research_fund_id = None
    s.valueresearch_url = None
    s.yahoo_finance_symbol = None
    s.yahoo_finance_url = None
    s.isin_growth = "INE000A1TEST1"
    s.isin_reinvest = None
    t = resolve_trusted_external_urls(s)
    assert t.yahoo_status == "lookup_isin"
    assert "finance.yahoo.com" in t.yahoo_finance_url


def test_canonical_yahoo_quote_url_encodes_symbol():
    u = canonical_yahoo_quote_url("FOO.BO")
    assert "finance.yahoo.com" in u
    assert "FOO.BO" in u or "FOO" in u
