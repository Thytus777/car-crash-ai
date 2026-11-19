from unittest.mock import AsyncMock, patch

import pytest

from app.core.llm import LLMUnavailableError
from app.models.llm_outputs import DamageFinding, DamageFindings
from app.services.damage_detect import detect_damage, to_damage_items
from tests.llm_fakes import llm_result


def _finding(
    component: str, severity: float, damage_type: str = "dent"
) -> DamageFinding:
    return DamageFinding.model_validate(
        {
            "component": component,
            "damage_type": damage_type,
            "severity": severity,
            "description": "test",
        }
    )


def test_high_severity_gets_replace() -> None:
    items = to_damage_items(
        [_finding("front_bumper", 0.75, "crush"), _finding("headlight_left", 0.9)]
    )

    assert [i.recommendation for i in items] == ["replace", "replace"]
    assert items[0].component == "front_bumper" and items[0].severity == 0.75


def test_low_severity_gets_repair() -> None:
    items = to_damage_items([_finding("door_front_left", 0.15, "scratch")])

    assert items[0].recommendation == "repair"


def test_structural_parts_use_lower_replace_threshold() -> None:
    # 0.25 is below the default 0.3 but above the A-pillar's 0.2 threshold.
    pillar, door = to_damage_items(
        [_finding("a_pillar_left", 0.25), _finding("door_front_left", 0.25)]
    )

    assert pillar.recommendation == "replace"
    assert door.recommendation == "repair"


async def test_detect_damage_merges_zone_passes_keeping_worst_severity() -> None:
    zone_outputs = iter(
        [
            DamageFindings(damages=[_finding("hood", 0.4)]),
            DamageFindings(damages=[_finding("rear_bumper", 0.65, "deformation")]),
            DamageFindings(damages=[_finding("hood", 0.7)]),
        ]
    )

    async def fake_generate(*_: object, **__: object) -> object:
        return llm_result(next(zone_outputs))

    with (
        patch("app.services.damage_detect.load_images", return_value=[b"jpeg"]),
        patch(
            "app.services.damage_detect.generate",
            new_callable=AsyncMock,
            side_effect=fake_generate,
        ) as generate,
    ):
        result = await detect_damage("0123456789ab")

    assert generate.await_count == 3
    assert [(d.component, d.severity) for d in result.damages] == [
        ("hood", 0.7),
        ("rear_bumper", 0.65),
    ]
    assert result.assessment_method == "zone_pass"


async def test_failed_zone_is_reported_not_silently_dropped() -> None:
    """Regression for #3: a failed zone used to look like an undamaged zone."""

    async def fake_generate(*_: object, task: str, **__: object) -> object:
        if task == "damage_front":
            raise LLMUnavailableError("gemini damage_front: unavailable")
        return llm_result(DamageFindings(damages=[_finding("rear_bumper", 0.5)]))

    with (
        patch("app.services.damage_detect.load_images", return_value=[b"jpeg"]),
        patch("app.services.damage_detect.generate", side_effect=fake_generate),
    ):
        result = await detect_damage("0123456789ab")

    assert result.failed_zones == ["front"]
    assert [d.component for d in result.damages] == ["rear_bumper"]


async def test_all_zones_failing_raises_instead_of_reporting_no_damage() -> None:
    """Regression for #3: three failed zones returned 200 with zero damages."""
    with (
        patch("app.services.damage_detect.load_images", return_value=[b"jpeg"]),
        patch(
            "app.services.damage_detect.generate",
            side_effect=LLMUnavailableError("down"),
        ),
        pytest.raises(LLMUnavailableError),
    ):
        await detect_damage("0123456789ab")


async def test_consensus_disagreements_are_kept() -> None:
    """Regression for #11: consensus flags were computed and thrown away."""
    flags = ["hood: models disagreed on severity (0.20 vs 0.70)."]
    with (
        patch("app.services.damage_detect.load_images", return_value=[b"jpeg"]),
        patch(
            "app.services.consensus.detect_damage_consensus",
            new_callable=AsyncMock,
            return_value=([], flags),
        ),
    ):
        result = await detect_damage("0123456789ab", use_consensus=True)

    assert result.consensus_flags == flags


def test_angle_guidance_does_not_claim_detected_angles() -> None:
    """Regression for #11: 'angles_detected' was inferred from the image count."""
    from app.services.image_proc import assess_angle_coverage

    few, many = assess_angle_coverage(2), assess_angle_coverage(5)

    assert few.angles_detected == [] and many.angles_detected == []
    assert "at least 4 photos" in few.suggestion
    assert many.suggestion == ""
