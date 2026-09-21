# Car Crash Damage Detection & Assessment AI — Project Plan

## Overview

An AI-powered system that accepts multiple images of a vehicle after an accident and produces a complete damage assessment report including vehicle identification, per-component damage severity, repair/replace recommendations, and cost estimates.

---

## High-Level Flow

```
User uploads images
        │
        ▼
┌─────────────────────┐
│  Image Preprocessing │  ← validate, resize, normalize
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ Vehicle Identification│  ← AI detection OR user prompt fallback
│ (make, model, year)  │
└────────┬────────────┘
         │
         ▼
┌─────────────────────────┐
│ Damage Detection &       │
│ Component Classification │  ← per-component severity 0.0–1.0
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Repair / Replace Logic   │  ← severity > 0.3 → replace; ≤ 0.3 → repair
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Cost Estimation          │  ← part prices + labor estimates
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Report Generation        │  ← structured JSON + human-readable PDF/HTML
└─────────────────────────┘
```

---

## 1. Image Input & Preprocessing

**What it does:** Accept 1–10 images of the damaged vehicle (front, rear, sides, close-ups).

**Details:**
- Supported formats: JPEG, PNG, HEIC (convert HEIC → JPEG on ingest)
- Validate: minimum resolution (640×480), file size limits (≤ 20 MB each)
- Resize to a consistent resolution for the model (e.g., 1024×1024)
- Store originals in cloud storage (S3/Azure Blob) for audit trail

**Tech:** Python with Pillow / OpenCV for preprocessing.

---

## 2. Vehicle Identification

**What it does:** Determine the make, model, year, and trim of the vehicle.

**Approach — Two Paths (try AI first, fall back to user):**

### Path A — Vision AI Auto-Detection
- Send one or more clear images to a Vision LLM (GPT-4 Vision, Claude Vision, or Gemini)
- Prompt: *"Identify the make, model, approximate year, and body style of this vehicle."*
- Parse structured response (JSON)
- Confidence threshold: if the model returns confidence < 0.7, fall back to Path B

### Path B — User Prompt Fallback
- Ask the user: "We couldn't confidently identify your vehicle. Please provide: Make, Model, Year"
- Validate against a known vehicle database (NHTSA VIN decoder API is free, or use a static dataset)

**Why this matters:** Vehicle identity determines part catalog, part prices, and labor rates.

**Data sources for vehicle data:**
| Source | Cost | Notes |
|--------|------|-------|
| NHTSA VIN Decoder API | Free | Decode VIN → make/model/year |
| CarMD API | Paid | Vehicle data + common repairs |
| Static dataset (Kaggle) | Free | Offline reference |

---

## 3. Damage Detection & Severity Scoring

**What it does:** Identify which components are damaged and score severity from 0.0 (no damage) to 1.0 (destroyed).

### Components to Detect
| Zone | Components |
|------|-----------|
| Front | Front bumper, hood, grille, headlights (L/R), fenders (L/R), windshield |
| Side | Doors (FL/FR/RL/RR), side mirrors (L/R), rocker panels, quarter panels |
| Rear | Rear bumper, trunk/tailgate, taillights (L/R), rear windshield |
| Structural | Frame, A/B/C pillars, roof, undercarriage |
| Other | Wheels/tires, suspension (visible), exhaust |

### Approach — Vision LLM (Chosen)

Use GPT-4 Vision / Claude Vision / Gemini with structured output prompting:

```
Prompt: "Analyze these images of a damaged vehicle. For each damaged
component, provide:
- component_name (from standard list)
- damage_type (scratch, dent, crack, shatter, crush, deformation)
- severity (0.0 to 1.0)
- description (brief)
Return as JSON array."
```

**Pros:** No training data needed, handles varied angles, produces structured output.
**Cons:** API costs (~$0.01–0.05 per image), non-deterministic, needs prompt tuning.

> **Future upgrade path:** Once we have enough labeled data from real assessments, train a
> YOLOv8 model for fast damage region detection and feed those crops into the Vision LLM
> for detailed severity scoring (hybrid approach).

### Severity Scale & Recommendations

| Severity | Description | Recommendation |
|----------|-------------|----------------|
| 0.0–0.1 | Cosmetic (light scratch, scuff) | Minor repair / buff out |
| 0.1–0.3 | Minor (small dent, paint chip) | Repair (PDR, touch-up paint) |
| 0.3–0.6 | Moderate (significant dent, crack) | **Replace recommended** |
| 0.6–0.8 | Severe (large deformation, shattered) | **Replace required** |
| 0.8–1.0 | Destroyed (component non-functional) | **Replace required** |

> **Decision threshold:** severity > 0.3 → recommend replacement; ≤ 0.3 → recommend repair.

---

## 4. Cost Estimation

**What it does:** Estimate the total repair cost broken into: part cost + labor cost.

### Part Replacement Pricing — Live Web Search Pipeline (Chosen)

No single parts database covers every vehicle. Instead, we search the web in real-time,
fetch the top results, and use AI to extract structured pricing data.

