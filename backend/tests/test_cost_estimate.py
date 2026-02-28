from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.models.damage import DamageItem
from app.models.estimate import PriceResult
from app.models.vehicle import Vehicle
from app.services.cost_estimate import estimate_cost
from app.services.labor import get_labor_cost, get_labor_hours
from app.services.static_prices import lookup_static_price


def test_labor_hours_known_component() -> None:
    hours = get_labor_hours("front_bumper")
    assert hours == Decimal("3.5")


def test_labor_hours_unknown_component() -> None:
    hours = get_labor_hours("nonexistent_part")
    assert hours == Decimal("3.0")


def test_labor_cost_calculation() -> None:
    hours, rate, cost = get_labor_cost("headlight_left")
    assert hours == Decimal("1.0")
    assert rate == Decimal("75.00")
    assert cost == Decimal("75.00")


def test_static_price_lookup_found() -> None:
    price = lookup_static_price("Toyota", "Camry", 2020, "front_bumper")
    assert price == Decimal("280.00")


def test_static_price_lookup_case_insensitive() -> None:
    price = lookup_static_price("toyota", "camry", 2020, "front_bumper")
    assert price == Decimal("280.00")


def test_static_price_lookup_not_found() -> None:
    price = lookup_static_price("Ferrari", "F40", 1990, "front_bumper")
    assert price is None


def test_static_price_lookup_year_range() -> None:
    price = lookup_static_price("Toyota", "Camry", 2017, "front_bumper")
    assert price is None

    price = lookup_static_price("Toyota", "Camry", 2018, "front_bumper")
    assert price == Decimal("280.00")


@pytest.mark.asyncio
async def test_estimate_cost_with_live_prices() -> None:
    vehicle = Vehicle(make="Toyota", model="Camry", year=2020)
    damage = DamageItem(
        component="front_bumper",
        damage_type="crush",
        severity=0.75,
        description="Crushed",
        recommendation="replace",
    )

    mock_results = [
        PriceResult(
            price=Decimal("250.00"),
            currency="USD",
            part_type="aftermarket",
            confidence=0.9,
            product_name="Front Bumper",
            source_url="https://example.com",
        ),
        PriceResult(
            price=Decimal("350.00"),
            currency="USD",
            part_type="oem",
            confidence=0.85,
            product_name="OEM Front Bumper",
            source_url="https://example2.com",
        ),
    ]

    with patch(
        "app.services.cost_estimate.search_part_prices",
        new_callable=AsyncMock,
        return_value=mock_results,
    ):
        result = await estimate_cost(vehicle, damage)

    assert result.pricing_method == "live_search"
    assert result.part_cost_low == Decimal("250.00")
    assert result.part_cost_high == Decimal("350.00")
    assert result.part_cost_avg == Decimal("300.00")
    assert result.labor_hours == Decimal("3.5")
    assert result.labor_cost == Decimal("262.50")


@pytest.mark.asyncio
async def test_estimate_cost_falls_back_to_static() -> None:
    vehicle = Vehicle(make="Toyota", model="Camry", year=2020)
    damage = DamageItem(
        component="front_bumper",
        damage_type="dent",
        severity=0.5,
        description="Dented",
        recommendation="replace",
    )

    with patch(
        "app.services.cost_estimate.search_part_prices",
        new_callable=AsyncMock,
        return_value=[],
    ):
        result = await estimate_cost(vehicle, damage)

    assert result.pricing_method == "static_reference"
    assert result.part_cost_avg == Decimal("280.00")


@pytest.mark.asyncio
async def test_estimate_cost_unknown_vehicle_uses_default() -> None:
    vehicle = Vehicle(make="Ferrari", model="F40", year=1990)
    damage = DamageItem(
        component="hood",
        damage_type="crush",
        severity=0.9,
        description="Destroyed",
        recommendation="replace",
    )

    with patch(
        "app.services.cost_estimate.search_part_prices",
        new_callable=AsyncMock,
        return_value=[],
    ):
        result = await estimate_cost(vehicle, damage)

    assert result.pricing_method == "static_reference"
    assert result.part_cost_avg == Decimal("300.00")
