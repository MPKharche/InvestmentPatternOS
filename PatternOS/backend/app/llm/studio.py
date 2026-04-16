"""
Pattern Studio LLM logic — split routing with vision support.

  chat()    → Grok 4.1 Fast (primary) / DeepSeek V3.2 (fallback)
    All conversational turns: greeting, clarifying questions, file/chart analysis.
    Supports multimodal content (images, extracted PDF text, Word docs).

  reason()  → Grok 4.1 Fast (primary) / DeepSeek V3.2 (fallback)
    Only fires when ready to extract a structured JSON rulebook.
"""
import json
import re
from typing import Any
from app.llm.client import chat, reason

# ─── Prompts ──────────────────────────────────────────────────────────────────

CHAT_SYSTEM = """You are PatternOS Pattern Architect — a sharp, concise expert in technical chart analysis.

Your role: help traders define a precise chart pattern for automated scanning.

When a user uploads a chart image or document:
- Critically examine it: identify the pattern type, price structure, volume behavior, key levels
- State your findings clearly and confidently — what you see, what it implies, what is unclear
- Raise any concerns or ambiguities (false signals, unclear pivots, conflicting signals)
- Form a hypothesis about the pattern and discuss it with the user

Momentum / divergence setups (e.g. MACD vs price, RSI vs price):
- Default MACD is 12,26,9 unless the user specifies otherwise.
- You do NOT need exact calendar dates for pivots — the scanner finds swing highs/lows in price and compares MACD at those bars.
- Ask at most ONE clarifying question if direction (bearish vs bullish divergence) is ambiguous; otherwise finalize.
- Do not loop on "confirm exact dates/prices" — that blocks the user; the system is approximate by design.

For classical breakout / consolidation patterns, you may still ask about prior trend, range, volume, and triggers (max 2 questions at a time).

Keep responses direct and practical. No emojis. No markdown headers.

When you have gathered enough information to define the pattern precisely, end your reply with exactly:
[READY_TO_FINALIZE]

Do NOT output JSON yourself. Just have the conversation and signal when ready."""


EXTRACT_SYSTEM = """You are a technical pattern rule extractor.

Given a conversation about a chart pattern (including any chart analysis from uploaded images),
output ONLY a well-constructed JSON rulebook. No explanation. No preamble. Just the JSON.

---

If the pattern is MACD (or RSI) **divergence** — price swings vs indicator swings — use THIS shape (this is what the scanner and backtest execute):

```json
{
  "finalized": true,
  "pattern_type": "macd_divergence",
  "description": "one line: e.g. bearish MACD divergence — price higher high, MACD lower high",
  "direction": "bearish",
  "timeframes": ["1d"],
  "criteria": ["macd_divergence_bearish"],
  "conditions": {
    "divergence_types": { "bearish": { "macd": "12,26,9" } },
    "trend": { "prior_trend": "bullish", "lookback_bars": 60, "min_move_pct": 8 },
    "histogram_crossover": { "required": false }
  },
  "divergence": {
    "lookback_bars": 65,
    "swing_order": 5,
    "min_swing_separation": 8
  },
  "confidence_weights": {
    "trend_alignment": 20,
    "momentum": 30,
    "pattern_tightness": 10,
    "volume_confirmation": 10,
    "breakout_quality": 10
  },
  "notes": "Scanner uses aligned swing highs/lows on price vs MACD at those bars; default MACD 12,26,9."
}
```

For **bullish** MACD divergence set direction to "bullish", criteria to ["macd_divergence_bullish"], and divergence_types.bullish.

---

For **non-divergence** patterns (flags, ranges, breakouts), use this structure instead:

```json
{
  "finalized": true,
  "pattern_type": "snake_case_name",
  "description": "precise one-line description",
  "timeframes": ["1d"],
  "conditions": {
    "trend": {
      "prior_trend": "bullish|bearish|any",
      "lookback_bars": 20,
      "min_move_pct": 15
    },
    "pattern_body": {
      "consolidation_bars_min": 5,
      "consolidation_bars_max": 30,
      "price_range_pct_max": 8
    },
    "volume": {
      "volume_dry_up": true,
      "volume_dry_up_pct": 40,
      "breakout_volume_multiplier": 1.5
    },
    "breakout": {
      "price_above_resistance": true,
      "resistance_lookback_bars": 20,
      "close_above": true
    },
    "indicators": {}
  },
  "confidence_weights": {
    "trend_alignment": 25,
    "volume_confirmation": 25,
    "pattern_tightness": 25,
    "breakout_quality": 25
  },
  "key_levels": {
    "entry": "breakout_close",
    "stop_loss": "pattern_low",
    "target": "measured_move"
  },
  "notes": "any important caveats or conditions from the conversation"
}
```

Use `trend_alignment` (not trend_strength) in confidence_weights. Pick ONE primary template — divergence OR breakout — matching the conversation."""


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _is_ready_to_finalize(reply: str) -> bool:
    return "[READY_TO_FINALIZE]" in reply


