"""Eval completion cache and nested call recording in app.core.llm (#15)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import BaseModel

import app.core.llm as llm
from app.core.config import settings
from app.core.llm import (
    CompletionCache,
    Usage,
    generate,
    record_llm_calls,
    use_completion_cache,
)
from tests.llm_fakes import ScriptedClient
from tests.unit.test_llm import rate_limited


def _cache_entries(directory: Path) -> int:
    return len(list(directory.glob("*.json")))


class Answer(BaseModel):
    value: int


@pytest.fixture
def gemini(monkeypatch: pytest.MonkeyPatch) -> Iterator[ScriptedClient]:
    client = ScriptedClient("gemini", [])
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(llm, "_providers", lambda: ["gemini"])
    monkeypatch.setattr(llm, "get_client", lambda _p: client)

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(llm, "_sleep", no_sleep)
    yield client


async def _ask(
    prompt: str = "q", images: tuple[bytes, ...] = (b"img",)
) -> llm.LLMResult[Answer]:
    return await generate(Answer, prompt, images, task="t", max_output_tokens=10)


async def test_second_identical_call_is_served_from_cache(
    gemini: ScriptedClient, tmp_path: Path
) -> None:
    cache = CompletionCache(tmp_path)
    gemini.script = ['{"value": 1}']

    with use_completion_cache(cache):
        live = await _ask()
        replay = await _ask()

    assert len(gemini.requests) == 1
    assert (live.call.cached, replay.call.cached) == (False, True)
    assert replay.output.value == 1
    assert replay.call.usage == live.call.usage == Usage(100, 20)
    assert replay.call.latency_s == pytest.approx(live.call.latency_s)
    assert (cache.hits, cache.misses) == (1, 1)


async def test_re_asks_replay_in_order(gemini: ScriptedClient, tmp_path: Path) -> None:
    cache = CompletionCache(tmp_path)
    gemini.script = ['{"value": "bad"}', '{"value": 2}']

    with use_completion_cache(cache):
        await _ask()
        replay = await _ask()

    assert replay.output.value == 2
    assert (replay.call.attempts, replay.call.invalid_outputs) == (2, 1)
    assert replay.call.cached


async def test_key_changes_with_images_and_prompt_version(
    gemini: ScriptedClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = CompletionCache(tmp_path)
    gemini.script = ['{"value": 1}'] * 3

    with use_completion_cache(cache):
        await _ask(images=(b"a",))
        await _ask(images=(b"b",))
        monkeypatch.setattr(settings, "prompt_version", "v-other")
        await _ask(images=(b"a",))

    assert len(gemini.requests) == 3 and cache.hits == 0


async def test_errors_are_never_cached(gemini: ScriptedClient, tmp_path: Path) -> None:
    cache = CompletionCache(tmp_path)
    gemini.script = [rate_limited(), '{"value": 3}']

    with use_completion_cache(cache):
        await _ask()
    gemini.script = []
    with use_completion_cache(cache):
        replay = await _ask()

    assert replay.output.value == 3 and replay.call.cached
    assert _cache_entries(tmp_path) == 1


async def test_nested_recorders_both_see_calls(gemini: ScriptedClient) -> None:
    gemini.script = ['{"value": 1}']

    with record_llm_calls() as outer:
        with record_llm_calls() as inner:
            await _ask()

    assert len(outer) == len(inner) == 1
