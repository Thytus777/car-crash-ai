"""Cost estimation service — orchestrates live price search + labor calculation."""

import logging
from decimal import Decimal

from app.models.damage import DamageItem
from app.models.estimate import CostEstimate
from app.models.vehicle import Vehicle
from app.services.labor import get_labor_cost
from app.services.price_search import search_part_prices
from app.services.static_prices import lookup_static_price

logger = logging.getLogger(__name__)


async def estimate_cost(
    vehicle: Vehicle,
    damage: DamageItem,
) -> CostEstimate:
    """Estimate repair/replacement cost for a single damaged component."""
    labor_hours, labor_rate, labor_cost = get_labor_cost(damage.component)

    live_results = await search_part_prices(
        make=vehicle.make,
        model=vehicle.model,
        year=vehicle.year,
        component=damage.component,
    )

    if live_results:
        prices = [r.price for r in live_results]
        part_low = min(prices)
        part_high = max(prices)
        part_avg = (sum(prices) / len(prices)).quantize(Decimal("0.01"))
        pricing_method = "live_search"
    else:
        static_price = lookup_static_price(
            make=vehicle.make,
            model=vehicle.model,
            year=vehicle.year,
            component=damage.component,
        )

        if static_price is not None:
            part_avg = static_price
            part_low = (static_price * Decimal("0.7")).quantize(Decimal("0.01"))
            part_high = (static_price * Decimal("1.4")).quantize(Decimal("0.01"))
        else:
            part_avg = Decimal("300.00")
            part_low = Decimal("150.00")
            part_high = Decimal("500.00")
            logger.warning(
                "No price data for %s %s %d %s, using default",
                vehicle.make,
                vehicle.model,
                vehicle.year,
                damage.component,
            )

        pricing_method = "static_reference"

    return CostEstimate(
        component=damage.component,
        recommendation=damage.recommendation,
        part_cost_low=part_low,
        part_cost_avg=part_avg,
        part_cost_high=part_high,
        price_sources=live_results,
        pricing_method=pricing_method,
        labor_hours=labor_hours,
        labor_rate=labor_rate,
        labor_cost=labor_cost,
        total_low=(part_low + labor_cost).quantize(Decimal("0.01")),
        total_avg=(part_avg + labor_cost).quantize(Decimal("0.01")),
        total_high=(part_high + labor_cost).quantize(Decimal("0.01")),
    )
