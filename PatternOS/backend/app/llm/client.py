"""
LLM routing layer for PatternOS.

Model assignment:
  chat()    → Gemini 2.5 Flash  — greetings, conversational turns, clarifying questions
  reason()  → Claude Haiku 4.5  — rulebook JSON extraction, audits, structured reasoning
  screen()  → Gemini 2.5 Flash  — fast scan-loop confidence scoring (high volume calls)

Fallback policy:
  Every call automatically retries on the fallback model (Claude Haiku) if the primary
  model returns an error, rate-limit, or empty response. Fallback errors propagate up.
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
    Primary: Gemini 2.5 Flash   Fallback: Claude Haiku
    Supports multimodal messages (content as list of text/image_url blocks).
    """
    return await _call_with_fallback(
        primary=settings.LLM_CHAT_MODEL,
        fallback=settings.LLM_FALLBACK_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        label="chat",
    )


async def reason(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> str:
    """
    Structured reasoning — rulebook JSON extraction, pattern audits, analysis.
    Primary: Claude Haiku 4.5   Fallback: Gemini 2.5 Flash
    """
    return await _call_with_fallback(
        primary=settings.LLM_REASONING_MODEL,
        fallback=settings.LLM_CHAT_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        label="reason",
    )


async def screen(
    messages: list[dict],
    temperature: float = 0.1,
    max_tokens: int = 512,
) -> str:
    """
    Fast scan-loop scoring — called per symbol, must be cheap & fast.
    Primary: Gemini 2.5 Flash   Fallback: Claude Haiku
    """
    return await _call_with_fallback(
        primary=settings.LLM_SCREENING_MODEL,
        fallback=settings.LLM_FALLBACK_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        label="screen",
    )
