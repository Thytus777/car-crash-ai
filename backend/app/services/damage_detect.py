"""Damage detection service.

Zone-based prompts, calibrated thresholds, optional consensus.
"""

import asyncio
import logging
from collections.abc import Sequence

from app.core.config import settings
from app.core.errors import AppError, NotFoundError
from app.core.llm import generate
from app.models.damage import (
    DAMAGE_ZONES,
    STANDARD_COMPONENTS,
    DamageAssessment,
    DamageItem,
    Recommendation,
)
from app.models.llm_outputs import DamageFinding, DamageFindings
from app.prompts import render
from app.services.image_proc import assess_angle_coverage, load_images

logger = logging.getLogger(__name__)

# Per-component replace thresholds, calibrated to typical repair industry practice.
# Components with higher structural importance get a lower threshold (replace sooner).
# Cosmetic panels get a higher threshold (repair longer).
# Default (any unlisted component): settings.severity_replace_threshold (0.3)
COMPONENT_THRESHOLDS: dict[str, float] = {
    # Structural — replace at lower severity
    "a_pillar_left": 0.2,
    "a_pillar_right": 0.2,
    "b_pillar_left": 0.2,
    "b_pillar_right": 0.2,
    "roof": 0.25,
    # Glass — replace immediately once damaged at all
    "windshield_front": 0.15,
    "windshield_rear": 0.15,
    # Safety components — replace at lower severity
    "headlight_left": 0.2,
    "headlight_right": 0.2,
    "taillight_left": 0.2,
    "taillight_right": 0.2,
    # Wheels — replace at moderate severity
    "wheel_front_left": 0.35,
    "wheel_front_right": 0.35,
    "wheel_rear_left": 0.35,
    "wheel_rear_right": 0.35,
    # Cosmetic panels — can repair longer
    "door_front_left": 0.35,
    "door_front_right": 0.35,
    "door_rear_left": 0.35,
    "door_rear_right": 0.35,
    "fender_front_left": 0.35,
    "fender_front_right": 0.35,
    "quarter_panel_left": 0.35,
    "quarter_panel_right": 0.35,
    "rocker_panel_left": 0.40,
    "rocker_panel_right": 0.40,
    "mirror_left": 0.30,
    "mirror_right": 0.30,
    # Bumpers — moderate
    "front_bumper": 0.30,
    "rear_bumper": 0.30,
    "hood": 0.30,
    "trunk": 0.30,
    "grille": 0.25,
}


def _get_threshold(component: str) -> float:
    return COMPONENT_THRESHOLDS.get(component, settings.severity_replace_threshold)


def to_damage_items(findings: Sequence[DamageFinding]) -> list[DamageItem]:
    """Turn validated findings into DamageItems with a repair/replace call."""
    items: list[DamageItem] = []
    for finding in findings:
        threshold = _get_threshold(finding.component)
        recommendation: Recommendation = (
            "replace" if finding.severity > threshold else "repair"
        )
        items.append(
            DamageItem(
                component=finding.component,
                damage_type=finding.damage_type,
                severity=finding.severity,
                description=finding.description,
                recommendation=recommendation,
            )
        )
    return items


def _merge_zone_results(zone_results: list[list[DamageItem]]) -> list[DamageItem]:
    """Merge results from multiple zone passes. Keep worst severity per component."""
    best: dict[str, DamageItem] = {}
    for zone_items in zone_results:
        for item in zone_items:
            existing = best.get(item.component)
            if existing is None or item.severity > existing.severity:
                best[item.component] = item

    merged = list(best.values())
    merged.sort(key=lambda x: x.severity, reverse=True)
    return merged


async def _run_zone_pass(
    zone: str,
    components: list[str],
    images: Sequence[bytes],
) -> list[DamageItem] | AppError:
    """Run one focused zone prompt; return its items, or the error if it failed."""
    prompt = render(
        "damage_zone", zone_upper=zone.upper(), component_list=", ".join(components)
    )
    try:
        result = await generate(
            DamageFindings,
            prompt,
            images,
            task=f"damage_{zone}",
            max_output_tokens=1500,
            temperature=0.2,
        )
    except AppError as exc:
        logger.warning("Zone pass '%s' failed: %s", zone, exc.detail)
        return exc
    logger.info("Zone '%s': %d finding(s)", zone, len(result.output.damages))
    return to_damage_items(result.output.damages)


async def detect_damage(
    upload_id: str,
    use_consensus: bool = False,
) -> DamageAssessment:
    """Detect damage using zone-based focused prompts run in parallel.

    Args:
        upload_id: ID returned by the upload endpoint.
        use_consensus: if True, run both LLM providers on each zone and merge.
    """
    images = load_images(upload_id)
    if not images:
        raise NotFoundError(f"Upload {upload_id} has no images")

    angle_guidance = assess_angle_coverage(len(images))

    if use_consensus:
        from app.services.consensus import detect_damage_consensus

        items, consensus_flags = await detect_damage_consensus(
            prompt=render("damage_full", component_list=", ".join(STANDARD_COMPONENTS)),
            images=images,
        )
        return DamageAssessment(
            damages=items,
            angle_guidance=angle_guidance,
            assessment_method="consensus",
        )

    # Zone-based parallel passes (default)
    zone_tasks = [
        _run_zone_pass(zone, components, images)
        for zone, components in DAMAGE_ZONES.items()
    ]
    outcomes = dict(zip(DAMAGE_ZONES, await asyncio.gather(*zone_tasks), strict=True))
    failed = {z: o for z, o in outcomes.items() if isinstance(o, AppError)}
    if len(failed) == len(outcomes):
        # Nothing was assessed: an empty damage list would read as "no damage".
        raise next(iter(failed.values()))

    succeeded = [o for o in outcomes.values() if not isinstance(o, AppError)]
    return DamageAssessment(
        damages=_merge_zone_results(succeeded),
        failed_zones=list(failed),
        angle_guidance=angle_guidance,
        assessment_method="zone_pass",
    )
