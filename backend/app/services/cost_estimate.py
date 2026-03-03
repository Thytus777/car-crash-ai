"""Cost estimation service — orchestrates live price search + labor calculation."""

import json
import logging
from decimal import Decimal

from app.core.llm import text_completion
from app.models.damage import DamageItem
from app.models.estimate import CostEstimate
from app.models.vehicle import Vehicle
from app.prompts.price_estimation import PRICE_ESTIMATION_PROMPT
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
            pricing_method = "static_reference"
        else:
            part_low, part_avg, part_high = await _ai_estimate_price(
                vehicle, damage.component
            )
            pricing_method = "ai_estimate"

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


async def _ai_estimate_price(
    vehicle: Vehicle, component: str
) -> tuple[Decimal, Decimal, Decimal]:
    """Ask the LLM to estimate part prices when no other data is available."""
    prompt = PRICE_ESTIMATION_PROMPT.format(
        year=vehicle.year,
        make=vehicle.make,
        model=vehicle.model,
        component=component.replace("_", " "),
    )

    try:
        raw = await text_completion(prompt=prompt, max_tokens=200, temperature=0.2)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
            cleaned = cleaned.rsplit("```", 1)[0].strip()

        data = json.loads(cleaned)
        low = Decimal(str(data["price_low"])).quantize(Decimal("0.01"))
        avg = Decimal(str(data["price_avg"])).quantize(Decimal("0.01"))
        high = Decimal(str(data["price_high"])).quantize(Decimal("0.01"))
        logger.info(
            "AI price estimate for %s %s %d %s: $%s / $%s / $%s",
            vehicle.make, vehicle.model, vehicle.year, component, low, avg, high,
        )
        return low, avg, high
    except Exception:
        logger.exception("AI price estimation failed, using defaults")
        return Decimal("150.00"), Decimal("300.00"), Decimal("500.00")
