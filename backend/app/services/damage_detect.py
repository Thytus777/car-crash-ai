"""Damage detection service — zone-based prompts, calibrated thresholds, optional consensus."""

import asyncio
import json
import logging

from app.core.config import settings
from app.core.llm import vision_completion
from app.models.damage import (
    STANDARD_COMPONENTS,
    AngleGuidance,
    DamageAssessment,
    DamageItem,
    ImageQualityWarning,
)
from app.prompts.damage_assessment import ALL_ZONES, build_zone_prompt
from app.services.image_proc import assess_angle_coverage, load_images_as_base64

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


def _parse_damage_response(raw_text: str) -> list[DamageItem]:
    """Parse the LLM JSON response into DamageItems with calibrated thresholds."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        cleaned = cleaned.rsplit("```", 1)[0].strip()

    data = json.loads(cleaned)

    items: list[DamageItem] = []
    for entry in data:
        component = entry.get("component", "")
        if component not in STANDARD_COMPONENTS:
            logger.warning("Unknown component '%s', skipping", component)
            continue

        severity = float(entry.get("severity", 0.0))
        severity = max(0.0, min(1.0, severity))
        threshold = _get_threshold(component)
        recommendation = "replace" if severity > threshold else "repair"

        items.append(
            DamageItem(
                component=component,
                damage_type=entry.get("damage_type", "dent"),
                severity=severity,
                description=entry.get("description", ""),
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
    images_b64: list[str],
) -> list[DamageItem]:
    """Run a single focused zone prompt and parse the result."""
    prompt = build_zone_prompt(zone, components)
    try:
        raw = await vision_completion(
            prompt=prompt,
            images_b64=images_b64,
            max_tokens=1500,
            temperature=0.2,
            detail="high",
        )
        logger.info("Zone '%s' raw response: %s", zone, raw[:200])
        return _parse_damage_response(raw)
    except Exception:
        logger.exception("Zone pass '%s' failed", zone)
        return []


async def detect_damage(
    upload_id: str,
    use_consensus: bool = False,
) -> DamageAssessment:
    """Detect damage using zone-based focused prompts run in parallel.

    Args:
        upload_id: ID returned by the upload endpoint.
        use_consensus: if True, run both LLM providers on each zone and merge.
    """
    images_b64 = load_images_as_base64(upload_id)
    if not images_b64:
        raise ValueError(f"No images found for upload {upload_id}")

    angle_guidance = assess_angle_coverage(len(images_b64))

    if use_consensus:
        from app.services.consensus import detect_damage_consensus
        from app.prompts.damage_assessment import DAMAGE_ASSESSMENT_PROMPT

        items, consensus_flags = await detect_damage_consensus(
            prompt=DAMAGE_ASSESSMENT_PROMPT,
            images_b64=images_b64,
        )
        return DamageAssessment(
            damages=items,
            angle_guidance=angle_guidance,
            assessment_method="consensus",
        )

    # Zone-based parallel passes (default)
    zone_tasks = [
        _run_zone_pass(zone, components, images_b64)
        for zone, components in ALL_ZONES.items()
    ]
    zone_results = await asyncio.gather(*zone_tasks)
    items = _merge_zone_results(list(zone_results))

    return DamageAssessment(
        damages=items,
        angle_guidance=angle_guidance,
        assessment_method="zone_pass",
    )
