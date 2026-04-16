"""
Second-pass LLM review before a signal reaches the inbox / Telegram.

Uses chart + pattern context plus optional SearxNG / Crawl4AI snippets for a
very brief equity-research-style view (company, sector, macro).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.llm.client import reason

logger = logging.getLogger("patternos.llm.equity_review")

SYSTEM = """You are a sell-side style equity desk assistant (India NSE focus).
You receive a technical pattern signal plus optional news/web snippets.
Give a VERY brief opinion (max 120 words total) covering:
- Setup vs company/sector context
- One macro / flow risk
- Whether the pattern looks actionable for a disciplined trader

Return ONLY valid JSON (no markdown fences):
{
  "stance": "constructive" | "neutral" | "skeptical",
  "headline": "one punchy line, <= 140 chars",
  "body": "2-4 short sentences, plain text",
  "tags": ["optional", "chips", "3 max"]
}
"""


async def run_signal_equity_review(
    *,
    pattern_name: str,
    symbol: str,
    company_name: str | None,
    sector: str | None,
    index_name: str | None,
    confidence: float,
    screener_analysis: str,
    chart_summary_excerpt: str,
    search_snippets: list[dict[str, Any]],
    crawl_excerpts: list[dict[str, str]],
) -> dict[str, Any]:
    snip_lines = []
    for s in search_snippets[:10]:
        snip_lines.append(f"- {s.get('title','')[:80]} | {s.get('url','')}\n  {s.get('content','')[:220]}")
    crawl_lines = []
    for c in crawl_excerpts[:2]:
        crawl_lines.append(f"URL {c.get('url','')[:80]}\n{c.get('text','')[:1200]}")

    user = f"""Symbol: {symbol}
Company: {company_name or "unknown"}
Sector: {sector or "unknown"}
Index: {index_name or "unknown"}
Pattern: {pattern_name}
Model confidence (0-100): {confidence:.1f}
Screener line: {screener_analysis[:400]}

Chart summary (truncated):
{chart_summary_excerpt[:1800]}

News / search snippets:
{chr(10).join(snip_lines) if snip_lines else "(none — rely on sector/macro general knowledge)"}

Page extracts (if any):
{chr(10).join(crawl_lines) if crawl_lines else "(none)"}
"""

    raw = await reason(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        temperature=0.25,
        max_tokens=500,
    )
    text = re.sub(r"```json|```", "", raw).strip()
    try:
        data = json.loads(text)
    except Exception:
        logger.warning("equity review JSON parse failed, using fallback")
        data = {
            "stance": "neutral",
            "headline": "AI desk: parse error — review manually",
            "body": text[:400],
            "tags": [],
        }
    return {
        "stance": data.get("stance", "neutral"),
        "headline": (data.get("headline") or "")[:200],
        "body": (data.get("body") or "")[:1200],
        "tags": data.get("tags") if isinstance(data.get("tags"), list) else [],
    }
