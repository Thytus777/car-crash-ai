---
name: managing-costs
description: "Handles parts pricing data, labor rate estimation, and cost calculation logic. Use when working on the cost estimation module or parts price database."
---

# Cost Estimation for Car Crash AI

## Cost Formula

```
component_total = part_cost + (labor_hours × hourly_rate)
grand_total = sum(component_totals) + paint_and_materials_estimate
```

## Parts Pricing — Live Web Search Pipeline

No MCP needed. The backend runs its own Search → Fetch → Extract pipeline.

### Pipeline Steps

1. **Search** — Call a search API (SerpAPI / Bing / Google Custom Search) with query:
   `"{year} {make} {model} {component} price buy"`
   Returns top 5 URLs + snippets.

2. **Fetch & Clean** — `httpx` GET each URL (5s timeout, skip failures).
   Clean HTML with `trafilatura` or `BeautifulSoup` (strip scripts/styles/nav/footer).

3. **AI Extract** — Send cleaned text (max 2000 chars per page) to LLM with extraction prompt.
   Returns: `{ price, currency, part_type, in_stock, product_name, confidence }`

4. **Aggregate** — Collect all extracted prices, filter by confidence ≥ 0.5.
   Return: `{ low: min, avg: mean, high: max, currency, sources[] }`

5. **Cache** — Store result in DB for 24 hours, keyed by `{make}_{model}_{year}_{component}`.

### Key Libraries
- `httpx` — async HTTP client for fetching pages
- `trafilatura` — HTML → clean text extraction
- `beautifulsoup4` — fallback HTML parser
- Search API client: `serpapi` package or raw HTTP to Bing/Google

### Fallback
If live search fails (API down, no results, low-confidence extractions):
- Fall back to static CSV: `backend/app/data/parts_prices.csv`
- Flag estimate as "based on reference data, not live pricing"

### Static Fallback Database
- File: `backend/app/data/parts_prices.csv`
- Schema: `make,model,year_start,year_end,component,avg_price,currency,source,last_updated`
- Covers top 30 vehicles × 20 common parts = 600 rows

## Labor Estimation

### Default Rates
| Repair Type | Labor Hours (typical) |
|------------|----------------------|
| Bumper replace | 3.0–4.0 hrs |
| Bumper repair (minor) | 1.0–2.0 hrs |
| Fender replace | 3.0–5.0 hrs |
| Door replace | 4.0–6.0 hrs |
| Hood replace | 2.0–3.0 hrs |
| Headlight replace | 0.5–1.5 hrs |
| Mirror replace | 0.5–1.0 hrs |
| Windshield replace | 1.5–2.5 hrs |
| Paint per panel | 2.0–4.0 hrs |
| Quarter panel replace | 6.0–10.0 hrs |

### Hourly Rate
- MVP default: **$75/hr** (US national average for auto body)
- Phase 2: regional adjustment based on user ZIP code
- Source: Bureau of Labor Statistics (BLS) Occupational Employment data

## Money Handling Rules
- All monetary values stored as `Decimal` with 2 decimal places
- Never use `float` for money
- Display as: `$1,234.56`
- Internal calculations in cents (integer) if precision issues arise

## Output Schema
```python
class PriceResult(BaseModel):
    price: Decimal
    currency: str  # "USD", "AUD", etc.
    part_type: Literal["oem", "aftermarket", "unknown"]
    in_stock: bool | None
    product_name: str
    source_url: str
    confidence: float

class CostEstimate(BaseModel):
    component: str
    recommendation: Literal["repair", "replace"]
    part_cost_low: Decimal
    part_cost_avg: Decimal
    part_cost_high: Decimal
    price_sources: list[PriceResult]
    pricing_method: Literal["live_search", "static_reference"]
    labor_hours: Decimal
    labor_rate: Decimal
    labor_cost: Decimal
    total_low: Decimal
    total_avg: Decimal
    total_high: Decimal
```
