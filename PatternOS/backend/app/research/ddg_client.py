"""DuckDuckGo Instant Answer API — lightweight fallback when SearxNG is unavailable."""
from __future__ import annotations

import logging
from urllib.parse import quote_plus

import httpx

logger = logging.getLogger("patternos.research.ddg")


async def ddg_related_topics(query: str, *, limit: int = 6, timeout: float = 12.0) -> list[dict]:
    """Returns {title, url, content} shaped like Searx snippets."""
    url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1"
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "PatternOS/1.0"})
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.debug("DDG instant answer failed: %s", e)
        return []

    out: list[dict] = []
    for it in (data.get("RelatedTopics") or [])[:limit]:
        if isinstance(it, dict) and "Text" in it:
            t = it.get("FirstURL") or ""
            out.append(
                {
                    "title": (it.get("Text") or "")[:160],
                    "url": t,
                    "content": (it.get("Text") or "")[:400],
                }
            )
        elif isinstance(it, dict) and "Topics" in it:
            for sub in (it.get("Topics") or [])[:3]:
                if isinstance(sub, dict) and sub.get("Text"):
                    out.append(
                        {
                            "title": (sub.get("Text") or "")[:160],
                            "url": sub.get("FirstURL") or "",
                            "content": (sub.get("Text") or "")[:400],
                        }
                    )
    return [x for x in out if x.get("url", "").startswith("http")]