#### Architecture: Search → Fetch → Extract

```
Backend receives:  "Toyota Corolla 2018 front bumper"
        │
        ▼
┌──────────────────────────┐
│ Step 1 — Search API       │  SerpAPI / Google Custom Search / Bing Search API
│                           │  Query: "{year} {make} {model} {component} price buy"
│                           │  Returns: top 5 result URLs + snippets
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ Step 2 — Fetch & Clean    │  httpx GET each result URL
│                           │  Strip scripts/styles with BeautifulSoup or trafilatura
│                           │  Extract: title, price-like text, product descriptions
│                           │  Timeout: 5s per page, skip failures
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ Step 3 — AI Price Extract │  Send cleaned snippets to LLM
│                           │  "Extract the product price, currency, and whether
│                           │   it's OEM or aftermarket from this text."
│                           │  Returns structured JSON per result
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ Step 4 — Aggregate        │  Collect prices from all results
│                           │  Return: { low, avg, high, currency, sources[] }
│                           │  Cache result for 24 hours
└──────────────────────────┘
```

#### Search API Options

| Provider | Free Tier | Paid | Notes |
|----------|-----------|------|-------|
| **SerpAPI** | 100 searches/mo | $50/mo for 5,000 | Best structured results, Google/Bing |
| **Google Custom Search API** | 100/day free | $5 per 1,000 | Requires Custom Search Engine setup |
| **Bing Web Search API** | 1,000/mo free | Pay-as-you-go | Via Azure, good quality |
| **SearXNG** (self-hosted) | Unlimited | Free (self-host) | Aggregates multiple engines, no API key |

> **Recommendation:** Start with **SerpAPI** (100 free/mo is enough for development).
> For production scale, switch to **Bing Search API** (cheapest at volume) or
> self-host **SearXNG** for zero per-query cost.

#### Page Fetching & Cleaning

```python
# Fetch with httpx (async, fast)
async with httpx.AsyncClient(timeout=5.0) as client:
    response = await client.get(url, follow_redirects=True)

# Clean with trafilatura (best for article/product page extraction)
import trafilatura
clean_text = trafilatura.extract(response.text)

# Or BeautifulSoup for more control
from bs4 import BeautifulSoup
soup = BeautifulSoup(response.text, "html.parser")
for tag in soup(["script", "style", "nav", "footer"]):
    tag.decompose()
text = soup.get_text(separator="\n", strip=True)
```

#### AI Price Extraction Prompt

```
Given the following product page text from {site_domain}, extract pricing info
for the car part: {year} {make} {model} {component}.

Text:
---
{cleaned_text[:2000]}
---

Return ONLY valid JSON:
{
  "price": <number or null if not found>,
  "currency": "<3-letter code, e.g. AUD, USD>",
  "part_type": "<oem | aftermarket | unknown>",
  "in_stock": <true | false | null>,
  "product_name": "<exact product name from page>",
  "confidence": <0.0 to 1.0>
}
```

#### Caching & Fallback

- **Cache:** Store search results + extracted prices in the database for 24 hours
  - Key: `{make}_{model}_{year}_{component}`
  - Avoids redundant API calls for the same vehicle/part combo
- **Fallback:** If live search fails (API down, no results, all extractions low-confidence):
  - Fall back to the static reference database (CSV of average prices)
  - Flag the estimate as "based on reference data, not live pricing"

#### Static Fallback Database

- File: `backend/app/data/parts_prices.csv`
- Schema: `make,model,year_start,year_end,component,avg_price,currency,source,last_updated`
- Covers top 30 vehicles × 20 common parts = 600 rows
- Updated manually as a baseline safety net

### Labor Cost Estimation

Labor is typically estimated as: `labor_hours × hourly_rate`

- **Labor hours:** Use flat-rate labor guides (e.g., Mitchell, ALLDATA) that define standard hours per repair operation
- **Hourly rate:** Varies by region ($50–$150/hr in the US). Can use:
  - User-input location → regional average
  - Bureau of Labor Statistics (BLS) data for auto body repair wages
  - Default to national average (~$75/hr) for MVP

**Example estimate structure:**
```json
{
  "vehicle": { "make": "Toyota", "model": "Camry", "year": 2020 },
  "damages": [
    {
      "component": "front_bumper",
      "severity": 0.75,
      "recommendation": "replace",
      "part_cost": { "low": 180, "avg": 250, "high": 350 },
      "labor_hours": 3.5,
      "labor_cost": 262.50,
      "total_estimate": 512.50
    },
    {
      "component": "left_headlight",
      "severity": 0.85,
      "recommendation": "replace",
      "part_cost": { "low": 120, "avg": 200, "high": 400 },
      "labor_hours": 1.0,
      "labor_cost": 75.00,
      "total_estimate": 275.00
    }
  ],
  "totals": {
    "parts_total": 450.00,
    "labor_total": 337.50,
    "grand_total": 787.50
  }
}
```

