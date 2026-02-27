from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.models.damage import DamageAssessment
from app.models.vehicle import Vehicle


class PriceResult(BaseModel):
    price: Decimal = Field(..., decimal_places=2, description="Part price")
    currency: str = Field(default="USD", description="3-letter currency code")
    part_type: Literal["oem", "aftermarket", "unknown"] = Field(
        default="unknown", description="OEM or aftermarket"
    )
    in_stock: bool | None = Field(default=None, description="Availability")
    product_name: str = Field(default="", description="Product name from source")
    source_url: str = Field(default="", description="URL where price was found")
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Extraction confidence"
    )


class CostEstimate(BaseModel):
    component: str
    recommendation: Literal["repair", "replace"]
    part_cost_low: Decimal = Field(..., decimal_places=2)
    part_cost_avg: Decimal = Field(..., decimal_places=2)
    part_cost_high: Decimal = Field(..., decimal_places=2)
    price_sources: list[PriceResult] = Field(default_factory=list)
    pricing_method: Literal["live_search", "static_reference"] = Field(
        default="static_reference"
    )
    labor_hours: Decimal = Field(..., decimal_places=2)
    labor_rate: Decimal = Field(..., decimal_places=2)
    labor_cost: Decimal = Field(..., decimal_places=2)
    total_low: Decimal = Field(..., decimal_places=2)
    total_avg: Decimal = Field(..., decimal_places=2)
    total_high: Decimal = Field(..., decimal_places=2)


class ReportTotals(BaseModel):
    parts_total: Decimal = Field(..., decimal_places=2)
    labor_total: Decimal = Field(..., decimal_places=2)
    grand_total: Decimal = Field(..., decimal_places=2)


class AssessmentReport(BaseModel):
    vehicle: Vehicle
    damage_assessment: DamageAssessment
    cost_estimates: list[CostEstimate] = Field(default_factory=list)
    totals: ReportTotals
    disclaimer: str = Field(
        default="This is an estimate only, not a quote. "
        "Actual repair costs may vary based on local labor rates, "
        "parts availability, and shop assessment."
    )
