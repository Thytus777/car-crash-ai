"""Cost estimation service — orchestrates live price search + labor calculation."""

import asyncio
import logging
from collections.abc import Sequence
from decimal import Decimal

from app.core.config import settings
from app.core.errors import AppError
from app.core.llm import generate
from app.core.tracing import traced
from app.models.damage import DamageItem
from app.models.estimate import CostEstimate, PricingMethod, ReportTotals
from app.models.llm_outputs import PriceEstimate
from app.models.vehicle import Vehicle
from app.prompts import render
from app.services.labor import get_labor_cost
from app.services.price_search import search_part_prices
from app.services.static_prices import lookup_static_price

logger = logging.getLogger(__name__)


_CENT = Decimal("0.01")


def compute_totals(estimates: Sequence[CostEstimate]) -> ReportTotals:
    """Sum a report: unpriced parts are listed and excluded; labour always counts."""
    parts = sum(
        (e.part_cost_avg for e in estimates if e.part_cost_avg is not None),
        Decimal("0"),
    ).quantize(_CENT)
    labor = sum((e.labor_cost for e in estimates), Decimal("0")).quantize(_CENT)
    return ReportTotals(
        parts_total=parts,
        labor_total=labor,
        grand_total=(parts + labor).quantize(_CENT),
        unpriced_components=[e.component for e in estimates if e.part_cost_avg is None],
    )


@traced("stage.pricing.component")
async def estimate_cost(
    vehicle: Vehicle,
    damage: DamageItem,
) -> CostEstimate:
    """Estimate repair/replacement cost for a single damaged component."""
    labor_hours, labor_rate, labor_cost = get_labor_cost(damage.component)

    try:
        async with asyncio.timeout(settings.price_search_deadline_s):
            live_results = await search_part_prices(
                make=vehicle.make,
                model=vehicle.model,
                year=vehicle.year,
                component=damage.component,
            )
    except TimeoutError:
        logger.warning(
            "Live price search for %s exceeded %.0fs; using fallback pricing",
            damage.component,
            settings.price_search_deadline_s,
        )
        live_results = []

    pricing_method: PricingMethod
    if live_results:
        prices = [r.price for r in live_results]
        part_low = min(prices)
        part_high = max(prices)
        part_avg = (sum(prices, Decimal("0")) / len(prices)).quantize(Decimal("0.01"))
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
            estimate = await _ai_estimate_price(vehicle, damage.component)
            if estimate is None:
                return CostEstimate(
                    component=damage.component,
                    recommendation=damage.recommendation,
                    part_cost_low=None,
                    part_cost_avg=None,
                    part_cost_high=None,
                    price_sources=live_results,
                    pricing_method="unpriced",
                    labor_hours=labor_hours,
                    labor_rate=labor_rate,
                    labor_cost=labor_cost,
                    total_low=None,
                    total_avg=None,
                    total_high=None,
                )
            part_low, part_avg, part_high = estimate
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
) -> tuple[Decimal, Decimal, Decimal] | None:
    """Ask the LLM for a price range; None if it couldn't give a usable one."""
    prompt = render(
        "price_estimation",
        year=vehicle.year,
        make=vehicle.make,
        model=vehicle.model,
        component=component.replace("_", " "),
    )

    try:
        result = await generate(
            PriceEstimate,
            prompt,
            task="price_estimate",
            max_output_tokens=200,
            temperature=0.2,
        )
    except AppError as exc:
        logger.warning("AI price estimate for %s failed: %s", component, exc.detail)
        return None

    est = result.output
    low, avg, high = (
        Decimal(str(v)).quantize(Decimal("0.01"))
        for v in (est.price_low, est.price_avg, est.price_high)
    )
    logger.info(
        "AI price estimate for %s %s %d %s: $%s / $%s / $%s",
        vehicle.make,
        vehicle.model,
        vehicle.year,
        component,
        low,
        avg,
        high,
    )
    return low, avg, high
