from __future__ import annotations

from app.mf.mfapi import _parse_mfapi_date


def test_parse_mfapi_date_formats():
    assert _parse_mfapi_date("17-04-2026") == "2026-04-17"
    assert _parse_mfapi_date("17/04/2026") == "2026-04-17"
    assert _parse_mfapi_date("2026-04-17") == "2026-04-17"
    assert _parse_mfapi_date("") is None

