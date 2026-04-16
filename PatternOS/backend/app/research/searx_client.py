"""SearxNG JSON API — news / web snippets for equity context."""
from __future__ import annotations

import logging
from urllib.parse import quote_plus

import httpx

logger = logging.getLogger("patternos.research.searx")


async def searx_search(base_url: str, query: str, *, limit: int = 8, timeout: float = 14.0) -> list[dict]:
    """
    Returns list of {title, url, content} from SearxNG format=json.
    base_url example: http://127.0.0.1:8888 (no trailing slash required).
    """
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return []
    url = f"{base}/search?q={quote_plus(query)}&format=json"
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "PatternOS/1.0 (signal-enrichment)"})
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning("SearxNG search failed: %s", e)
        return []

    out: list[dict] = []
    for it in (data.get("results") or [])[:limit]:
        title = (it.get("title") or "")[:200]
        u = it.get("url") or ""
        content = (it.get("content") or it.get("snippet") or "")[:500]
        if u.startswith("http"):
            out.append({"title": title, "url": u, "content": content})
    return out
