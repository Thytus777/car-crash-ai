from unittest.mock import AsyncMock, patch

from app.models.llm_outputs import VehicleIdentification
from app.models.vehicle import Vehicle
from app.services.vehicle_id import identify_vehicle, needs_user_input, to_vehicle
from tests.llm_fakes import llm_result


def _identified(**overrides: object) -> VehicleIdentification:
    fields: dict[str, object] = {
        "make": "Ford",
        "model": "Mustang",
        "year": 2022,
        "body_style": "coupe",
        "color": "red",
        "confidence": 0.95,
    }
    fields.update(overrides)
    return VehicleIdentification.model_validate(fields)


def test_to_vehicle_maps_fields() -> None:
    vehicle = to_vehicle(_identified())

    assert (vehicle.make, vehicle.model, vehicle.year) == ("Ford", "Mustang", 2022)
    assert vehicle.confidence == 0.95


def test_to_vehicle_unknown_year_becomes_zero() -> None:
    assert to_vehicle(_identified(year=None)).year == 0


def test_needs_user_input_low_confidence() -> None:
    v = Vehicle(make="Unknown", model="Unknown", year=0, confidence=0.4)
    assert needs_user_input(v) is True


def test_needs_user_input_high_confidence() -> None:
    v = Vehicle(make="Toyota", model="Camry", year=2020, confidence=0.9)
    assert needs_user_input(v) is False


async def test_identify_vehicle_requests_typed_output_with_low_detail() -> None:
    with (
        patch("app.services.vehicle_id.load_images", return_value=[b"jpeg"]),
        patch(
            "app.services.vehicle_id.generate",
            new_callable=AsyncMock,
            return_value=llm_result(_identified()),
        ) as generate,
    ):
        vehicle = await identify_vehicle("0123456789ab")

    assert vehicle.make == "Ford" and vehicle.confidence == 0.95
    args, kwargs = generate.call_args
    assert args[0] is VehicleIdentification and args[2] == [b"jpeg"]
    assert kwargs["image_detail"] == "low"
