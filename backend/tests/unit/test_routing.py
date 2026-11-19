"""Cheap-first routing for damage zones (#51)."""

import json
from collections.abc import Iterator

import pytest
from prometheus_client import REGISTRY
from pydantic import SecretStr

import app.core.llm as llm
from app.core.config import settings
from app.core.llm import GeminiClient, OpenAIClient
from app.models.damage import DAMAGE_ZONES
from app.services.damage_detect import _run_zone_pass
from tests.llm_fakes import ScriptedClient

FRONT = DAMAGE_ZONES["front"]


def _finding(component: str, severity: float) -> str:
    damage = {
        "component": component,
        "damage_type": "dent",
        "severity": severity,
        "description": "d",
    }
    return json.dumps({"damages": [damage]})


def _decisions() -> dict[str, float]:
    names = (
        "fast_accepted",
        "escalated_failure",
        "escalated_borderline",
        "escalated_empty",
    )
    return {
        n: REGISTRY.get_sample_value("damage_routing_total", {"decision": n}) or 0.0
        for n in names
    }


@pytest.fixture
def gemini(monkeypatch: pytest.MonkeyPatch) -> Iterator[ScriptedClient]:
    client = ScriptedClient("gemini", [])
    monkeypatch.setattr(settings, "openai_api_key", SecretStr(""))
    monkeypatch.setattr(llm, "get_client", lambda _p: client)
    monkeypatch.setattr(settings, "routing_enabled", True)
    monkeypatch.setattr(settings, "gemini_fast_model", "gemini-fast")
    yield client


def _tiers(client: ScriptedClient) -> list[object]:
    return [r["tier"] for r in client.requests]


async def test_confident_fast_answer_is_kept(gemini: ScriptedClient) -> None:
    gemini.script = [_finding("hood", 0.9)]  # threshold 0.3: far from it
    before = _decisions()

    items = await _run_zone_pass("front", FRONT, [b"img"])

    assert not isinstance(items, Exception) and items[0].severity == 0.9
    assert _tiers(gemini) == ["fast"]
    assert _decisions()["fast_accepted"] == before["fast_accepted"] + 1


async def test_borderline_severity_escalates_to_the_strong_model(
    gemini: ScriptedClient,
) -> None:
    gemini.script = [_finding("hood", 0.35), _finding("hood", 0.6)]  # 0.35 ~ 0.3
    before = _decisions()

    items = await _run_zone_pass("front", FRONT, [b"img"])

    assert _tiers(gemini) == ["fast", "strong"]
    assert not isinstance(items, Exception) and items[0].severity == 0.6
    assert _decisions()["escalated_borderline"] == before["escalated_borderline"] + 1


async def test_fast_failure_escalates(gemini: ScriptedClient) -> None:
    invalid = '{"damages": "nope"}'
    gemini.script = [invalid] * (settings.llm_max_invalid_outputs + 1) + [
        _finding("grille", 0.8)
    ]

    items = await _run_zone_pass("front", FRONT, [b"img"])

    assert _tiers(gemini)[-1] == "strong"
    assert not isinstance(items, Exception) and items[0].component == "grille"


async def test_empty_zones_escalate_only_when_configured(
    gemini: ScriptedClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = json.dumps({"damages": []})
    gemini.script = [empty]
    await _run_zone_pass("front", FRONT, [b"img"])
    assert _tiers(gemini) == ["fast"]

    monkeypatch.setattr(settings, "routing_escalate_empty_zones", True)
    gemini.requests.clear()
    gemini.script = [empty, _finding("hood", 0.5)]
    items = await _run_zone_pass("front", FRONT, [b"img"])
    assert _tiers(gemini) == ["fast", "strong"]
    assert not isinstance(items, Exception) and len(items) == 1


@pytest.mark.parametrize(
    ("enabled", "fast_model"), [(False, "gemini-fast"), (True, "")]
)
async def test_routing_needs_the_flag_and_a_fast_model(
    gemini: ScriptedClient,
    monkeypatch: pytest.MonkeyPatch,
    enabled: bool,
    fast_model: str,
) -> None:
    monkeypatch.setattr(settings, "routing_enabled", enabled)
    monkeypatch.setattr(settings, "gemini_fast_model", fast_model)
    gemini.script = [_finding("hood", 0.9)]

    await _run_zone_pass("front", FRONT, [b"img"])

    assert _tiers(gemini) == ["strong"]


def test_clients_pick_the_fast_model_only_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "gemini_model", "g-strong")
    monkeypatch.setattr(settings, "gemini_fast_model", "g-fast")
    monkeypatch.setattr(settings, "openai_vision_model", "o-vision")
    monkeypatch.setattr(settings, "openai_fast_model", "")
    gemini, openai = GeminiClient(None), OpenAIClient(None)

    assert gemini.model_for(vision=True, tier="fast") == "g-fast"
    assert gemini.model_for(vision=True) == "g-strong"
    assert openai.model_for(vision=True, tier="fast") == "o-vision"  # none set
