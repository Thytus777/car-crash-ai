"""Ground-truth label format: evals/dataset/<case_id>/label.json.

Labels are written by a person (see evals/LABELLING.md), never generated.
This module is the single source of truth for their shape. The validator
(``python -m evals validate``) and the eval runner both parse them through it.
"""

import datetime as dt
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.damage import DamageType
from app.models.llm_outputs import Component

CASE_ID_PATTERN = r"^[a-z0-9][a-z0-9_-]{2,63}$"

SeverityLevel = Literal["cosmetic", "minor", "moderate", "severe", "destroyed"]

# Upper bound of each level on the model's 0-1 severity scale. Mirrors the
# severity guide the damage prompts give the model (prompts/<v>/_severity_guide.md).
SEVERITY_UPPER_BOUNDS: tuple[tuple[float, SeverityLevel], ...] = (
    (0.1, "cosmetic"),
    (0.3, "minor"),
    (0.6, "moderate"),
    (0.8, "severe"),
    (1.0, "destroyed"),
)

Tag = Literal[
    "night",
    "glare",
    "rain",
    "partial_view",
    "close_up",
    "undamaged",
    "non_vehicle",
    "multiple_vehicles",
    "prompt_injection",
]


def severity_level(score: float) -> SeverityLevel:
    """Map a 0-1 model severity onto the labelled level it falls in."""
    for upper, level in SEVERITY_UPPER_BOUNDS:
        if score <= upper:
            return level
    return "destroyed"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ImageRef(_Strict):
    file: str = Field(pattern=r"^[A-Za-z0-9._-]+\.(jpg|jpeg|png|webp)$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source: str = Field(min_length=1, description="URL, dataset name, or 'own photo'")
    licence: str = Field(min_length=1, description="e.g. CC-BY-4.0, CC0, own, unknown")
    redistributable: bool = Field(
        description="True: committed under images/. False: kept in evals/local_images/"
    )


class ExpectedTriage(_Strict):
    shows_vehicle: bool
    usable: bool


class VehicleLabel(_Strict):
    make: str
    model: str
    year: int | None = None


class LabelledDamage(_Strict):
    component: Component
    severity: SeverityLevel
    damage_type: DamageType | None = None


class CostRange(_Strict):
    currency: Literal["USD", "AUD"]
    low: Decimal = Field(ge=0, decimal_places=2)
    high: Decimal = Field(ge=0, decimal_places=2)
    basis: Literal["repair_quote", "insurer_assessment", "labeller_estimate"]

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.low > self.high:
            raise ValueError("cost.low must be <= cost.high")
        return self


class CaseLabel(_Strict):
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    images: list[ImageRef] = Field(min_length=1, max_length=10)
    triage: ExpectedTriage
    vehicle: VehicleLabel | None = None
    damages: list[LabelledDamage] = Field(
        description="Every visibly damaged component; empty means undamaged"
    )
    cost: CostRange | None = Field(
        default=None, description="Reference repair cost, if a trustworthy one exists"
    )
    tags: list[Tag] = Field(default_factory=list)
    labeller: str = Field(min_length=1)
    labelled_on: dt.date
    notes: str = ""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        components = [d.component for d in self.damages]
        if len(components) != len(set(components)):
            raise ValueError("each component may be labelled at most once")
        assessable = self.triage.shows_vehicle and self.triage.usable
        if not assessable and (self.damages or self.cost):
            raise ValueError("cases that fail triage carry no damages or cost")
        if ("undamaged" in self.tags) != (assessable and not self.damages):
            raise ValueError(
                "tag 'undamaged' iff the vehicle is assessable and has no damages"
            )
        if "non_vehicle" in self.tags and self.triage.shows_vehicle:
            raise ValueError("tag 'non_vehicle' requires triage.shows_vehicle = false")
        files = [i.file for i in self.images]
        if len(files) != len(set(files)):
            raise ValueError("image file names must be unique within a case")
        return self


class Manifest(_Strict):
    """evals/dataset/manifest.json"""

    version: str = Field(
        pattern=r"^\d+\.\d+\.\d+$", description="Bump whenever labels change"
    )
    smoke: list[str] = Field(
        default_factory=list,
        description="Case IDs run in CI; all of their images must be redistributable",
    )
