from collections.abc import Sequence
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, Field

from app.core.llm import LLMCall
from app.models.damage import DamageAssessment
from app.models.vehicle import Vehicle

# "unpriced": no price source succeeded; part costs and totals are null.
PricingMethod = Literal["live_search", "static_reference", "ai_estimate", "unpriced"]


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
    part_cost_low: Decimal | None = Field(..., decimal_places=2)
    part_cost_avg: Decimal | None = Field(..., decimal_places=2)
    part_cost_high: Decimal | None = Field(..., decimal_places=2)
    price_sources: list[PriceResult] = Field(default_factory=list)
    pricing_method: PricingMethod = Field(default="static_reference")
    labor_hours: Decimal = Field(..., decimal_places=2)
    labor_rate: Decimal = Field(..., decimal_places=2)
    labor_cost: Decimal = Field(..., decimal_places=2)
    total_low: Decimal | None = Field(..., decimal_places=2)
    total_avg: Decimal | None = Field(..., decimal_places=2)
    total_high: Decimal | None = Field(..., decimal_places=2)


class ReportTotals(BaseModel):
    parts_total: Decimal = Field(
        ..., decimal_places=2, description="Sum over priced components only"
    )
    labor_total: Decimal = Field(..., decimal_places=2)
    grand_total: Decimal = Field(..., decimal_places=2)
    unpriced_components: list[str] = Field(
        default_factory=list,
        description="Components with no part price; excluded from parts_total",
    )


AssessmentStage = Literal["image_triage", "damage_detection", "pricing", "sanity_check"]


class AssessmentIssue(BaseModel):
    """A stage that degraded without failing the whole request."""

    stage: AssessmentStage
    scope: str | None = Field(
        default=None, description="Zone or component affected, if any"
    )
    detail: str


class AssessmentMeta(BaseModel):
    """How a result was produced; ties it to exact prompts and models."""

    prompt_version: str
    models: list[str] = Field(
        default_factory=list, description="Distinct provider/model IDs that answered"
    )
    llm_calls: int = Field(0, description="Model calls made (provider attempts)")
    input_tokens: int = 0
    output_tokens: int = 0

    @classmethod
    def from_calls(cls, prompt_version: str, calls: Sequence[LLMCall]) -> Self:
        return cls(
            prompt_version=prompt_version,
            models=sorted({f"{c.provider}/{c.model}" for c in calls if c.ok}),
            llm_calls=sum(c.attempts for c in calls),
            input_tokens=sum(c.usage.input_tokens for c in calls),
            output_tokens=sum(c.usage.output_tokens for c in calls),
        )


class AssessmentReport(BaseModel):
    meta: AssessmentMeta | None = None
    status: Literal["complete", "partial"] = Field(
        default="complete",
        description="'partial' when any stage degraded; see issues",
    )
    issues: list[AssessmentIssue] = Field(default_factory=list)
    estimate_id: int | None = Field(
        default=None,
        description=(
            "ID of the saved estimate (for /estimates and /report), "
            "or null if the result could not be saved"
        ),
    )
    vehicle: Vehicle
    damage_assessment: DamageAssessment
    cost_estimates: list[CostEstimate] = Field(default_factory=list)
    totals: ReportTotals
    assessment_warnings: list[str] = Field(
        default_factory=list,
        description=(
            "Sanity-check flags — items the AI flagged as uncertain or inconsistent"
        ),
    )
    disclaimer: str = Field(
        default="This is an estimate only, not a quote. "
        "Actual repair costs may vary based on local labor rates, "
        "parts availability, and shop assessment."
    )
