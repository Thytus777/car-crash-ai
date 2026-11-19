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
import hashlib
import json
import logging
import random
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx
import httpx2
import openai
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from opentelemetry import trace
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.core.errors import (
    AppError,
    UpstreamError,
    UpstreamRateLimitedError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)
from app.core.metrics import LLM_CALLS, LLM_DURATION, LLM_TOKENS
from app.core.tracing import (
    GEN_AI_INPUT_TOKENS,
    GEN_AI_MODEL,
    GEN_AI_OUTPUT_TOKENS,
    GEN_AI_SYSTEM,
    traced,
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
    latency_s: float  # model time: live attempts, or as recorded when cached
    error: str | None = None
    cached: bool = False  # every completion came from the eval cache


@dataclass(frozen=True)
class LLMResult[T: BaseModel]:
    output: T
    call: LLMCall


# Active collectors, innermost last; every call is appended to all of them,
# so a nested record_llm_calls() doesn't hide calls from an outer one.
_call_logs: ContextVar[tuple[list[LLMCall], ...]] = ContextVar(
    "llm_call_logs", default=()
)


@contextmanager
def record_llm_calls() -> Iterator[list[LLMCall]]:
    """Collect every LLMCall made inside the block (including child tasks)."""
    calls: list[LLMCall] = []
    token = _call_logs.set((*_call_logs.get(), calls))
    try:
        yield calls
    finally:
        _call_logs.reset(token)


def _log_call(call: LLMCall) -> None:
    for calls in _call_logs.get():
        calls.append(call)


# --- Completion cache (evals) ------------------------------------------------


class CompletionCache:
    """Disk cache of raw completions, so eval runs can be replayed for free.

    The key covers everything that determines the reply: provider, model,
    prompt version, schema, prompt text, image hashes, generation settings,
    and how many invalid replies preceded this one (so re-asks replay in
    order). Errors are never cached.
    """

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.hits = 0
        self.misses = 0

    def key(
        self,
        *,
        provider: Provider,
        model: str,
        schema: type[BaseModel],
        prompt: str,
        images: Sequence[bytes],
        max_output_tokens: int,
        temperature: float,
        image_detail: ImageDetail,
        reply_index: int,
    ) -> str:
        material = {
            "provider": provider,
            "model": model,
            "prompt_version": settings.prompt_version,
            "schema": schema.model_json_schema(),
            "prompt": hashlib.sha256(prompt.encode()).hexdigest(),
            "images": [hashlib.sha256(i).hexdigest() for i in images],
            "max_output_tokens": max_output_tokens,
            "temperature": temperature,
            "image_detail": image_detail,
            "reply_index": reply_index,
        }
        blob = json.dumps(material, sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()

    def get(self, key: str) -> tuple[Completion, float] | None:
        path = self.directory / f"{key}.json"
        if not path.is_file():
            self.misses += 1
            return None
        self.hits += 1
        data = json.loads(path.read_text(encoding="utf-8"))
        completion = Completion(
            text=data["text"],
            usage=Usage(data["input_tokens"], data["output_tokens"]),
            model=data["model"],
        )
        return completion, float(data["latency_s"])

    def put(self, key: str, completion: Completion, latency_s: float) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        record = {
            "text": completion.text,
            "input_tokens": completion.usage.input_tokens,
            "output_tokens": completion.usage.output_tokens,
            "model": completion.model,
            "latency_s": latency_s,
        }
        (self.directory / f"{key}.json").write_text(json.dumps(record), "utf-8")


_completion_cache: ContextVar[CompletionCache | None] = ContextVar(
    "completion_cache", default=None
)


@contextmanager
def use_completion_cache(cache: CompletionCache) -> Iterator[CompletionCache]:
    token = _completion_cache.set(cache)
    try:
        yield cache
    finally:
        _completion_cache.reset(token)


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


@traced("llm.call")
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
    model = client.model_for(vision=bool(images))
    attempts = transient_failures = invalid_outputs = cached_replies = 0
    usage = Usage()
    model_latency = 0.0
    cache = _completion_cache.get()

    def record(ok: bool, error: str | None = None) -> LLMCall:
        call = LLMCall(
            task=task,
            provider=client.provider,
            model=model,
            ok=ok,
            attempts=attempts,
            invalid_outputs=invalid_outputs,
            usage=usage,
            latency_s=model_latency,
            error=error,
            cached=attempts > 0 and cached_replies == attempts,
        )
        _log_call(call)
        outcome = "ok" if ok else "failed"
        LLM_CALLS.labels(
            call.provider, call.model, call.task, outcome, str(call.cached).lower()
        ).inc()
        LLM_TOKENS.labels(call.provider, call.model, "input").inc(
            call.usage.input_tokens
        )
        LLM_TOKENS.labels(call.provider, call.model, "output").inc(
            call.usage.output_tokens
        )
        LLM_DURATION.labels(call.provider, call.task).observe(call.latency_s)
        trace.get_current_span().set_attributes(
            {
                GEN_AI_SYSTEM: call.provider,
                GEN_AI_MODEL: call.model,
                GEN_AI_INPUT_TOKENS: call.usage.input_tokens,
                GEN_AI_OUTPUT_TOKENS: call.usage.output_tokens,
                "app.llm.task": call.task,
                "app.llm.ok": call.ok,
                "app.llm.attempts": call.attempts,
                "app.llm.invalid_outputs": call.invalid_outputs,
                "app.llm.cached": call.cached,
                "app.llm.latency_s": call.latency_s,
                "app.prompt_version": settings.prompt_version,
            }
        )
        return call

    while True:
        attempts += 1
        cache_key = (
            cache.key(
                provider=client.provider,
                model=model,
                schema=schema,
                prompt=prompt,
                images=images,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                image_detail=image_detail,
                reply_index=invalid_outputs,
            )
            if cache
            else None
        )
        hit = cache.get(cache_key) if cache and cache_key else None
        attempt_started = time.perf_counter()
        try:
            if hit:
                completion, recorded_latency = hit
                cached_replies += 1
                model_latency += recorded_latency
            else:
                async with asyncio.timeout(settings.llm_timeout_s):
                    completion = await client.complete(
                        schema=schema,
                        prompt=prompt,
                        images=images,
                        max_output_tokens=max_output_tokens,
                        temperature=temperature,
                        image_detail=image_detail,
                    )
                elapsed = time.perf_counter() - attempt_started
                model_latency += elapsed
                if cache and cache_key:
                    cache.put(cache_key, completion, elapsed)
        except Exception as exc:
            model_latency += time.perf_counter() - attempt_started
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
