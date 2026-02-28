"""Vehicle identification service — uses Vision LLM to identify make/model/year."""

import json
import logging

from openai import AsyncOpenAI

from app.core.config import settings
from app.models.vehicle import Vehicle
from app.prompts.vehicle_identification import VEHICLE_ID_PROMPT
from app.services.image_proc import load_images_as_base64

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.7


async def identify_vehicle(upload_id: str) -> Vehicle:
    """Send uploaded images to GPT-4 Vision to identify the vehicle.

    Returns a Vehicle model. If confidence < 0.7, the caller should prompt
    the user for manual input.
    """
    images_b64 = load_images_as_base64(upload_id)
    if not images_b64:
        raise ValueError(f"No images found for upload {upload_id}")

    content: list[dict] = [{"type": "text", "text": VEHICLE_ID_PROMPT}]
    for img_b64 in images_b64:
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{img_b64}",
                    "detail": "low",
                },
            }
        )

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": content}],
        max_tokens=300,
        temperature=0.2,
    )

    raw_text = response.choices[0].message.content or ""
    logger.info("Vehicle ID raw response: %s", raw_text)

    parsed = _parse_vehicle_response(raw_text)
    return parsed


def _parse_vehicle_response(raw_text: str) -> Vehicle:
    """Parse the LLM JSON response into a Vehicle model."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

    data = json.loads(cleaned)

    return Vehicle(
        make=data.get("make", "Unknown"),
        model=data.get("model", "Unknown"),
        year=int(data.get("year", 0)),
        body_style=data.get("body_style"),
        color=data.get("color"),
        confidence=float(data.get("confidence", 0.0)),
    )


def needs_user_input(vehicle: Vehicle) -> bool:
    """Check if the AI confidence is too low and user input is needed."""
    return vehicle.confidence < CONFIDENCE_THRESHOLD
