"""
LLM routing layer for PatternOS.

Model assignment (defaults from Settings / .env):
  chat()    → Grok 4.1 Fast — studio chat + multimodal
  reason()  → Grok 4.1 Fast — rulebook JSON, audits, structured reasoning
  screen()  → Grok 4.1 Fast — scan-loop scoring

Fallback policy:
  All paths retry with LLM_FALLBACK_MODEL (DeepSeek V3.2) on primary failure.
"""
import logging
from openai import AsyncOpenAI, APIStatusError, APIConnectionError, APITimeoutError
from app.config import get_settings

logger = logging.getLogger("patternos.llm")
settings = get_settings()

_client = AsyncOpenAI(
    api_key=settings.OPENROUTER_API_KEY,
    base_url=settings.OPENROUTER_BASE_URL,
)

# Exceptions that trigger a fallback retry
_RETRYABLE = (APIStatusError, APIConnectionError, APITimeoutError)


async def _call(
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
) -> str:
    """Raw call to a single model. Raises on failure."""
    resp = await _client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    content = resp.choices[0].message.content
    if not content or not content.strip():
        raise ValueError(f"Empty response from {model}")
    return content.strip()


async def _call_with_fallback(
    primary: str,
    fallback: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    label: str,
) -> str:
    """
    Try primary model first. On any error, log and retry with fallback.
    If fallback also fails, the exception propagates.
    """
    try:
        result = await _call(primary, messages, temperature, max_tokens)
        logger.debug(f"[{label}] OK via primary={primary}")
        return result
    except Exception as e:
        logger.warning(f"[{label}] Primary {primary} failed ({type(e).__name__}: {e}). Retrying with fallback={fallback}")
        result = await _call(fallback, messages, temperature, max_tokens)
        logger.info(f"[{label}] OK via fallback={fallback}")
        return result


# ─── Public API ───────────────────────────────────────────────────────────────

async def chat(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> str:
    """
    Conversational turns — greetings, clarifying questions, general chat.
    Primary: Grok 4.1 Fast   Fallback: DeepSeek V3.2
    Supports multimodal messages (content as list of text/image_url blocks).
    """
    if settings.LLM_DISABLED or not settings.OPENROUTER_API_KEY:
        return "LLM disabled (stub)."
    try:
        return await _call_with_fallback(
            primary=settings.LLM_CHAT_MODEL,
            fallback=settings.LLM_FALLBACK_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            label="chat",
        )
    except Exception as e:
        # Keep Studio usable in dev/stdtest even if model routing is misconfigured.
        logger.error(f"[chat] LLM call failed, returning stub ({type(e).__name__}: {e})")
        return "LLM unavailable (stub)."


async def reason(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> str:
    """
    Structured reasoning — rulebook JSON extraction, pattern audits, analysis.
    Primary: Grok 4.1 Fast   Fallback: DeepSeek V3.2
    """
    if settings.LLM_DISABLED or not settings.OPENROUTER_API_KEY:
        return "{}"
    try:
        return await _call_with_fallback(
            primary=settings.LLM_REASONING_MODEL,
            fallback=settings.LLM_FALLBACK_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            label="reason",
        )
    except Exception as e:
        logger.error(f"[reason] LLM call failed, returning stub ({type(e).__name__}: {e})")
        return "{}"


async def screen(
    messages: list[dict],
    temperature: float = 0.1,
    max_tokens: int = 512,
) -> str:
    """
    Fast scan-loop scoring — called per symbol, must be cheap & fast.
    Primary: Grok 4.1 Fast   Fallback: DeepSeek V3.2
    """
    if settings.LLM_DISABLED or not settings.OPENROUTER_API_KEY:
        # Expected by llm_screen: it parses freeform text, so keep it consistent.
        return "Adjusted score: same as base. Analysis: LLM disabled (stub)."
    try:
        return await _call_with_fallback(
            primary=settings.LLM_SCREENING_MODEL,
            fallback=settings.LLM_FALLBACK_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            label="screen",
        )
    except Exception as e:
        logger.error(f"[screen] LLM call failed, returning stub ({type(e).__name__}: {e})")
        return "Adjusted score: same as base. Analysis: LLM unavailable (stub)."
