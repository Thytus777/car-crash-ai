---
name: writing-prompts
description: "Creates and refines Vision LLM prompts for vehicle identification and damage assessment. Use when building or tuning AI prompts for image analysis."
---

# Vision LLM Prompt Engineering for Car Crash AI

## Prompt Design Principles

1. **Always request structured JSON output** — include the exact schema in the prompt
2. **Be explicit about the severity scale** — define 0.0–1.0 with examples
3. **Provide the component list** — so the model uses consistent naming
4. **Include few-shot examples** — show the expected output format
5. **Set boundaries** — tell the model what NOT to do (e.g., don't diagnose mechanical issues from photos)

## Standard Component Names

Use these exact names in all prompts and outputs:

```
front_bumper, rear_bumper, hood, trunk, grille,
headlight_left, headlight_right, taillight_left, taillight_right,
fender_front_left, fender_front_right,
door_front_left, door_front_right, door_rear_left, door_rear_right,
mirror_left, mirror_right,
quarter_panel_left, quarter_panel_right,
rocker_panel_left, rocker_panel_right,
windshield_front, windshield_rear,
roof, a_pillar_left, a_pillar_right, b_pillar_left, b_pillar_right,
wheel_front_left, wheel_front_right, wheel_rear_left, wheel_rear_right
```

## Prompt Templates

### Vehicle Identification Prompt
```
Analyze the provided images of a vehicle. Identify the vehicle with the
following details. Return ONLY valid JSON, no other text.

{
  "make": "string (manufacturer, e.g. Toyota)",
  "model": "string (e.g. Camry)",
  "year": "integer (approximate year or year range)",
  "body_style": "string (sedan, SUV, truck, coupe, hatchback, van, wagon)",
  "color": "string",
  "confidence": "float 0.0-1.0 (how confident you are in this identification)"
}
```

### Damage Assessment Prompt
```
Analyze the provided images of a damaged vehicle. Identify ALL visible
damage to the vehicle components.

For each damaged component, provide:
- component: use ONLY names from this list: [front_bumper, rear_bumper, hood, ...]
- damage_type: one of [scratch, dent, crack, shatter, crush, deformation, missing]
- severity: float from 0.0 to 1.0 where:
  - 0.0-0.1: cosmetic only (light scratch, scuff)
  - 0.1-0.3: minor (small dent, paint chip, repairable)
  - 0.3-0.6: moderate (significant dent, crack, replacement recommended)
  - 0.6-0.8: severe (large deformation, shattered, replacement required)
  - 0.8-1.0: destroyed (component non-functional/missing)
- description: brief description of the damage observed

Return ONLY valid JSON array, no other text:
[
  {
    "component": "front_bumper",
    "damage_type": "crush",
    "severity": 0.75,
    "description": "Front bumper is crushed inward with paint transfer and cracking"
  }
]
```

## Prompt Storage Convention

Store prompts in `backend/app/prompts/`:
```
prompts/
├── __init__.py
├── vehicle_identification.py   # VEHICLE_ID_PROMPT constant
└── damage_assessment.py        # DAMAGE_ASSESSMENT_PROMPT constant
```

Each file exports a string constant. Prompts should be parameterizable using `.format()` or f-strings for dynamic parts (like the component list).

## Testing Prompts

- Use saved example images with known damage to validate prompt output
- Check that JSON parses correctly
- Check severity values are in [0.0, 1.0]
- Check component names match the standard list
- Log prompt + response pairs for iterative improvement
