"""LLM prompt for extracting part prices from cleaned web page text."""

PRICE_EXTRACTION_PROMPT = """\
Given the following product page text from {site_domain}, extract pricing info
for the car part: {year} {make} {model} {component}.

Text:
---
{cleaned_text}
---

Return ONLY valid JSON:
{{
  "price": <number or null if not found>,
  "currency": "<3-letter code, e.g. AUD, USD>",
  "part_type": "<oem | aftermarket | unknown>",
  "in_stock": <true | false | null>,
  "product_name": "<exact product name from page>",
  "confidence": <0.0 to 1.0>
}}
"""
