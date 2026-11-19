"""Call policy of app.core.llm: validation, retries, timeouts, fallback."""

import asyncio
from collections.abc import Iterator

import httpx2
import openai
import pytest
from google.genai import errors as genai_errors
from pydantic import BaseModel, SecretStr

import app.core.llm as llm
from app.core.config import settings
from app.core.llm import (
    LLMOutputError,
    LLMRateLimitError,
    LLMRequestError,
    LLMTimeoutError,
    LLMUnavailableError,
    Usage,
    backoff_delay,
    classify_failure,
    generate,
    generate_both,
    record_llm_calls,
)
from tests.llm_fakes import ScriptedClient


class Answer(BaseModel):
    value: int


VALID = '{"value": 42}'
INVALID = '{"value": "not a number"}'


def _openai_status_error(cls: type[openai.APIStatusError], status: int) -> Exception:
    request = httpx2.Request("POST", "https://api.openai.test/v1/chat/completions")
    return cls("boom", response=httpx2.Response(status, request=request), body=None)


def rate_limited() -> Exception:
    return _openai_status_error(openai.RateLimitError, 429)


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Make backoff instant and deterministic (jitter draws 0.5)."""
    recorded: list[float] = []

    async def fake_sleep(delay: float) -> None:
        recorded.append(delay)

    monkeypatch.setattr(llm, "_sleep", fake_sleep)
    monkeypatch.setattr(llm, "_random", lambda: 0.5)
    return recorded


@pytest.fixture
def providers(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, ScriptedClient]]:
    """Gemini primary, OpenAI configured as fallback; scripts set per test."""
    clients = {
        "gemini": ScriptedClient("gemini", []),
        "openai": ScriptedClient("openai", []),
    }
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "openai_api_key", SecretStr("sk-test"))
    monkeypatch.setattr(llm, "get_client", lambda p: clients[p])
    yield clients


async def test_valid_first_reply_is_parsed_and_recorded(
    providers: dict[str, ScriptedClient],
) -> None:
    providers["gemini"].script = [VALID]

    with record_llm_calls() as calls:
        result = await generate(Answer, "q", task="t", max_output_tokens=10)

    assert result.output == Answer(value=42)
    assert result.call.attempts == 1 and result.call.invalid_outputs == 0
    assert result.call.usage == Usage(100, 20)
    assert calls == [result.call]


async def test_schema_is_sent_and_images_forwarded(
    providers: dict[str, ScriptedClient],
) -> None:
    providers["gemini"].script = [VALID]

    result = await generate(Answer, "q", [b"img"], task="t", max_output_tokens=10)

    request = providers["gemini"].requests[0]
    assert request["schema"] is Answer and request["images"] == [b"img"]
    assert result.call.model == "gemini-vision"


async def test_invalid_output_is_re_asked_without_backoff(
    providers: dict[str, ScriptedClient], sleeps: list[float]
) -> None:
    providers["gemini"].script = [INVALID, "not json", VALID]

    result = await generate(Answer, "q", task="t", max_output_tokens=10)

    assert result.output.value == 42
    assert result.call.attempts == 3 and result.call.invalid_outputs == 2
    assert result.call.usage == Usage(300, 60)
    assert sleeps == []


async def test_persistently_invalid_output_falls_back_then_raises(
    providers: dict[str, ScriptedClient],
) -> None:
    limit = settings.llm_max_invalid_outputs + 1
    providers["gemini"].script = [INVALID] * limit
    providers["openai"].script = [INVALID] * limit

    with record_llm_calls() as calls, pytest.raises(LLMOutputError) as exc_info:
        await generate(Answer, "q", task="t", max_output_tokens=10)

    assert exc_info.value.status == 502
    assert [(c.provider, c.ok, c.error) for c in calls] == [
        ("gemini", False, "invalid_output"),
        ("openai", False, "invalid_output"),
    ]


async def test_rate_limit_retries_with_jittered_exponential_backoff(
    providers: dict[str, ScriptedClient],
    sleeps: list[float],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "llm_max_attempts", 3)
    monkeypatch.setattr(settings, "llm_backoff_base_s", 1.0)
    providers["gemini"].script = [rate_limited(), rate_limited(), VALID]

    result = await generate(Answer, "q", task="t", max_output_tokens=10)

    assert result.call.attempts == 3
    assert sleeps == [0.5 * 1.0, 0.5 * 2.0]  # jitter 0.5 x base*2^(n-1)


async def test_exhausted_primary_falls_back_to_secondary(
    providers: dict[str, ScriptedClient], sleeps: list[float]
) -> None:
    providers["gemini"].script = [rate_limited()] * settings.llm_max_attempts
    providers["openai"].script = [VALID]

    with record_llm_calls() as calls:
        result = await generate(Answer, "q", task="t", max_output_tokens=10)

    assert result.call.provider == "openai"
    assert [(c.provider, c.ok) for c in calls] == [("gemini", False), ("openai", True)]


async def test_all_providers_rate_limited_raises_429(
    providers: dict[str, ScriptedClient], sleeps: list[float]
) -> None:
    providers["gemini"].script = [rate_limited()] * settings.llm_max_attempts
    providers["openai"].script = [rate_limited()] * settings.llm_max_attempts

    with pytest.raises(LLMRateLimitError) as exc_info:
        await generate(Answer, "q", task="t", max_output_tokens=10)

    assert exc_info.value.status == 429


async def test_no_fallback_without_a_secondary_key(
    providers: dict[str, ScriptedClient],
    sleeps: list[float],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openai_api_key", SecretStr(""))
    providers["gemini"].script = [rate_limited()] * settings.llm_max_attempts

    with pytest.raises(LLMRateLimitError):
        await generate(Answer, "q", task="t", max_output_tokens=10)

    assert providers["openai"].requests == []


async def test_rejected_request_is_not_retried(
    providers: dict[str, ScriptedClient], sleeps: list[float]
) -> None:
    bad_request = _openai_status_error(openai.BadRequestError, 400)
    providers["gemini"].script = [bad_request]
    providers["openai"].script = [bad_request]

    with pytest.raises(LLMRequestError):
        await generate(Answer, "q", task="t", max_output_tokens=10)

    assert len(providers["gemini"].requests) == 1 and sleeps == []


async def test_slow_provider_times_out_per_attempt(
    providers: dict[str, ScriptedClient],
    sleeps: list[float],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "llm_timeout_s", 0.01)
    monkeypatch.setattr(settings, "openai_api_key", SecretStr(""))

    async def hang(**_: object) -> llm.Completion:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    monkeypatch.setattr(providers["gemini"], "complete", hang)

    with pytest.raises(LLMTimeoutError) as exc_info:
        await generate(Answer, "q", task="t", max_output_tokens=10)

    assert exc_info.value.status == 504
    assert len(sleeps) == settings.llm_max_attempts - 1


async def test_unknown_exceptions_propagate_unchanged(
    providers: dict[str, ScriptedClient],
) -> None:
    providers["gemini"].script = [KeyError("bug in our code")]

    with pytest.raises(KeyError):
        await generate(Answer, "q", task="t", max_output_tokens=10)


async def test_generate_both_returns_both_results(
    providers: dict[str, ScriptedClient],
) -> None:
    providers["gemini"].script = [VALID]
    providers["openai"].script = ['{"value": 7}']

    first, second = await generate_both(Answer, "q", task="t", max_output_tokens=10)

    assert first.output.value == 42
    assert second is not None and second.output.value == 7


async def test_generate_both_survives_one_provider_failing(
    providers: dict[str, ScriptedClient], sleeps: list[float]
) -> None:
    providers["gemini"].script = [rate_limited()] * settings.llm_max_attempts
    providers["openai"].script = ['{"value": 7}']

    first, second = await generate_both(Answer, "q", task="t", max_output_tokens=10)

    assert first.call.provider == "openai" and second is None


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (rate_limited(), "rate_limit"),
        (_openai_status_error(openai.InternalServerError, 500), "unavailable"),
        (_openai_status_error(openai.AuthenticationError, 401), "rejected"),
        (genai_errors.APIError(429, {"error": {"message": "quota"}}), "rate_limit"),
        (genai_errors.APIError(503, {"error": {"message": "down"}}), "unavailable"),
        (genai_errors.APIError(400, {"error": {"message": "bad"}}), "rejected"),
        (TimeoutError(), "timeout"),
        (httpx2.ConnectTimeout("slow"), "timeout"),
        (httpx2.ConnectError("refused"), "unavailable"),
        (ValueError("ours"), None),
    ],
)
def test_classify_failure(exc: Exception, expected: str | None) -> None:
    assert classify_failure(exc) == expected


@pytest.mark.parametrize("error", [LLMUnavailableError, LLMTimeoutError])
def test_llm_errors_carry_http_status(error: type[LLMUnavailableError]) -> None:
    assert error("x").status in (503, 504)


def test_backoff_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_backoff_base_s", 1.0)
    monkeypatch.setattr(settings, "llm_backoff_max_s", 10.0)

    assert backoff_delay(1, 1.0) == 1.0
    assert backoff_delay(4, 1.0) == 8.0
    assert backoff_delay(10, 1.0) == 10.0
    assert backoff_delay(10, 0.0) == 0.0
