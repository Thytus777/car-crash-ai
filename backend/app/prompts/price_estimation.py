"""LLM prompt for AI-based part price estimation when no live/static data exists."""

PRICE_ESTIMATION_PROMPT = """\
Estimate the replacement part price for the following vehicle component.
Use your knowledge of typical automotive parts pricing.

Vehicle: {year} {make} {model}
Component: {component}

Return ONLY valid JSON:
{{
  "price_low": <number — lowest realistic aftermarket price in USD>,
  "price_avg": <number — typical average price in USD>,
  "price_high": <number — OEM/dealer price in USD>,
  "confidence": <0.0 to 1.0 — how confident you are in these estimates>
}}

Guidelines:
- Consider the vehicle's market segment (economy, mid-range, luxury, exotic)
- Aftermarket parts are typically 30-60% cheaper than OEM
- Prices should reflect the US market in 2025
- Common components (bumpers, mirrors) have well-known price ranges
- Rare or luxury vehicle parts cost significantly more
"""
