"""LLM access: typed structured output with bounded retries and fallback.

``generate(schema, prompt, images)`` is the single entry point. It sends the
Pydantic ``schema`` to the provider as a native structured-output schema,
validates the reply against the same schema, and returns the parsed object.

Call policy (tunable in Settings):
- every attempt runs under ``llm_timeout_s``;
- transient failures (rate limit, 5xx, connection, timeout) are retried up to
  ``llm_max_attempts`` per provider with capped exponential backoff and full
  jitter;
- schema-invalid output is re-requested up to ``llm_max_invalid_outputs``
  times, without backoff;
- if the primary provider is exhausted and the other one has a key, the call
  falls back to it;
- a request the provider rejects (4xx other than 429) is not retried.

Every provider attempt sequence is recorded as an ``LLMCall`` (tokens,
attempts, latency); wrap work in ``record_llm_calls()`` to collect them.
"""

import asyncio
import base64
import logging
import random
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import httpx
import httpx2
import openai
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.core.errors import (
    AppError,
    UpstreamError,
    UpstreamRateLimitedError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)

logger = logging.getLogger(__name__)

Provider = Literal["gemini", "openai"]
ImageDetail = Literal["low", "high"]

# --- Errors -----------------------------------------------------------------


class LLMRateLimitError(UpstreamRateLimitedError):
    """Every available provider is rate-limited."""


class LLMTimeoutError(UpstreamTimeoutError):
    """The provider did not answer within the per-attempt timeout."""


class LLMUnavailableError(UpstreamUnavailableError):
    """The provider could not be reached or returned a server error."""


class LLMOutputError(UpstreamError):
    """The provider kept returning output that fails the schema."""


class LLMRequestError(UpstreamError):
    """The provider rejected the request (auth, bad request, missing key)."""


Failure = Literal["rate_limit", "timeout", "unavailable", "rejected"]

_ERROR_FOR: dict[Failure, type[AppError]] = {
    "rate_limit": LLMRateLimitError,
    "timeout": LLMTimeoutError,
    "unavailable": LLMUnavailableError,
    "rejected": LLMRequestError,
}

_LLMError = (
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
    LLMOutputError,
    LLMRequestError,
)


def classify_failure(exc: BaseException) -> Failure | None:
    """Map an SDK/transport exception to a failure kind; None if unknown."""
    if isinstance(exc, TimeoutError | openai.APITimeoutError):
        return "timeout"
    if isinstance(exc, openai.RateLimitError):
        return "rate_limit"
    if isinstance(exc, openai.APIConnectionError):
        return "unavailable"
    if isinstance(exc, openai.APIStatusError):
        return _from_status(exc.status_code)
    if isinstance(exc, genai_errors.APIError):
        return _from_status(exc.code)
    # The SDKs use httpx2; our own HTTP calls use httpx.
    if isinstance(exc, httpx.TimeoutException | httpx2.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.TransportError | httpx2.TransportError):
        return "unavailable"
    return None


def _from_status(status: int) -> Failure:
    if status == 429:
        return "rate_limit"
    if status >= 500:
        return "unavailable"
    return "rejected"


# --- Results and call log ---------------------------------------------------


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0  # includes reasoning/"thinking" tokens

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
        )


@dataclass(frozen=True)
class Completion:
    """One raw provider reply."""

    text: str
    usage: Usage
    model: str


@dataclass(frozen=True)
class LLMCall:
    """Summary of one provider's attempts for one generate() call."""

    task: str
    provider: Provider
    model: str
    ok: bool
    attempts: int  # requests sent, including retries
    invalid_outputs: int  # replies that failed schema validation
    usage: Usage  # summed over all attempts
    latency_s: float
    error: str | None = None


@dataclass(frozen=True)
class LLMResult[T: BaseModel]:
    output: T
    call: LLMCall


_call_log: ContextVar[list[LLMCall] | None] = ContextVar("llm_call_log", default=None)


@contextmanager
def record_llm_calls() -> Iterator[list[LLMCall]]:
    """Collect every LLMCall made inside the block (including child tasks)."""
    calls: list[LLMCall] = []
    token = _call_log.set(calls)
    try:
        yield calls
    finally:
        _call_log.reset(token)


def _log_call(call: LLMCall) -> None:
    calls = _call_log.get()
    if calls is not None:
        calls.append(call)


# --- Provider clients -------------------------------------------------------


