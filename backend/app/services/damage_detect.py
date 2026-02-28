"""Damage detection service — uses Vision LLM to assess per-component damage."""

import json
import logging

from openai import AsyncOpenAI

from app.core.config import settings
from app.models.damage import STANDARD_COMPONENTS, DamageAssessment, DamageItem
from app.prompts.damage_assessment import DAMAGE_ASSESSMENT_PROMPT
from app.services.image_proc import load_images_as_base64

logger = logging.getLogger(__name__)


async def detect_damage(upload_id: str) -> DamageAssessment:
    """Send uploaded images to GPT-4 Vision to detect and score damage."""
    images_b64 = load_images_as_base64(upload_id)
    if not images_b64:
        raise ValueError(f"No images found for upload {upload_id}")

    content: list[dict] = [{"type": "text", "text": DAMAGE_ASSESSMENT_PROMPT}]
    for img_b64 in images_b64:
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{img_b64}",
                    "detail": "high",
                },
            }
        )

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": content}],
        max_tokens=2000,
        temperature=0.2,
    )

    raw_text = response.choices[0].message.content or ""
    logger.info("Damage detection raw response: %s", raw_text)

    items = _parse_damage_response(raw_text)
    return DamageAssessment(damages=items)


def _parse_damage_response(raw_text: str) -> list[DamageItem]:
    """Parse the LLM JSON response into a list of DamageItem models."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

    data = json.loads(cleaned)

    items: list[DamageItem] = []
    for entry in data:
        component = entry.get("component", "")
        if component not in STANDARD_COMPONENTS:
            logger.warning("Unknown component '%s', skipping", component)
            continue

        severity = float(entry.get("severity", 0.0))
        severity = max(0.0, min(1.0, severity))

        recommendation = (
            "replace" if severity > settings.severity_replace_threshold else "repair"
        )

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
