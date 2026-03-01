"""LLM abstraction layer — supports Gemini and OpenAI providers."""

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


async def vision_completion(
    prompt: str,
    images_b64: list[str],
    max_tokens: int = 2000,
    temperature: float = 0.2,
    detail: str = "high",
) -> str:
    """Send a vision (text + images) request to the configured LLM provider.

    Returns the raw text response from the model.
    """
    if settings.ai_provider == "gemini":
        return await _gemini_vision(prompt, images_b64, max_tokens, temperature)
    return await _openai_vision(prompt, images_b64, max_tokens, temperature, detail)


async def text_completion(
    prompt: str,
    max_tokens: int = 200,
    temperature: float = 0.1,
) -> str:
    """Send a text-only request to the configured LLM provider.

    Uses a smaller/cheaper model suitable for extraction tasks.
    Returns the raw text response.
    """
    if settings.ai_provider == "gemini":
        return await _gemini_text(prompt, max_tokens, temperature)
    return await _openai_text(prompt, max_tokens, temperature)


# --- Gemini implementation ---


def _get_gemini_key() -> str:
    """Return the Gemini API key from whichever env var is set."""
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

    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents,
        config=types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
            response_mime_type="application/json",
        ),
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

    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
            response_mime_type="application/json",
        ),
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
