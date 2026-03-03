"""LLM abstraction layer — supports Gemini and OpenAI providers with retry."""

import asyncio
import logging
import re

from app.core.config import settings

logger = logging.getLogger(__name__)

# Gemini 2.5 is a "thinking" model — reasoning tokens count against
# max_output_tokens. We pad the budget so visible output isn't truncated.
_GEMINI_TOKEN_PADDING = 8000
_GEMINI_THINKING_BUDGET = 512

_MAX_RETRIES = 2
_RETRY_BASE_DELAY = 10  # seconds


class LLMRateLimitError(Exception):
    """Raised when all configured LLM providers are rate-limited."""


def _is_rate_limit_error(exc: Exception) -> bool:
    return "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc) or "RateLimitError" in type(exc).__name__


def _parse_retry_delay(exc: Exception) -> float:
    m = re.search(r"retryDelay.*?'?(\d+\.?\d*)s'?", str(exc))
    return float(m.group(1)) + 1 if m else _RETRY_BASE_DELAY


async def _retry(coro_factory, label: str):
    """Call coro_factory() up to _MAX_RETRIES times on rate-limit errors."""
    last_exc = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return await coro_factory()
        except Exception as exc:
            last_exc = exc
            if not _is_rate_limit_error(exc) or attempt == _MAX_RETRIES:
                raise
            delay = _parse_retry_delay(exc)
            logger.warning(
                "%s rate-limited (attempt %d/%d), retrying in %.0fs",
                label, attempt + 1, _MAX_RETRIES + 1, delay,
            )
            await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]


# --- Public API ---


async def vision_completion(
    prompt: str,
    images_b64: list[str],
    max_tokens: int = 2000,
    temperature: float = 0.2,
    detail: str = "high",
) -> str:
    """Send a vision request, with automatic retry and provider fallback."""
    primary = settings.ai_provider
    fallback = "openai" if primary == "gemini" else "gemini"

    # Try primary provider
    try:
        if primary == "gemini":
            return await _retry(
                lambda: _gemini_vision(prompt, images_b64, max_tokens, temperature),
                "Gemini vision",
            )
        return await _retry(
            lambda: _openai_vision(prompt, images_b64, max_tokens, temperature, detail),
            "OpenAI vision",
        )
    except Exception as primary_exc:
        if not _is_rate_limit_error(primary_exc):
            raise

    # Fallback to other provider if it has a key
    logger.warning("%s exhausted, falling back to %s", primary, fallback)
    try:
        if fallback == "gemini" and _get_gemini_key():
            return await _retry(
                lambda: _gemini_vision(prompt, images_b64, max_tokens, temperature),
                "Gemini vision (fallback)",
            )
        elif fallback == "openai" and settings.openai_api_key:
            return await _retry(
                lambda: _openai_vision(prompt, images_b64, max_tokens, temperature, detail),
                "OpenAI vision (fallback)",
            )
    except Exception:
        pass

    raise LLMRateLimitError(
        "All AI providers are rate-limited. Please wait a few minutes and try again, "
        "or check your API key quotas."
    )


async def text_completion(
    prompt: str,
    max_tokens: int = 200,
    temperature: float = 0.1,
) -> str:
    """Send a text request, with automatic retry and provider fallback."""
    primary = settings.ai_provider
    fallback = "openai" if primary == "gemini" else "gemini"

    try:
        if primary == "gemini":
            return await _retry(
                lambda: _gemini_text(prompt, max_tokens, temperature),
                "Gemini text",
            )
        return await _retry(
            lambda: _openai_text(prompt, max_tokens, temperature),
            "OpenAI text",
        )
    except Exception as primary_exc:
        if not _is_rate_limit_error(primary_exc):
            raise

    logger.warning("%s exhausted, falling back to %s", primary, fallback)
    try:
        if fallback == "gemini" and _get_gemini_key():
            return await _retry(
                lambda: _gemini_text(prompt, max_tokens, temperature),
                "Gemini text (fallback)",
            )
        elif fallback == "openai" and settings.openai_api_key:
            return await _retry(
                lambda: _openai_text(prompt, max_tokens, temperature),
                "OpenAI text (fallback)",
            )
    except Exception:
        pass

    raise LLMRateLimitError(
        "All AI providers are rate-limited. Please wait a few minutes and try again, "
        "or check your API key quotas."
    )


# --- Gemini implementation ---


def _get_gemini_key() -> str:
    return settings.gemini_api_key or settings.google_ai_gemini_api_key


async def _gemini_vision(
    prompt: str,
    images_b64: list[str],
    max_tokens: int,
    temperature: float,
) -> str:
    import base64

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=_get_gemini_key())

    contents: list = [prompt]
    for img_b64 in images_b64:
        image_bytes = base64.b64decode(img_b64)
        contents.append(
            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
        )

    model_name = settings.gemini_model
    config_kwargs: dict = {
        "max_output_tokens": max_tokens,
        "temperature": temperature,
        "response_mime_type": "application/json",
    }
    if "2.5" in model_name:
        config_kwargs["max_output_tokens"] = max_tokens + _GEMINI_TOKEN_PADDING
        config_kwargs["thinking_config"] = types.ThinkingConfig(
            thinking_budget=_GEMINI_THINKING_BUDGET
        )

    response = await client.aio.models.generate_content(
        model=model_name,
        contents=contents,
        config=types.GenerateContentConfig(**config_kwargs),
    )

    return response.text or ""


async def _gemini_text(
    prompt: str,
    max_tokens: int,
    temperature: float,
) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=_get_gemini_key())

    model_name = settings.gemini_model
    config_kwargs: dict = {
        "max_output_tokens": max_tokens,
        "temperature": temperature,
        "response_mime_type": "application/json",
    }
    if "2.5" in model_name:
        config_kwargs["max_output_tokens"] = max_tokens + _GEMINI_TOKEN_PADDING
        config_kwargs["thinking_config"] = types.ThinkingConfig(
            thinking_budget=_GEMINI_THINKING_BUDGET
        )

    response = await client.aio.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(**config_kwargs),
    )

    return response.text or ""


# --- OpenAI implementation ---


async def _openai_vision(
    prompt: str,
    images_b64: list[str],
    max_tokens: int,
    temperature: float,
    detail: str,
) -> str:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    content: list[dict] = [{"type": "text", "text": prompt}]
    for img_b64 in images_b64:
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{img_b64}",
                    "detail": detail,
                },
            }
        )

    response = await client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": content}],
        max_tokens=max_tokens,
        temperature=temperature,
    )

    return response.choices[0].message.content or ""


async def _openai_text(
    prompt: str,
    max_tokens: int,
    temperature: float,
) -> str:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    response = await client.chat.completions.create(
        model="gpt-4.1-nano",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
    )

    return response.choices[0].message.content or ""
