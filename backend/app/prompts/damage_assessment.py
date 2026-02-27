"""Vision LLM prompt for damage detection and severity scoring."""

from app.models.damage import STANDARD_COMPONENTS

_COMPONENT_LIST = ", ".join(STANDARD_COMPONENTS)

DAMAGE_ASSESSMENT_PROMPT = f"""\
Analyze the provided images of a damaged vehicle. Identify ALL visible
damage to the vehicle components.

For each damaged component, provide:
- component: use ONLY names from this list: [{_COMPONENT_LIST}]
- damage_type: one of [scratch, dent, crack, shatter, crush, deformation, missing]
- severity: float from 0.0 to 1.0 where:
  - 0.0-0.1: cosmetic only (light scratch, scuff)
  - 0.1-0.3: minor (small dent, paint chip, repairable)
  - 0.3-0.6: moderate (significant dent, crack, replacement recommended)
  - 0.6-0.8: severe (large deformation, shattered, replacement required)
  - 0.8-1.0: destroyed (component non-functional/missing)
- description: brief description of the damage observed

Return ONLY a valid JSON array, no other text:
[
  {{{{
    "component": "front_bumper",
    "damage_type": "crush",
    "severity": 0.75,
    "description": "Front bumper is crushed inward with paint transfer and cracking"
  }}}}
]
"""
