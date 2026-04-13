"""
LLM Screener — used inside the scanner loop.

Routing:
  llm_screen()       → screen() → Gemini 2.5 Flash  (fast, called per symbol)
  llm_audit_pattern()→ reason() → Claude Haiku 4.5  (deep analysis, on-demand)
"""
import json
import re
from app.llm.client import screen, reason

SCREENER_PROMPT = """You are a chart pattern screener assistant.
You will receive:
- A pattern name and its rules
- A stock symbol and a summary of its recent price action
- A base confidence score computed by rule matching

Your job: adjust the confidence score based on context (broader trend, volume quality, sector, news sensitivity) and provide a one-line analysis.

Respond ONLY in this JSON format (no other text):
{"adjusted_score": 72, "analysis": "Strong volume confirmation on breakout, but broader market in correction — moderate confidence."}

Score range: 0-100. Be conservative. Only push above 80 for very clean setups."""


async def llm_screen(
    pattern_name: str,
    rulebook_json: dict,
    symbol: str,
    chart_summary: str,
    base_score: float,
) -> tuple[float, str]:
    """
    Returns (adjusted_score, analysis_text).
    Falls back to base_score if LLM call fails.
    OPTIMIZED: Reduced token size to keep cost <$0.0001 per call
    """
    # Extract only key conditions (max 200 tokens instead of 400)
    conditions = rulebook_json.get('conditions', {})
    if isinstance(conditions, dict):
        # Compact condition summary
        cond_summary = ", ".join([str(k) for k in list(conditions.keys())[:5]])
    else:
        cond_summary = str(conditions)[:150]

    user_content = f"""Pattern: {pattern_name}
Conditions: {cond_summary}
{symbol}: {chart_summary}
Base score: {base_score:.0f}/100

Adjust score (0-100) and brief analysis."""

    try:
        reply = await screen(
            [
                {"role": "system", "content": SCREENER_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
            max_tokens=100,  # Reduced from 150
        )
        # Strip markdown if present
        clean = re.sub(r"```json|```", "", reply).strip()
        data = json.loads(clean)
        return float(data["adjusted_score"]), data.get("analysis", "")
    except Exception:
        return base_score, "LLM screening unavailable — using base score."


async def llm_audit_pattern(pattern_name: str, outcomes_summary: str) -> str:
    """
    Pattern audit: reads outcome history, returns insight text for learning log.
    Uses Claude Haiku (reasoning model) — deep structured analysis.
    """
    messages = [
        {
            "role": "system",
            "content": (
                "You are a trading pattern analyst. Analyze the outcome history of a pattern "
                "and provide specific, actionable rulebook improvement suggestions. "
                "Be concise — max 5 bullet points."
            ),
        },
        {
            "role": "user",
            "content": f"Pattern: {pattern_name}\n\nOutcome history:\n{outcomes_summary}",
        },
    ]
    return await reason(messages, temperature=0.3, max_tokens=600)