class ProviderClient(Protocol):
    provider: Provider

    def model_for(self, *, vision: bool) -> str: ...

    async def complete(
        self,
        *,
        schema: type[BaseModel],
        prompt: str,
        images: Sequence[bytes],
        max_output_tokens: int,
        temperature: float,
        image_detail: ImageDetail,
    ) -> Completion: ...


class GeminiClient:
    provider: Provider = "gemini"

    def __init__(self, client: Any) -> None:
        self._client = client

    def model_for(self, *, vision: bool) -> str:
        return settings.gemini_model

    async def complete(
        self,
        *,
        schema: type[BaseModel],
        prompt: str,
        images: Sequence[bytes],
        max_output_tokens: int,
        temperature: float,
        image_detail: ImageDetail,
    ) -> Completion:
        contents: list[Any] = [prompt]
        contents.extend(
            genai_types.Part.from_bytes(data=img, mime_type="image/jpeg")
            for img in images
        )
        config = genai_types.GenerateContentConfig(
            max_output_tokens=max_output_tokens + settings.gemini_output_token_padding,
            temperature=temperature,
            response_mime_type="application/json",
            response_json_schema=schema.model_json_schema(),
            thinking_config=genai_types.ThinkingConfig(
                thinking_budget=settings.gemini_thinking_budget
            ),
        )
        model = self.model_for(vision=bool(images))
        response = await self._client.aio.models.generate_content(
            model=model, contents=contents, config=config
        )
        meta = response.usage_metadata
        usage = Usage(
            input_tokens=(meta.prompt_token_count or 0) if meta else 0,
            output_tokens=(
                (meta.candidates_token_count or 0) + (meta.thoughts_token_count or 0)
                if meta
                else 0
            ),
        )
        return Completion(text=response.text or "", usage=usage, model=model)


class OpenAIClient:
    provider: Provider = "openai"

    def __init__(self, client: Any) -> None:
        self._client = client

    def model_for(self, *, vision: bool) -> str:
        return settings.openai_vision_model if vision else settings.openai_text_model

    async def complete(
        self,
        *,
        schema: type[BaseModel],
        prompt: str,
        images: Sequence[bytes],
        max_output_tokens: int,
        temperature: float,
        image_detail: ImageDetail,
    ) -> Completion:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for img in images:
            data_url = "data:image/jpeg;base64," + base64.b64encode(img).decode()
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": data_url, "detail": image_detail},
                }
            )
        model = self.model_for(vision=bool(images))
        response = await self._client.chat.completions.parse(
            model=model,
            messages=[{"role": "user", "content": content}],
            response_format=schema,
            max_completion_tokens=max_output_tokens,
            temperature=temperature,
        )
        message = response.choices[0].message
        usage = Usage(
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
        )
        # A refusal has no content; validation then fails and is retried.
        return Completion(text=message.content or "", usage=usage, model=model)


def _api_key(provider: Provider) -> str:
    if provider == "gemini":
        return (
            settings.gemini_api_key.get_secret_value()
            or settings.google_ai_gemini_api_key.get_secret_value()
        )
    return settings.openai_api_key.get_secret_value()


_clients: dict[Provider, ProviderClient] = {}


def get_client(provider: Provider) -> ProviderClient:
    """Process-wide client per provider. SDK retries are off: we own policy."""
    if provider not in _clients:
        key = _api_key(provider)
        if provider == "gemini":
            timeout_ms = int(settings.llm_timeout_s * 1000)
            _clients[provider] = GeminiClient(
                genai.Client(
                    api_key=key,
                    http_options=genai_types.HttpOptions(timeout=timeout_ms),
                )
            )
        else:
            _clients[provider] = OpenAIClient(
                openai.AsyncOpenAI(
                    api_key=key, timeout=settings.llm_timeout_s, max_retries=0
                )
            )
    return _clients[provider]


def _providers() -> list[Provider]:
    primary: Provider = settings.ai_provider
    secondary: Provider = "openai" if primary == "gemini" else "gemini"
    return [primary, secondary] if _api_key(secondary) else [primary]


# --- Call policy ------------------------------------------------------------


def backoff_delay(failures: int, rand: float) -> float:
    """Full-jitter exponential backoff: uniform in [0, min(cap, base*2^(n-1))]."""
    ceiling = min(
        settings.llm_backoff_max_s, settings.llm_backoff_base_s * 2.0 ** (failures - 1)
    )
    return rand * ceiling


