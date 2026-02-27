"""Vision LLM prompt for vehicle identification."""

VEHICLE_ID_PROMPT = """\
Analyze the provided images of a vehicle. Identify the vehicle with the
following details. Return ONLY valid JSON, no other text.

{{
  "make": "string (manufacturer, e.g. Toyota)",
  "model": "string (e.g. Camry)",
  "year": integer (approximate year),
  "body_style": "string (sedan, SUV, truck, coupe, hatchback, van, wagon)",
  "color": "string",
  "confidence": float 0.0-1.0 (how confident you are in this identification)
}}
"""
