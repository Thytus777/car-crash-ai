"""Vision LLM prompts for damage detection and severity scoring.

Three zone-specific prompts replace the single broad prompt, reducing missed
damage that gets overlooked when the model scans the full component list at once.
"""

_SEVERITY_GUIDE = """\
severity: float from 0.0 to 1.0 where:
  - 0.0-0.1: cosmetic only (light scratch, scuff)
  - 0.1-0.3: minor (small dent, paint chip, repairable)
  - 0.3-0.6: moderate (significant dent, crack, replacement recommended)
  - 0.6-0.8: severe (large deformation, shattered, replacement required)
  - 0.8-1.0: destroyed (component non-functional/missing)"""

_JSON_SHAPE = """\
Return ONLY a valid JSON array (empty array [] if nothing is damaged):
[
  {
    "component": "<component_name>",
    "damage_type": "<scratch|dent|crack|shatter|crush|deformation|missing>",
    "severity": 0.0,
    "description": "<brief description>"
  }
]"""

# --- Zone component lists ---

FRONT_ZONE_COMPONENTS = [
    "front_bumper", "hood", "grille",
    "headlight_left", "headlight_right",
    "fender_front_left", "fender_front_right",
    "windshield_front",
    "a_pillar_left", "a_pillar_right",
]

REAR_ZONE_COMPONENTS = [
    "rear_bumper", "trunk",
    "taillight_left", "taillight_right",
    "quarter_panel_left", "quarter_panel_right",
    "windshield_rear",
]

SIDE_ZONE_COMPONENTS = [
    "door_front_left", "door_front_right",
    "door_rear_left", "door_rear_right",
    "mirror_left", "mirror_right",
    "rocker_panel_left", "rocker_panel_right",
    "b_pillar_left", "b_pillar_right",
    "roof",
    "wheel_front_left", "wheel_front_right",
    "wheel_rear_left", "wheel_rear_right",
]

ALL_ZONES = {
    "front": FRONT_ZONE_COMPONENTS,
    "rear": REAR_ZONE_COMPONENTS,
    "side": SIDE_ZONE_COMPONENTS,
}

# Kept for backwards-compatible single-pass use
from app.models.damage import STANDARD_COMPONENTS as _ALL
_COMPONENT_LIST = ", ".join(_ALL)

DAMAGE_ASSESSMENT_PROMPT = f"""\
Analyze the provided images of a damaged vehicle. Identify ALL visible damage.

For each damaged component, provide:
- component: use ONLY names from this list: [{_COMPONENT_LIST}]
- damage_type: one of [scratch, dent, crack, shatter, crush, deformation, missing]
- {_SEVERITY_GUIDE}
- description: brief description of the damage observed

{_JSON_SHAPE}
"""


def build_zone_prompt(zone: str, components: list[str]) -> str:
    """Build a focused prompt for a specific vehicle zone."""
    component_list = ", ".join(components)
    return f"""\
Carefully examine these vehicle images and focus ONLY on the {zone.upper()} ZONE.
Look specifically for damage on these components: [{component_list}].
Ignore all other parts of the vehicle.

For each damaged component from the list above, provide:
- component: exact name from [{component_list}]
- damage_type: one of [scratch, dent, crack, shatter, crush, deformation, missing]
- {_SEVERITY_GUIDE}
- description: brief description of the specific damage you observe

If none of these components are damaged, return an empty array.

{_JSON_SHAPE}
"""
