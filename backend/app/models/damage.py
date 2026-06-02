from typing import Literal

from pydantic import BaseModel, Field


class ImageQualityWarning(BaseModel):
    image_filename: str
    warning_type: Literal["blurry", "dark", "overexposed", "low_resolution"]
    message: str


class AngleGuidance(BaseModel):
    angles_detected: list[str] = Field(default_factory=list)
    angles_missing: list[str] = Field(default_factory=list)
    suggestion: str = ""

STANDARD_COMPONENTS = [
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

DamageType = Literal[
    "scratch",
    "dent",
    "crack",
    "shatter",
    "crush",
    "deformation",
    "missing",
]

Recommendation = Literal["repair", "replace"]


class DamageItem(BaseModel):
    component: str = Field(
        ..., description="Component name from standard list"
    )
    damage_type: DamageType = Field(..., description="Type of damage observed")
    severity: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Severity score (0.0 = no damage, 1.0 = destroyed)",
    )
    description: str = Field(..., description="Brief description of the damage")
    recommendation: Recommendation = Field(
        ..., description="Repair or replace recommendation"
    )


class DamageAssessment(BaseModel):
    damages: list[DamageItem] = Field(
        default_factory=list, description="List of detected damages"
    )
    image_quality_warnings: list[ImageQualityWarning] = Field(
        default_factory=list, description="Per-image quality issues detected before analysis"
    )
    angle_guidance: AngleGuidance | None = Field(
        default=None, description="Missing photo angles that would improve accuracy"
    )
    assessment_method: Literal["single_pass", "zone_pass", "consensus"] = Field(
        default="single_pass", description="Detection method used"
    )
