"""Vehicle identification service — uses Vision LLM to identify make/model/year."""

import json
import logging

from app.core.llm import vision_completion
from app.models.vehicle import Vehicle
from app.prompts.vehicle_identification import VEHICLE_ID_PROMPT
from app.services.image_proc import load_images_as_base64

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.7


async def identify_vehicle(upload_id: str) -> Vehicle:
    """Send uploaded images to a Vision LLM to identify the vehicle.

    Returns a Vehicle model. If confidence < 0.7, the caller should prompt
    the user for manual input.
    """
    images_b64 = load_images_as_base64(upload_id)
    if not images_b64:
        raise ValueError(f"No images found for upload {upload_id}")

    raw_text = await vision_completion(
        prompt=VEHICLE_ID_PROMPT,
        images_b64=images_b64,
        max_tokens=300,
        temperature=0.2,
        detail="low",
    )
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
        year=int(data.get("year") or 0),
        body_style=data.get("body_style"),
        color=data.get("color"),
        confidence=float(data.get("confidence", 0.0)),
    )


def needs_user_input(vehicle: Vehicle) -> bool:
    """Check if the AI confidence is too low and user input is needed."""
    return vehicle.confidence < CONFIDENCE_THRESHOLD
