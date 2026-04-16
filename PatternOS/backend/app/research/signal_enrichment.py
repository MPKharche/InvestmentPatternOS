"""Assemble SearxNG + Crawl4AI context and run the equity-desk LLM pass."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import Settings
from app.research.crawl_client import crawl_url_markdown
from app.research.ddg_client import ddg_related_topics
from app.research.searx_client import searx_search
from app.llm.signal_equity_review import run_signal_equity_review

logger = logging.getLogger("patternos.research.enrichment")


async def build_equity_research_note(
    settings: Settings,
    *,
    pattern_name: str,
    symbol: str,
    company_name: str | None,
    sector: str | None,
    index_name: str | None,
    confidence: float,
    screener_analysis: str,
    chart_summary: str,
) -> dict[str, Any] | None:
    if not settings.SIGNAL_DEEP_REVIEW_ENABLED:
        return None
    if not (settings.OPENROUTER_API_KEY or "").strip():
        return {
            "stance": "neutral",
            "headline": "AI desk offline",
            "body": "Set OPENROUTER_API_KEY for pre-inbox equity review.",
            "tags": [],
            "sources": [],
            "searx_used": False,
            "crawl_used": False,
        }

    sym_short = symbol.replace(".NS", "").replace(".BO", "")
    q1 = f"{sym_short} stock news India NSE"
    q2 = f"{company_name or sym_short} {sector or ''} sector outlook India 2025"

    search_snippets: list[dict[str, Any]] = []
    searx_used = False
    ddg_used = False
    if (settings.SEARXNG_BASE_URL or "").strip():
        try:
            a, b = await asyncio.gather(
                searx_search(settings.SEARXNG_BASE_URL, q1, limit=6),
                searx_search(settings.SEARXNG_BASE_URL, q2, limit=6),
            )
            seen: set[str] = set()
            for block in (a or []) + (b or []):
                u = block.get("url") or ""
                if u in seen:
                    continue
                seen.add(u)
                search_snippets.append(block)
            searx_used = bool(search_snippets)
        except Exception as e:
            logger.warning("searx gather failed: %s", e)

    if not search_snippets:
        try:
            d1 = await ddg_related_topics(q1, limit=4)
            d2 = await ddg_related_topics(q2, limit=4)
            search_snippets = (d1 or []) + (d2 or [])
            ddg_used = bool(search_snippets)
        except Exception as e:
            logger.debug("ddg fallback failed: %s", e)

    crawl_excerpts: list[dict[str, str]] = []
    crawl_used = False
    base_crawl = (settings.CRAWL4AI_BASE_URL or "").strip()
    if base_crawl and search_snippets:
        urls: list[str] = []
        for s in search_snippets:
            u = s.get("url") or ""
            if u.startswith("https://") and "google.com/search" not in u:
                urls.append(u)
            if len(urls) >= 2:
                break
        for u in urls[:2]:
            try:
                md = await crawl_url_markdown(base_crawl, u, timeout=40.0)
                if md:
                    crawl_excerpts.append({"url": u, "text": md})
                    crawl_used = True
            except Exception as e:
                logger.debug("crawl skip %s: %s", u[:60], e)

    try:
        opinion = await run_signal_equity_review(
            pattern_name=pattern_name,
            symbol=symbol,
            company_name=company_name,
            sector=sector,
            index_name=index_name,
            confidence=confidence,
            screener_analysis=screener_analysis,
            chart_summary_excerpt=chart_summary,
            search_snippets=search_snippets,
            crawl_excerpts=crawl_excerpts,
        )
    except Exception as e:
        logger.warning("equity review LLM failed: %s", e)
        opinion = {
            "stance": "neutral",
            "headline": "AI desk unavailable",
            "body": f"Review error: {e!s}"[:400],
            "tags": [],
        }

    sources = [{"title": s.get("title"), "url": s.get("url")} for s in search_snippets[:8]]
    return {
        **opinion,
        "sources": sources,
        "searx_used": searx_used,
        "ddg_used": ddg_used,
        "crawl_used": crawl_used,
    }
