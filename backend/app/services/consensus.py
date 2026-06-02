"""Multi-model consensus service.

Runs both LLM providers on the same damage-detection prompt in parallel,
then merges results. Components where the two models diverge significantly
(severity difference > DIVERGENCE_THRESHOLD) are flagged as uncertain so
the final report can surface that to the user.
"""

import json
import logging

from app.core.llm import dual_vision_completion
from app.models.damage import DamageItem, STANDARD_COMPONENTS
from app.services.damage_detect import _parse_damage_response, COMPONENT_THRESHOLDS

logger = logging.getLogger(__name__)

# Severity gap that triggers an "uncertain" flag
DIVERGENCE_THRESHOLD = 0.25


async def detect_damage_consensus(
    prompt: str,
    images_b64: list[str],
) -> tuple[list[DamageItem], list[str]]:
    """Run damage detection with both providers and merge results.

    Returns:
        (merged_items, uncertainty_flags)
        uncertainty_flags is a list of human-readable strings for components
        where the two models disagreed significantly.
    """
    primary_raw, secondary_raw = await dual_vision_completion(
        prompt=prompt,
        images_b64=images_b64,
        max_tokens=2000,
        temperature=0.2,
    )

    primary_items = _parse_damage_response(primary_raw)

    if secondary_raw is None:
        logger.info("Consensus: only one provider available, using single result")
        return primary_items, []

    secondary_items = _parse_damage_response(secondary_raw)

    merged, flags = _merge_assessments(primary_items, secondary_items)
    return merged, flags


def _merge_assessments(
    primary: list[DamageItem],
    secondary: list[DamageItem],
) -> tuple[list[DamageItem], list[str]]:
    """Merge two damage lists. For each component:
    - If only one model detected it: include it as-is.
    - If both detected it: average the severity, flag if divergence is high.
    - Take the damage_type and description from the higher-severity model.
    """
    primary_map = {item.component: item for item in primary}
    secondary_map = {item.component: item for item in secondary}

    all_components = set(primary_map) | set(secondary_map)
    merged: list[DamageItem] = []
    flags: list[str] = []

    for component in all_components:
        p = primary_map.get(component)
        s = secondary_map.get(component)

        if p is None and s is not None:
            merged.append(s)
            continue
        if s is None and p is not None:
            merged.append(p)
            continue

        # Both detected — average severity
        assert p is not None and s is not None
        divergence = abs(p.severity - s.severity)
        avg_severity = (p.severity + s.severity) / 2.0

        if divergence >= DIVERGENCE_THRESHOLD:
            flags.append(
                f"{component}: models disagreed on severity "
                f"({p.severity:.2f} vs {s.severity:.2f}). "
                f"Using average ({avg_severity:.2f}). Physical inspection recommended."
            )

        # Use the higher-severity item's damage_type/description for richer detail
        source = p if p.severity >= s.severity else s
        threshold = COMPONENT_THRESHOLDS.get(component, 0.3)
        recommendation = "replace" if avg_severity > threshold else "repair"

        merged.append(
            DamageItem(
                component=component,
                damage_type=source.damage_type,
                severity=round(avg_severity, 3),
                description=source.description,
                recommendation=recommendation,
            )
        )

    # Sort by severity descending
    merged.sort(key=lambda x: x.severity, reverse=True)
    return merged, flags
