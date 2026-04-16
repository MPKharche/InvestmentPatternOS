"""Crawl4AI Docker HTTP API — markdown extract for a single URL."""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("patternos.research.crawl4ai")


def _extract_markdown(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for k in ("markdown", "md", "extracted_content", "text", "content"):
            v = payload.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()[:8000]
        res = payload.get("results")
        if isinstance(res, list) and res:
            first = res[0]
            if isinstance(first, dict):
                for k in ("markdown", "extracted_content", "html"):
                    v = first.get(k)
                    if isinstance(v, str) and v.strip():
                        return v.strip()[:8000]
    return None


async def crawl_url_markdown(base_url: str, target_url: str, *, timeout: float = 35.0) -> str | None:
    base = (base_url or "").strip().rstrip("/")
    if not base or not target_url.startswith("http"):
        return None
    body = {"urls": [target_url]}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            r = await client.post(
                f"{base}/crawl",
                json=body,
                headers={"User-Agent": "PatternOS/1.0", "Content-Type": "application/json"},
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning("Crawl4AI crawl failed for %s: %s", target_url[:80], e)
        return None

    if isinstance(data, list) and data:
        md = _extract_markdown(data[0])
        if md:
            return md
    md = _extract_markdown(data)
    return md
