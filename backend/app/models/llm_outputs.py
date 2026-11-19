"""Schemas for every LLM output: the single source of truth for their JSON.

Each model is passed to the provider as its native structured-output schema
and is also used to validate the reply, so the prompt, the provider
constraint and our parsing can't drift apart. Keep field names and
descriptions in sync with the prompt text that asks for them.
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.damage import DamageType

# Literal mirrors app.models.damage.STANDARD_COMPONENTS; a test keeps them equal.
Component = Literal[
    "front_bumper",
    "rear_bumper",
    "hood",
    "trunk",
    "grille",
    "headlight_left",
    "headlight_right",
    "taillight_left",
    "taillight_right",
    "fender_front_left",
    "fender_front_right",
    "door_front_left",
    "door_front_right",
    "door_rear_left",
    "door_rear_right",
    "mirror_left",
    "mirror_right",
    "quarter_panel_left",
    "quarter_panel_right",
    "rocker_panel_left",
    "rocker_panel_right",
    "windshield_front",
    "windshield_rear",
    "roof",
    "a_pillar_left",
    "a_pillar_right",
    "b_pillar_left",
    "b_pillar_right",
    "wheel_front_left",
    "wheel_front_right",
    "wheel_rear_left",
    "wheel_rear_right",
]


class _Output(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImageTriage(_Output):
    shows_vehicle: bool = Field(description="At least one image shows a road vehicle")
    usable: bool = Field(description="At least one image allows judging damage")
    reason: str = Field(description="One sentence for the uploader")


class VehicleIdentification(_Output):
    make: str = Field(description="Manufacturer, e.g. Toyota")
    model: str = Field(description="Model, e.g. Camry")
    year: int | None = Field(description="Approximate model year, null if unknown")
    body_style: str | None = Field(
        description="sedan, SUV, truck, coupe, hatchback, van or wagon"
    )
    color: str | None = Field(description="Exterior colour")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in the ID")


class DamageFinding(_Output):
    component: Component
    damage_type: DamageType
    severity: float = Field(ge=0.0, le=1.0)
    description: str


class DamageFindings(_Output):
    damages: list[DamageFinding] = Field(
        description="One entry per damaged component; empty if none"
    )


class PriceExtraction(_Output):
    price: float | None = Field(ge=0.0, description="Part price, null if not found")
    currency: str = Field(description="3-letter currency code")
    part_type: Literal["oem", "aftermarket", "unknown"]
    in_stock: bool | None
    product_name: str
    confidence: float = Field(ge=0.0, le=1.0)


class PriceEstimate(_Output):
    price_low: float = Field(ge=0.0, description="Lowest realistic aftermarket price")
    price_avg: float = Field(ge=0.0, description="Typical price")
    price_high: float = Field(ge=0.0, description="OEM / dealer price")
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if not self.price_low <= self.price_avg <= self.price_high:
            raise ValueError("expected price_low <= price_avg <= price_high")
        return self


class SanityReview(_Output):
    looks_reasonable: bool
    warnings: list[str] = Field(description="One entry per concern; empty if none")
