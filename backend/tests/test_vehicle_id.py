import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.vehicle_id import (
    _parse_vehicle_response,
    identify_vehicle,
    needs_user_input,
)


def test_parse_valid_json() -> None:
    raw = json.dumps(
        {
            "make": "Toyota",
            "model": "Camry",
            "year": 2020,
            "body_style": "sedan",
            "color": "white",
            "confidence": 0.92,
        }
    )
    vehicle = _parse_vehicle_response(raw)
    assert vehicle.make == "Toyota"
    assert vehicle.model == "Camry"
    assert vehicle.year == 2020
    assert vehicle.confidence == 0.92


def test_parse_json_with_code_fences() -> None:
    raw = '```json\n{"make": "Honda", "model": "Civic", "year": 2019, "confidence": 0.85}\n```'
    vehicle = _parse_vehicle_response(raw)
    assert vehicle.make == "Honda"
    assert vehicle.year == 2019


def test_needs_user_input_low_confidence() -> None:
    from app.models.vehicle import Vehicle

    v = Vehicle(make="Unknown", model="Unknown", year=0, confidence=0.4)
    assert needs_user_input(v) is True


def test_needs_user_input_high_confidence() -> None:
    from app.models.vehicle import Vehicle

    v = Vehicle(make="Toyota", model="Camry", year=2020, confidence=0.9)
    assert needs_user_input(v) is False


@pytest.mark.asyncio
async def test_identify_vehicle_calls_llm() -> None:
    llm_response = json.dumps(
        {
            "make": "Ford",
            "model": "Mustang",
            "year": 2022,
            "body_style": "coupe",
            "color": "red",
            "confidence": 0.95,
        }
    )

    with (
        patch(
            "app.services.vehicle_id.load_images_as_base64",
            return_value=["fake_base64"],
        ),
        patch(
            "app.services.vehicle_id.vision_completion",
            new_callable=AsyncMock,
            return_value=llm_response,
        ),
    ):
        vehicle = await identify_vehicle("test_upload_id")

    assert vehicle.make == "Ford"
    assert vehicle.model == "Mustang"
    assert vehicle.year == 2022
    assert vehicle.confidence == 0.95
