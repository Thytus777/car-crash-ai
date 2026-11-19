"""Versioned prompt files (#25).

The golden files in tests/golden/prompts were rendered by the Python prompt
constants these files replaced. Matching them byte for byte shows the move
to files changed no prompt text. v2 differs from v1 only where intended.
"""

from pathlib import Path

import pytest

from app.core.config import settings
from app.models.damage import DAMAGE_ZONES, STANDARD_COMPONENTS
from app.prompts import PROMPT_NAMES, PROMPTS_ROOT, _load, render, validate_prompts

GOLDEN = Path(__file__).parents[1] / "golden" / "prompts"


def golden(name: str) -> str:
    return (GOLDEN / f"{name}.txt").read_text(encoding="utf-8").rstrip("\n")


def test_every_prompt_exists_for_the_configured_version() -> None:
    for name in PROMPT_NAMES:
        assert (PROMPTS_ROOT / settings.prompt_version / f"{name}.md").is_file()
    validate_prompts()


def test_vehicle_identification_matches_golden() -> None:
    assert render("vehicle_identification", "v1") == golden("vehicle_identification")


@pytest.mark.parametrize("zone", list(DAMAGE_ZONES))
def test_damage_zone_matches_golden(zone: str) -> None:
    rendered = render(
        "damage_zone",
        "v1",
        zone_upper=zone.upper(),
        component_list=", ".join(DAMAGE_ZONES[zone]),
    )
    assert rendered == golden(f"damage_zone_{zone}")


def test_damage_full_matches_golden() -> None:
    rendered = render(
        "damage_full", "v1", component_list=", ".join(STANDARD_COMPONENTS)
    )
    assert rendered == golden("damage_full")


def test_price_prompts_match_golden() -> None:
    car = {"year": 2019, "make": "Toyota", "model": "Camry"}
    assert render("price_estimation", "v1", component="front bumper", **car) == golden(
        "price_estimation"
    )
    assert render(
        "price_extraction",
        "v1",
        site_domain="parts.example",
        component="front bumper",
        cleaned_text="Bumper cover $289.99",
        **car,
    ) == golden("price_extraction")


def test_sanity_check_matches_golden() -> None:
    rendered = render(
        "sanity_check",
        "v1",
        year=2019,
        make="Toyota",
        model="Camry",
        grand_total="650.00",
        damage_summary="  - front_bumper: crush, severity 0.75, recommendation=replace",
    )
    assert rendered == golden("sanity_check")


def test_missing_placeholder_value_raises() -> None:
    with pytest.raises(KeyError, match="component"):
        render("price_estimation", year=2019, make="Toyota", model="Camry")


def test_unknown_prompt_version_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "prompt_version", "v999")
    _load.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="v999"):
            validate_prompts()
    finally:
        _load.cache_clear()


def test_v2_only_fixes_the_vehicle_id_braces() -> None:
    """v1 sent the vehicle-ID JSON example with doubled braces ({{ }})."""
    v1, v2 = PROMPTS_ROOT / "v1", PROMPTS_ROOT / "v2"
    changed = sorted(
        p.name
        for p in v1.glob("*.md")
        if p.read_text(encoding="utf-8") != (v2 / p.name).read_text(encoding="utf-8")
    )
    assert changed == ["vehicle_identification.md"]
    assert sorted(p.name for p in v2.glob("*.md")) == sorted(
        p.name for p in v1.glob("*.md")
    )

    fixed = render("vehicle_identification", "v2")
    assert "{{" not in fixed and fixed == render(
        "vehicle_identification", "v1"
    ).replace("{{", "{").replace("}}", "}")