# Indirection so tests can make backoff instant and deterministic.
_sleep = asyncio.sleep
_random = random.random


async def _call_provider[T: BaseModel](
    client: ProviderClient,
    schema: type[T],
    prompt: str,
    images: Sequence[bytes],
    *,
    task: str,
    max_output_tokens: int,
    temperature: float,
    image_detail: ImageDetail,
) -> LLMResult[T]:
    started = time.perf_counter()
    model = client.model_for(vision=bool(images))
    attempts = transient_failures = invalid_outputs = 0
    usage = Usage()

    def record(ok: bool, error: str | None = None) -> LLMCall:
        call = LLMCall(
            task=task,
            provider=client.provider,
            model=model,
            ok=ok,
            attempts=attempts,
            invalid_outputs=invalid_outputs,
            usage=usage,
            latency_s=time.perf_counter() - started,
            error=error,
        )
        _log_call(call)
        return call

    while True:
        attempts += 1
        try:
            async with asyncio.timeout(settings.llm_timeout_s):
                completion = await client.complete(
                    schema=schema,
                    prompt=prompt,
                    images=images,
                    max_output_tokens=max_output_tokens,
                    temperature=temperature,
                    image_detail=image_detail,
                )
        except Exception as exc:
            failure = classify_failure(exc)
            if failure is None:
                record(ok=False, error=type(exc).__name__)
                raise
            transient_failures += failure != "rejected"
            if failure == "rejected" or transient_failures >= settings.llm_max_attempts:
                record(ok=False, error=failure)
                raise _ERROR_FOR[failure](
                    f"{client.provider} {task}: {failure} after {attempts} attempt(s)"
                ) from exc
            delay = backoff_delay(transient_failures, _random())
            logger.warning(
                "%s %s: %s (attempt %d), retrying in %.1fs",
                client.provider,
                task,
                failure,
                attempts,
                delay,
            )
            await _sleep(delay)
            continue

        usage = usage + completion.usage
        try:
            output = schema.model_validate_json(completion.text)
        except ValidationError as exc:
            invalid_outputs += 1
            if invalid_outputs > settings.llm_max_invalid_outputs:
                record(ok=False, error="invalid_output")
                raise LLMOutputError(
                    f"{client.provider} {task}: output failed schema validation "
                    f"{invalid_outputs} time(s)"
                ) from exc
            logger.warning(
                "%s %s: invalid output (%d error(s)), re-asking",
                client.provider,
                task,
                exc.error_count(),
            )
            continue

        return LLMResult(output=output, call=record(ok=True))


async def generate[T: BaseModel](
    schema: type[T],
    prompt: str,
    images: Sequence[bytes] = (),
    *,
    task: str,
    max_output_tokens: int,
    temperature: float = 0.2,
    image_detail: ImageDetail = "high",
) -> LLMResult[T]:
    """Ask the configured provider(s) for output matching ``schema``."""
    last_error: Exception | None = None
    for provider in _providers():
        try:
            return await _call_provider(
                get_client(provider),
                schema,
                prompt,
                images,
                task=task,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                image_detail=image_detail,
            )
        except _LLMError as exc:
            logger.warning("%s %s failed: %s", provider, task, exc.detail)
            last_error = exc
    assert last_error is not None
    raise last_error


async def generate_both[T: BaseModel](
    schema: type[T],
    prompt: str,
    images: Sequence[bytes] = (),
    *,
    task: str,
    max_output_tokens: int,
    temperature: float = 0.2,
) -> tuple[LLMResult[T], LLMResult[T] | None]:
    """Run every configured provider in parallel (for consensus).

    Returns (first successful result, the other result or None). Raises the
    primary provider's error only if every provider failed.
    """
    providers = _providers()
    results = await asyncio.gather(
        *(
            _call_provider(
                get_client(p),
                schema,
                prompt,
                images,
                task=task,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                image_detail="high",
            )
            for p in providers
        ),
        return_exceptions=True,
    )
    ok = [r for r in results if isinstance(r, LLMResult)]
    for r in results:
        if isinstance(r, BaseException) and not isinstance(r, _LLMError):
            raise r
    if not ok:
        first = results[0]
        assert isinstance(first, Exception)
        raise first
    return ok[0], (ok[1] if len(ok) > 1 else None)
