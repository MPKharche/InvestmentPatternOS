"""Generate LLM pattern study from backtest results."""
from __future__ import annotations
import json
from app.llm.client import reason

STUDY_SYSTEM = """You are a quantitative trading analyst specializing in pattern recognition and backtesting.
You analyze pattern detection results and provide:
1. Why the pattern worked in successful cases
2. Why it failed in failure cases
3. Specific rulebook improvements to increase the success rate
4. Risk management insights

Be specific and data-driven. Reference actual indicator values and market conditions."""


async def generate_pattern_study(
    pattern_name: str,
    rulebook: dict,
    run_stats: dict,
    sample_events: list[dict],
) -> dict:
    """Generate LLM study analysis from backtest data."""

    prompt = f"""Pattern: {pattern_name}

Rulebook criteria: {json.dumps(rulebook.get("criteria", []), indent=2)}
Direction: {rulebook.get("direction", "unknown")}

Backtest Results:
- Symbols scanned: {run_stats.get("symbols_scanned")}
- Total events detected: {run_stats.get("events_found")}
- Success count: {run_stats.get("success_count")} ({run_stats.get("success_rate")}%)
- Failure count: {run_stats.get("failure_count")}
- Neutral count: {run_stats.get("neutral_count")}
- Avg 5d return: {run_stats.get("avg_ret_5d")}%
- Avg 10d return: {run_stats.get("avg_ret_10d")}%
- Avg 20d return: {run_stats.get("avg_ret_20d")}%
- Avg ~1m (21d) return: {run_stats.get("avg_ret_21d")}%
- Avg ~3m (63d) return: {run_stats.get("avg_ret_63d")}%
- Avg ~6m (126d) return: {run_stats.get("avg_ret_126d")}%

Sample successful events (first 5):
{json.dumps([e for e in sample_events if e.get("outcome") == "success"][:5], indent=2)}

Sample failure events (first 5):
{json.dumps([e for e in sample_events if e.get("outcome") == "failure"][:5], indent=2)}

Please analyze:
1. What makes this pattern work well (success factors)
2. What causes it to fail (failure factors)
3. Specific additional criteria to add to reduce false positives (e.g., minimum ADX value, RSI threshold, trend filter)
4. Confidence score adjustments based on indicator values
5. Risk management guidelines (stop-loss, take-profit based on ATR)

Format your response as a JSON object with keys:
- "analysis" (string): 3-4 paragraph narrative analysis
- "success_factors" (array of strings): bullet points of what makes it work
- "failure_factors" (array of strings): bullet points of why it fails
- "rulebook_suggestions" (array of objects). Each object MUST include:
  - "type" (string): e.g. filter, threshold, universe
  - "condition" (string): human-readable rule text
  - "rationale" (string): why it helps
  - "estimated_delta" (object, optional but preferred): plausible improvements vs current backtest, numeric estimates:
      "success_rate_pct" (number): expected change in success rate in percentage points (e.g. 5 means +5pp)
      "coverage_events_pct" (number): expected change in share of events kept (negative = fewer signals)
      "avg_raw_ret_1w_pct", "avg_raw_ret_1m_pct", "avg_raw_ret_3m_pct" (numbers): expected change in average raw forward returns (5d/21d/63d) in percentage points
  - "apply_patch" (object, optional): a SMALL partial rulebook JSON fragment to deep-merge if the user accepts this suggestion (e.g. {{"criteria": ["RSI > 40"]}} or {{"min_adx": 20}} — only keys you are confident exist or should be added; keep minimal)
- "confidence_improvements" (array of strings): how to adjust confidence scoring
- "risk_guidelines" (object with "stop_loss_atr_multiple", "take_profit_atr_multiple", "notes")
"""

    try:
        response = await reason(
            messages=[
                {"role": "system", "content": STUDY_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=3000,
        )
        # Strip markdown code fences if present
        text = response.strip()
        if text.startswith("```"):
            import re
            match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
            if match:
                text = match.group(1).strip()
        try:
            return json.loads(text)
        except Exception:
            return {
                "analysis": response,
                "success_factors": [],
                "failure_factors": [],
                "rulebook_suggestions": [],
                "confidence_improvements": [],
            }
    except Exception as e:
        return {
            "analysis": f"Study generation failed: {e}",
            "success_factors": [],
            "failure_factors": [],
            "rulebook_suggestions": [],
            "confidence_improvements": [],
        }
