"""Vehicle identification service — uses Vision LLM to identify make/model/year."""

import logging

from app.core.errors import NotFoundError
from app.core.llm import generate
from app.models.llm_outputs import VehicleIdentification
from app.models.vehicle import Vehicle
from app.prompts.vehicle_identification import VEHICLE_ID_PROMPT
from app.services.image_proc import load_images

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.7


async def identify_vehicle(upload_id: str) -> Vehicle:
    """Send uploaded images to a Vision LLM to identify the vehicle.

    Returns a Vehicle model. If confidence < 0.7, the caller should prompt
    the user for manual input.
    """
    images = load_images(upload_id)
    if not images:
        raise NotFoundError(f"Upload {upload_id} has no images")

    result = await generate(
        VehicleIdentification,
        VEHICLE_ID_PROMPT,
        images,
        task="vehicle_id",
        max_output_tokens=300,
        temperature=0.2,
        image_detail="low",
    )
    return to_vehicle(result.output)


def to_vehicle(identified: VehicleIdentification) -> Vehicle:
    return Vehicle(
        make=identified.make,
        model=identified.model,
        year=identified.year or 0,
        body_style=identified.body_style,
        color=identified.color,
        confidence=identified.confidence,
    )


def needs_user_input(vehicle: Vehicle) -> bool:
    """Check if the AI confidence is too low and user input is needed."""
    return vehicle.confidence < CONFIDENCE_THRESHOLD