def _clean_reply(reply: str) -> str:
    return reply.replace("[READY_TO_FINALIZE]", "").strip()


def _extract_json(text: str) -> dict | None:
    match = re.search(r"```json\s*([\s\S]+?)\s*```", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None


def _normalize_rulebook(rb: dict) -> dict:
    """Ensure divergence patterns have executable criteria + params for scanner/backtest."""
    pt = str(rb.get("pattern_type", "")).lower()
    cond = rb.setdefault("conditions", {})
    div_types = cond.get("divergence_types") or {}

    if "macd_divergence" in pt or div_types:
        rb.setdefault(
            "divergence",
            {"lookback_bars": 65, "swing_order": 5, "min_swing_separation": 8},
        )
        direction = str(rb.get("direction", "bearish")).lower()
        if "bullish" in direction or "bullish" in div_types:
            rb["direction"] = "bullish"
            rb.setdefault("criteria", ["macd_divergence_bullish"])
        else:
            rb["direction"] = "bearish"
            rb.setdefault("criteria", ["macd_divergence_bearish"])

    if "rsi_divergence" in pt:
        rb.setdefault(
            "divergence",
            {"lookback_bars": 65, "swing_order": 5, "min_swing_separation": 8},
        )
        direction = str(rb.get("direction", "bearish")).lower()
        if "bullish" in direction:
            rb.setdefault("criteria", ["rsi_divergence_bullish"])
        else:
            rb.setdefault("criteria", ["rsi_divergence_bearish"])

    cw = rb.get("confidence_weights")
    if isinstance(cw, dict) and "trend_strength" in cw and "trend_alignment" not in cw:
        cw["trend_alignment"] = cw.pop("trend_strength")

    return rb


def _build_user_content(
    text: str,
    file_blocks: list[dict[str, Any]] | None,
) -> str | list[dict[str, Any]]:
    """
    Build the user message content.
    - Text only → plain string (compatible with all models)
    - With files → list of content blocks (multimodal)
    """
    if not file_blocks:
        return text
    content: list[dict[str, Any]] = []
    # Files first (context before question)
    content.extend(file_blocks)
    if text.strip():
        content.append({"type": "text", "text": text})
    return content


def _history_to_text(history: list[dict], user_message: str) -> str:
    """Flatten history to text for the rulebook JSON extraction prompt."""
    lines = []
    for m in history:
        role = m["role"].upper()
        content = m["content"]
        # If content is a list of blocks (multimodal), extract text portions only
        if isinstance(content, list):
            text_parts = [b["text"] for b in content if b.get("type") == "text"]
            content = " ".join(text_parts)
        lines.append(f"{role}: {content}")
    lines.append(f"USER: {user_message}")
    return "\n".join(lines)


# ─── Main entry point ─────────────────────────────────────────────────────────

async def run_studio_chat(
    history: list[dict],
    user_message: str,
    pattern_name: str,
    file_blocks: list[dict[str, Any]] | None = None,
) -> tuple[str, dict | None]:
    """
    Returns (reply_text, rulebook_dict_or_None).

    Flow:
    1. Build user content (text + optional file vision blocks).
    2. Grok drives the conversation turn (vision-capable when attachments present).
    3. If Grok signals [READY_TO_FINALIZE], reason() extracts the rulebook JSON.
    """
    user_content = _build_user_content(user_message, file_blocks)

    messages = [{"role": "system", "content": CHAT_SYSTEM}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_content})

    # Step 1 — Grok conversational + vision turn
    raw_reply = await chat(messages, temperature=0.6, max_tokens=1200)

    ready = _is_ready_to_finalize(raw_reply)
    clean_reply = _clean_reply(raw_reply)
    rulebook = None

    # Step 2 — reason() extracts JSON only when ready signal present
    if ready:
        history_text = _history_to_text(history, user_message)
        if file_blocks:
            # Tell reason() there was a chart/document uploaded
            file_note = f"[Note: User uploaded {len(file_blocks)} file attachment(s) — chart or document — which was analyzed visually in the conversation.]\n\n"
            history_text = file_note + history_text

        extraction_messages = [
            {"role": "system", "content": EXTRACT_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Pattern name: '{pattern_name}'\n\n"
                    f"Full conversation:\n{history_text}"
                ),
            },
        ]
        raw_json = await reason(extraction_messages, temperature=0.1, max_tokens=1800)
        rulebook = _extract_json(raw_json)

        if rulebook:
            rulebook = _normalize_rulebook(rulebook)
            rulebook["finalized"] = True
            clean_reply += "\n\nRulebook finalized and saved. Review it on the right, then run a scan."
        else:
            clean_reply += "\n\n(Rulebook extraction failed — could you give me a bit more detail on the entry rules?)"

    return clean_reply, rulebook