---

## 5. Tech Stack (Recommended)

| Layer | Technology | Why |
|-------|-----------|-----|
| **Backend API** | Python + FastAPI | Best ML/AI ecosystem, async, auto-docs |
| **AI / Vision** | OpenAI GPT-4 Vision | Vehicle ID + damage detection + price extraction |
| **Search API** | SerpAPI (dev) → Bing Search API (prod) | Legal web search for live part prices |
| **HTML Parsing** | trafilatura + BeautifulSoup | Clean web pages for AI extraction |
| **HTTP Client** | httpx (async) | Fetch search results and product pages |
| **Database** | PostgreSQL + SQLAlchemy | Structured data, price cache, estimates |
| **Object Storage** | AWS S3 or Azure Blob | Store uploaded images |
| **Frontend** | Next.js (React) or Streamlit (quick MVP) | Streamlit for internal tool; Next.js for customer-facing |
| **Task Queue** | Celery + Redis | Async image processing + price lookups |
| **Deployment** | Docker + AWS ECS or Railway | Containerized, scalable |

---

## 6. Project Phases

### Phase 1 — MVP (4–6 weeks)
- [ ] Image upload endpoint (FastAPI)
- [ ] Vehicle identification via Vision LLM
- [ ] Damage detection via Vision LLM with structured output
- [ ] Severity scoring + repair/replace recommendations
- [ ] Live price search pipeline (SerpAPI → fetch → AI extract)
- [ ] Static parts price CSV as fallback
- [ ] Simple labor cost estimation (national average rate)
- [ ] Basic Streamlit or HTML frontend
- [ ] JSON report output

### Phase 2 — Enhanced (6–8 weeks)
- [ ] Price result caching (24hr TTL in PostgreSQL)
- [ ] Regional labor rate adjustment
- [ ] PDF report generation
- [ ] User accounts + estimate history
- [ ] Image annotation (highlight damaged areas on the image)
- [ ] VIN decoder integration for precise vehicle identification

### Phase 3 — Production (8–12 weeks)
- [ ] Custom YOLO model trained on car damage dataset
- [ ] Hybrid approach (YOLO detection + LLM assessment)
- [ ] Multi-language support
- [ ] Insurance-grade reporting format
- [ ] Admin dashboard for price database management
- [ ] A/B testing for model accuracy improvements
- [ ] Mobile-responsive frontend or dedicated mobile app

---

## 7. Key Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Vision LLM inaccuracy on severity | Wrong cost estimates | Calibrate with real assessor data; allow user override |
| Part price data staleness | Incorrect quotes | Refresh prices periodically; show date of last update |
| Legal liability of estimates | User relies on incorrect estimate | Add disclaimers: "Estimate only, not a quote" |
| API cost at scale | High operating cost | Migrate to custom models in Phase 3 |
| Poor image quality | Bad analysis | Validate image quality on upload; guide user on photo angles |

---

## 8. Directory Structure (Planned)

```
car-crash-ai/
├── .agents/                    # Amp agent configuration
│   ├── AGENTS.md
│   └── skills/
├── backend/
│   ├── app/
│   │   ├── main.py             # FastAPI entry point
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── upload.py   # Image upload endpoints
│   │   │   │   ├── analysis.py # Damage analysis endpoints
│   │   │   │   └── estimate.py # Cost estimation endpoints
│   │   │   └── deps.py         # Shared dependencies
│   │   ├── core/
│   │   │   ├── config.py       # App configuration
│   │   │   └── security.py     # API key management
│   │   ├── models/
│   │   │   ├── vehicle.py      # Vehicle data models
│   │   │   ├── damage.py       # Damage assessment models
│   │   │   └── estimate.py     # Cost estimate models
│   │   ├── services/
│   │   │   ├── vehicle_id.py   # Vehicle identification service
│   │   │   ├── damage_detect.py# Damage detection service
│   │   │   ├── cost_estimate.py# Cost estimation service
│   │   │   └── image_proc.py   # Image preprocessing
│   │   └── data/
│   │       └── parts_prices.csv# Static parts price reference
│   ├── tests/
│   │   ├── test_upload.py
│   │   ├── test_analysis.py
│   │   └── test_estimate.py
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                   # Next.js or Streamlit
│   ├── ...
├── ml/                         # ML training (Phase 3)
│   ├── data/
│   ├── notebooks/
│   └── train.py
├── docker-compose.yml
├── PROJECT_PLAN.md
└── README.md
```

---

## 9. Getting Started (Next Steps)

1. **Set up the Python backend** — FastAPI skeleton with image upload
2. **Integrate a Vision LLM** — Start with OpenAI GPT-4 Vision for both vehicle ID and damage detection
3. **Build the prompt engineering** — Iterate on prompts to get reliable structured JSON output
4. **Create the static parts database** — Research prices for common vehicles/parts
5. **Build a minimal frontend** — Streamlit for rapid iteration
6. **Test with real crash images** — Validate accuracy, tune severity thresholds
