# Car Crash AI — Learning & Concepts Guide

Everything you need to understand about the technologies, patterns, and decisions used in this project.

---

## Table of Contents

1. [Python & FastAPI Backend](#1-python--fastapi-backend)
2. [Pydantic & Data Validation](#2-pydantic--data-validation)
3. [Vision LLM Integration (Multi-Provider)](#3-vision-llm-integration-multi-provider)
4. [Prompt Engineering for Structured Output](#4-prompt-engineering-for-structured-output)
5. [Image Processing with Pillow](#5-image-processing-with-pillow)
6. [Live Price Search Pipeline](#6-live-price-search-pipeline)
7. [Cost Estimation Logic](#7-cost-estimation-logic)
8. [Streamlit Frontend](#8-streamlit-frontend)
9. [Async Programming (asyncio)](#9-async-programming-asyncio)
10. [Environment & Configuration](#10-environment--configuration)
11. [Testing with pytest](#11-testing-with-pytest)
12. [AI Model Selection & Cost Guide](#12-ai-model-selection--cost-guide)

---

## 1. Python & FastAPI Backend

### What is FastAPI?
FastAPI is a modern Python web framework for building APIs. It's built on top of Starlette (for async web handling) and Pydantic (for data validation). It automatically generates interactive API documentation (Swagger UI) at `/docs`.

### How we use it

**Entry point** — `backend/app/main.py`:
```python
from fastapi import FastAPI

app = FastAPI(title="Car Crash AI", version="0.1.0")

@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
```

**Key concepts used:**
- **Routers** — We split endpoints into separate files (`upload.py`, `analysis.py`, `estimate.py`) and mount them with `app.include_router(router, prefix="/api/v1")`
- **CORS middleware** — Allows the Streamlit frontend (port 8501) to call the backend API (port 8000)
- **Async handlers** — All route handlers use `async def` because our AI calls are I/O-bound (waiting on OpenAI API)
- **Dependency injection** — FastAPI's `Depends()` for shared dependencies

### Why FastAPI over Flask/Django?
- Native async support (critical for calling external APIs like OpenAI)
- Automatic request/response validation via Pydantic
- Auto-generated API docs at `/docs`
- Type hints everywhere = better IDE support and fewer bugs

---

## 2. Pydantic & Data Validation

### What is Pydantic?
Pydantic enforces type validation on Python data structures at runtime. You define a model class, and Pydantic ensures all data matches the expected types and constraints.

### How we use it

**Data models** — `backend/app/models/`:

```python
from pydantic import BaseModel, Field

class Vehicle(BaseModel):
    make: str = Field(..., description="Manufacturer (e.g. Toyota)")
    model: str = Field(..., description="Model name (e.g. Camry)")
    year: int = Field(..., description="Model year")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
```

**Key concepts:**
- `Field(...)` — The `...` means "required" (no default value)
- `ge=0.0, le=1.0` — Built-in validators: greater-than-or-equal and less-than-or-equal
- `Literal["repair", "replace"]` — Restricts values to an exact set of strings
- `Decimal` — Used for money values instead of `float` to avoid floating-point rounding errors (e.g., `0.1 + 0.2 != 0.3` with floats)

**pydantic-settings** — `backend/app/core/config.py`:
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    model_config = {"env_file": ".env"}
    openai_api_key: str = ""
    serpapi_key: str = ""
    labor_rate_per_hour: float = 75.00
```
This automatically reads values from the `.env` file and environment variables. No manual `os.getenv()` calls needed.

### Why Pydantic over plain dicts?
- Runtime type checking catches bugs early
- Auto-serialization to/from JSON
- Self-documenting (field descriptions appear in API docs)
- IDE autocomplete on `.make`, `.model`, etc.

---

## 3. Vision LLM Integration (Multi-Provider)

### What is a Vision LLM?
A "Vision Language Model" can understand both text AND images. You send it images (as base64-encoded data or URLs) along with a text prompt, and it responds with text. We use this for three AI tasks:
1. **Vehicle identification** (vision) — "What make/model/year is this car?"
2. **Damage detection** (vision) — "What parts are damaged and how severely?"
3. **Price estimation** (text) — "What would a replacement bumper cost for this vehicle?"

### The LLM abstraction layer (`backend/app/core/llm.py`)

Instead of calling AI providers directly in each service, we have a central abstraction layer. Services call two public functions — `vision_completion()` and `text_completion()` — and the layer handles provider selection, retries, and fallback automatically.

```python
from app.core.llm import vision_completion, text_completion

# Vision task (vehicle ID, damage detection)
response = await vision_completion(
    prompt="Identify this vehicle...",
    images_b64=["base64-encoded-image-data"],
    max_tokens=2000,
    temperature=0.2,
)

# Text task (price estimation, price extraction)
response = await text_completion(
    prompt="Estimate the price of...",
    max_tokens=200,
    temperature=0.1,
)
```

**Why an abstraction layer?** Services don't need to know which AI provider is being used. Switching from Gemini to OpenAI (or adding a new provider) requires zero changes in service code.

### Provider: Gemini (default)

The default provider is **Gemini 2.5 Flash** via Google's `google-genai` SDK. It's free-tier-eligible, making it ideal for development.

```python
from google import genai
from google.genai import types

client = genai.Client(api_key=gemini_api_key)

response = await client.aio.models.generate_content(
    model="gemini-2.5-flash",
    contents=[prompt, image_part],
    config=types.GenerateContentConfig(
        max_output_tokens=max_tokens,
        temperature=0.2,
        response_mime_type="application/json",  # Structured JSON output
    ),
)
```

**Key Gemini details:**
- `response_mime_type="application/json"` — Tells Gemini to return valid JSON directly (no markdown fences to strip)
- **Thinking model** — Gemini 2.5 Flash is a "thinking" model that uses internal reasoning tokens. These count against `max_output_tokens`, so we pad the budget:
  ```python
  _GEMINI_TOKEN_PADDING = 8000    # Extra tokens for internal reasoning
  _GEMINI_THINKING_BUDGET = 512   # Cap on thinking tokens

  config_kwargs["max_output_tokens"] = max_tokens + _GEMINI_TOKEN_PADDING
  config_kwargs["thinking_config"] = types.ThinkingConfig(
      thinking_budget=_GEMINI_THINKING_BUDGET
  )
  ```
  Without this padding, the model's visible output gets truncated because reasoning tokens eat into the token limit.

### Provider: OpenAI (fallback)

OpenAI is used as a fallback when Gemini is rate-limited, using the `openai` SDK with `AsyncOpenAI`:

```python
from openai import AsyncOpenAI

client = AsyncOpenAI(api_key=settings.openai_api_key)

response = await client.chat.completions.create(
    model="gpt-4.1-mini",   # Vision tasks
    messages=[{"role": "user", "content": content}],
    max_tokens=max_tokens,
    temperature=temperature,
)
```

OpenAI uses `gpt-4.1-mini` for vision tasks and `gpt-4.1-nano` for text-only tasks.

### Sending images

Images must be base64-encoded. Gemini accepts raw bytes via `types.Part.from_bytes()`, while OpenAI expects them wrapped in a specific JSON format:

```python
# Base64 encoding (used by both providers)
import base64
with open(image_path, "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode("utf-8")

# OpenAI format — images wrapped in content blocks:
content = [
    {"type": "text", "text": "Identify this vehicle..."},
    {
        "type": "image_url",
        "image_url": {
            "url": f"data:image/jpeg;base64,{img_b64}",
            "detail": "high",  # "low" for vehicle ID, "high" for damage
        },
    },
]
```

### Key parameters explained
- `temperature` — Controls randomness. 0.0 = always pick the most likely response. 1.0 = more creative/random. We use 0.2 for consistency.
- `max_tokens` — Limits the response length. Vehicle ID needs ~300 tokens, damage detection needs ~2000.
- `detail` — (OpenAI only) Image resolution mode. `"low"` = cheaper, faster. `"high"` = better for spotting small damage.

### Auto-retry and provider fallback

The layer automatically retries on rate limits (HTTP 429 / `RESOURCE_EXHAUSTED`):

```python
_MAX_RETRIES = 2          # Try up to 3 times total (initial + 2 retries)
_RETRY_BASE_DELAY = 10    # Seconds between retries (or parsed from error)
```

**Fallback flow:**
1. Try the primary provider (set by `AI_PROVIDER` env var, default `gemini`)
2. If rate-limited after all retries, automatically try the other provider
3. If both providers are exhausted, raise `LLMRateLimitError`

```python
class LLMRateLimitError(Exception):
    """Raised when all configured LLM providers are rate-limited."""
```

This means the system stays available even when one provider hits quota limits — as long as the other provider has a valid API key configured.

---

## 4. Prompt Engineering for Structured Output

### What is prompt engineering?
Crafting the exact text you send to an LLM to get reliable, structured responses. This is critical because LLMs are non-deterministic — the same prompt can produce different output formats.

### Our approach — "Return ONLY valid JSON"

**Vehicle identification prompt** (`backend/app/prompts/vehicle_identification.py`):
```
Analyze the provided images of a vehicle. Return ONLY valid JSON:
{
  "make": "string",
  "model": "string",
  "year": integer,
  "confidence": float 0.0-1.0
}
```

**Damage assessment prompt** (`backend/app/prompts/damage_assessment.py`):
```
Analyze the images. For each damaged component provide:
- component: use ONLY names from this list: [front_bumper, rear_bumper, ...]
- damage_type: one of [scratch, dent, crack, shatter, crush, deformation, missing]
- severity: float 0.0 to 1.0
Return ONLY a valid JSON array.
```

**Key techniques:**
1. **Explicit format** — Show the exact JSON schema you expect
2. **Constrained vocabulary** — "use ONLY names from this list" prevents the LLM from inventing component names
3. **Severity scale** — Providing ranges (0.0-0.1 = cosmetic, 0.8-1.0 = destroyed) helps the LLM calibrate
4. **"Return ONLY valid JSON"** — Prevents the LLM from wrapping output in markdown code blocks or adding explanatory text

**Handling markdown code fences** — Despite asking for "ONLY JSON", LLMs sometimes wrap responses in ` ```json ... ``` `. We strip these:
```python
if cleaned.startswith("```"):
    cleaned = cleaned.split("\n", 1)[1]
    cleaned = cleaned.rsplit("```", 1)[0].strip()
data = json.loads(cleaned)
```

### Price extraction prompt
For price extraction, we use a template with `.format()`:
```python
prompt = PRICE_EXTRACTION_PROMPT.format(
    site_domain=domain,
    year=year,
    make=make,
    model=model,
    component=component,
    cleaned_text=text,
)
```
This inserts the specific vehicle/part details and the scraped web page text into the prompt.

---

## 5. Image Processing with Pillow

### What is Pillow?
Pillow (PIL Fork) is Python's standard image processing library. We use it to validate, resize, and convert uploaded images.

### How we use it (`backend/app/services/image_proc.py`)

**Validation:**
```python
from PIL import Image
from io import BytesIO

img = Image.open(BytesIO(data))  # Load image from bytes
img.verify()                      # Check it's a valid image (not a corrupted file)
img = Image.open(BytesIO(data))   # Re-open (verify() exhausts the file pointer)
width, height = img.size          # Check dimensions >= 640x480
```

**Why verify() twice?** `img.verify()` checks the file header is valid but makes the image object unusable. So we re-open it for actual processing.

**Resizing:**
```python
TARGET_SIZE = (1024, 1024)
img.thumbnail(TARGET_SIZE, Image.Resampling.LANCZOS)
```
- `thumbnail()` resizes proportionally (doesn't distort the aspect ratio)
- `LANCZOS` is a high-quality downsampling filter (smooth, no pixelation)

**RGBA → RGB conversion:**
```python
if img.mode == "RGBA":
    img = img.convert("RGB")  # JPEG doesn't support transparency
```

**Saving as JPEG:**
```python
img.save(save_path, format="JPEG", quality=90)
```
Quality 90 = good balance between file size and image quality.

---

## 6. Live Price Search Pipeline

### Architecture: Search → Fetch → Extract → Aggregate

This is the most complex part of the system. We don't have a parts price database — instead, we search the web in real-time.

### Step 1: Web Search (SerpAPI)

SerpAPI is a service that performs Google searches via API and returns structured results:
```python
async with httpx.AsyncClient(timeout=10.0) as client:
    response = await client.get(
        "https://serpapi.com/search.json",
        params={
            "q": "2020 Toyota Camry front bumper price buy",
            "api_key": settings.serpapi_key,
            "num": 5,
            "engine": "google",
        },
    )
```
Returns top 5 URLs from Google results.

### Step 2: Fetch & Clean (httpx + trafilatura)

**httpx** — An async HTTP client (like `requests` but async-capable):
```python
async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
    response = await client.get(url)
```

**trafilatura** — Extracts readable text from HTML pages, stripping scripts, ads, navigation:
```python
import trafilatura
clean_text = trafilatura.extract(response.text)  # Returns plain text
```
Why trafilatura over BeautifulSoup? It's specifically designed for extracting the "main content" of a page, automatically removing boilerplate (headers, footers, sidebars).

### Step 3: AI Price Extraction (via LLM abstraction layer)

We send the cleaned text through the LLM abstraction layer's `text_completion()` to extract structured price data:
```python
from app.core.llm import text_completion

raw = await text_completion(
    prompt=prompt,       # Includes vehicle details + scraped page text
    max_tokens=200,
    temperature=0.1,     # Very deterministic
)
```
The LLM returns: `{"price": 249.99, "currency": "USD", "part_type": "aftermarket", "confidence": 0.85}`

The provider (Gemini or OpenAI) is selected automatically — the price extraction code doesn't need to know which one is being used.

### Step 4: Aggregate

```python
prices = [r.price for r in live_results]
part_low = min(prices)
part_high = max(prices)
part_avg = sum(prices) / len(prices)
```

### Static CSV Fallback

If the live search fails (API down, no results), we fall back to a pre-built CSV:
```python
# backend/app/data/parts_prices.csv
# make,model,year_start,year_end,component,avg_price,currency,source,last_updated
```
Loaded once into memory using Python's `csv.DictReader`, cached in a module-level variable.

### Why this approach?
- No single parts database covers every vehicle
- Prices change frequently
- Web search gives real-time, vendor-specific pricing
- AI extraction handles the messy, inconsistent format of product pages

---

## 7. Cost Estimation Logic

### The formula

For each damaged component:
```
Total Cost = Part Cost + Labor Cost
Labor Cost = Labor Hours × Hourly Rate ($75/hr default)
```

### Repair vs. Replace threshold

```python
# Severity > 0.3 → recommend replacement
# Severity ≤ 0.3 → recommend repair
recommendation = "replace" if severity > 0.3 else "repair"
```

### Labor hours lookup

A static dictionary mapping component names to (min, max) labor hours:
```python
LABOR_HOURS = {
    "front_bumper": (Decimal("3.0"), Decimal("4.0")),  # 3-4 hours
    "headlight_left": (Decimal("0.5"), Decimal("1.5")),  # 30-90 minutes
    "quarter_panel_left": (Decimal("6.0"), Decimal("10.0")),  # 6-10 hours
}
```
We use the average: `(min + max) / 2`

### AI price estimation fallback

When both the live web search AND the static CSV miss (no data for this vehicle/component), the system asks the LLM to estimate prices using `text_completion()`:

```python
from app.core.llm import text_completion

prompt = PRICE_ESTIMATION_PROMPT.format(
    year=vehicle.year,
    make=vehicle.make,
    model=vehicle.model,
    component=component.replace("_", " "),
)

raw = await text_completion(prompt=prompt, max_tokens=200, temperature=0.2)
data = json.loads(raw)
# Returns: {"price_low": 120.00, "price_avg": 250.00, "price_high": 450.00}
```

The prompt asks the LLM to estimate low/avg/high prices based on the vehicle's market segment (economy, mid-range, luxury) and the specific component. Each estimate gets a `pricing_method` value:

| Pricing method | Source | Priority |
|---------------|--------|----------|
| `"live_search"` | Real-time web search via SerpAPI | Tried first |
| `"static_reference"` | Pre-built CSV database | Second fallback |
| `"ai_estimate"` | LLM-generated price estimate | Third fallback |

If even the AI estimation fails (e.g., both providers are rate-limited), the system falls back to hardcoded defaults: `$150 / $300 / $500` (low/avg/high).

### Why Decimal instead of float?

```python
# Float:
>>> 0.1 + 0.2
0.30000000000000004  # WRONG for money!

# Decimal:
>>> Decimal("0.1") + Decimal("0.2")
Decimal('0.3')  # CORRECT

# Always quantize to 2 decimal places:
cost = (hours * rate).quantize(Decimal("0.01"))  # $262.50, not $262.4999999
```

---

## 8. Streamlit Frontend

### What is Streamlit?
A Python framework for building web UIs with just Python code. No HTML/CSS/JavaScript needed. Perfect for MVP/internal tools.

### How we use it (`frontend/streamlit_app.py`)

**Key Streamlit components used:**

| Component | What it does | Our usage |
|-----------|-------------|-----------|
| `st.file_uploader()` | File upload widget | Upload 1-10 car photos |
| `st.columns()` | Side-by-side layout | Display images, metrics |
| `st.metric()` | Key-value display | Show make, model, year, costs |
| `st.expander()` | Collapsible section | Damage details per component |
| `st.progress()` | Progress bar | Severity visualization (0.0–1.0) |
| `st.spinner()` | Loading indicator | "Analyzing damage..." |
| `st.sidebar` | Side panel | Vehicle info override |
| `st.json()` | JSON viewer | Raw report data |

**Communication with backend:**
```python
import httpx

# Upload images
upload_resp = httpx.post(f"{API_BASE}/upload", files=files, timeout=30.0)

# Run analysis
analysis_resp = httpx.post(f"{API_BASE}/analyze", json=payload, timeout=120.0)
```
The frontend is a separate process that calls the FastAPI backend via HTTP.

---

## 9. Async Programming (asyncio)

### Why async?
Our app spends most of its time *waiting* — waiting for OpenAI API responses, waiting for web pages to load, waiting for SerpAPI. With synchronous code, the server would be blocked during each wait. Async allows it to handle other requests while waiting.

### How it works in our code

```python
from app.core.llm import vision_completion

# This function can "pause" at each `await` and let other work happen
async def detect_damage(upload_id: str) -> DamageAssessment:
    images_b64 = load_images_as_base64(upload_id)  # Sync (fast, local file read)
    
    # This pauses here while waiting for the LLM (could take 10-30 seconds)
    response = await vision_completion(
        prompt=DAMAGE_PROMPT,
        images_b64=images_b64,
        max_tokens=2000,
    )
    
    # Continues when the response arrives
    return parse_response(response)
```

**FastAPI + async** — FastAPI automatically runs `async def` handlers in an event loop:
```python
@router.post("/analyze")
async def analyze_damage(request: AnalyzeRequest):
    vehicle = await identify_vehicle(request.upload_id)  # Async call
    damage = await detect_damage(request.upload_id)       # Async call
    return report
```

**httpx async client:**
```python
async with httpx.AsyncClient(timeout=5.0) as client:
    response = await client.get(url)  # Non-blocking HTTP request
```

---

## 10. Environment & Configuration

### .env file pattern

Secrets are stored in `backend/.env` (git-ignored):
```env
AI_PROVIDER=gemini
GEMINI_API_KEY=your-gemini-key-here
GEMINI_MODEL=gemini-2.5-flash
OPENAI_API_KEY=sk-your-key-here
SERPAPI_KEY=your-serpapi-key-here
LABOR_RATE_PER_HOUR=75.00
```

**pydantic-settings** reads this automatically:
```python
class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    ai_provider: Literal["gemini", "openai"] = "gemini"
    gemini_model: str = "gemini-2.5-flash"

    openai_api_key: str = ""
    gemini_api_key: str = ""
    google_ai_gemini_api_key: str = ""  # Alternative Gemini key (Google AI Studio format)
    serpapi_key: str = ""
```

`ai_provider` controls which LLM is used first. `gemini_api_key` and `google_ai_gemini_api_key` are both accepted — the LLM layer checks both (useful because Google AI Studio exports the key under different env var names).

### Why this matters
- Never hardcode API keys in source code
- `.env` is in `.gitignore` — keys never get committed
- Each developer has their own `.env` with their own keys
- Easy to override in production (real environment variables take precedence)

---

## 11. Testing with pytest

### Test structure
```
backend/tests/
├── test_health.py        # API health endpoint
├── test_upload.py        # Image upload endpoint
├── test_analysis.py      # Analysis endpoint
├── test_vehicle_id.py    # Vehicle identification service
├── test_damage_detect.py # Damage detection service
└── test_cost_estimate.py # Cost estimation service
```

### Key testing concepts

**pytest-asyncio** — Tests async functions:
```python
import pytest

@pytest.mark.asyncio
async def test_detect_damage():
    result = await detect_damage("test-upload-id")
    assert len(result.damages) > 0
```

**Mocking the LLM abstraction layer** — We mock `vision_completion` / `text_completion` from `app.core.llm` instead of mocking SDK clients directly:
```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_identify_vehicle():
    llm_response = json.dumps({
        "make": "Ford", "model": "Mustang", "year": 2022, "confidence": 0.95
    })

    with (
        patch("app.services.vehicle_id.load_images_as_base64", return_value=["fake_base64"]),
        patch(
            "app.services.vehicle_id.vision_completion",
            new_callable=AsyncMock,
            return_value=llm_response,
        ),
    ):
        vehicle = await identify_vehicle("test_upload_id")

    assert vehicle.make == "Ford"
    assert vehicle.year == 2022
```

**Why mock at the abstraction layer?** We don't need to replicate the complex response objects of each SDK. `vision_completion()` returns a simple string, so mocking is just `return_value="some JSON"`. This also means tests don't break when we switch providers.

**httpx.AsyncClient for API tests:**
```python
from httpx import AsyncClient

async with AsyncClient(app=app, base_url="http://test") as client:
    response = await client.get("/health")
    assert response.status_code == 200
```

### Run tests
```bash
cd backend
python -m pytest tests/ -v
```

---

## 12. AI Model Selection & Cost Guide

### Current setup (what we're using)

| Task | Model (default) | Fallback | Why |
|------|----------------|----------|-----|
| Vehicle ID | `gemini-2.5-flash` | `gpt-4.1-mini` | Free tier for dev, excellent vision |
| Damage Detection | `gemini-2.5-flash` | `gpt-4.1-mini` | Same model, high accuracy via `vision_completion()` |
| Price Estimation | `gemini-2.5-flash` | `gpt-4.1-nano` | Same model via `text_completion()` |

**Why Gemini as default?** The free tier means $0 cost during development. Rate limits exist but the auto-fallback to OpenAI handles them transparently.

### Model options and pricing

#### Google Gemini
| Model | Input $/1M | Output $/1M | Vision? | Free tier? | Notes |
|-------|-----------|------------|---------|------------|-------|
| **gemini-2.5-flash** | $0.30 | $2.50 | ✅ | ✅ Yes | Our default. "Thinking" model with internal reasoning |
| gemini-2.5-flash-lite | $0.10 | $0.40 | ✅ | ✅ Yes | Cheaper, lower quality for complex vision |

#### OpenAI GPT-4.1 family
| Model | Input $/1M | Output $/1M | Vision? | Notes |
|-------|-----------|------------|---------|-------|
| gpt-4.1 | $2.00 | $8.00 | ✅ | Best non-reasoning OpenAI model |
| **gpt-4.1-mini** | $0.40 | $1.60 | ✅ | Our vision fallback. Great price/performance |
| **gpt-4.1-nano** | $0.10 | $0.40 | ✅ | Our text fallback. Cheapest available |

#### Other providers (not currently integrated)
| Model | Input $/1M | Output $/1M | Notes |
|-------|-----------|------------|-------|
| Claude Haiku 4.5 | $1.00 | $5.00 | Fast, good vision. No free tier |
| Claude Sonnet 4.5 | $3.00 | $15.00 | Excellent reasoning. Expensive for our use case |

### How to switch models

No code changes needed — everything is controlled via environment variables:

```env
# Switch the default provider (gemini or openai)
AI_PROVIDER=gemini

# Change the Gemini model
GEMINI_MODEL=gemini-2.5-flash
```

- `AI_PROVIDER` — Controls which provider is tried first (`gemini` or `openai`). The other becomes the fallback.
- `GEMINI_MODEL` — Controls which Gemini model is used. The OpenAI models (`gpt-4.1-mini` for vision, `gpt-4.1-nano` for text) are hardcoded in the LLM layer since they're only used as fallbacks.

**Example: switch to OpenAI as primary:**
```env
AI_PROVIDER=openai
OPENAI_API_KEY=sk-your-key-here
```
Gemini becomes the fallback automatically.

---

## Glossary

| Term | Definition |
|------|-----------|
| **API** | Application Programming Interface — a way for programs to talk to each other over HTTP |
| **async/await** | Python's way of writing non-blocking code that can wait for I/O without freezing |
| **Base64** | A way to encode binary data (like images) as text characters for transmission in JSON |
| **CORS** | Cross-Origin Resource Sharing — security policy that controls which websites can call your API |
| **Decimal** | Python's exact decimal arithmetic type, used for money to avoid floating-point errors |
| **Endpoint** | A specific URL path in an API (e.g., `/api/v1/upload`) |
| **FastAPI** | Python web framework for building APIs with automatic validation and documentation |
| **google-genai** | Google's official Python SDK for the Gemini family of AI models |
| **httpx** | Async-capable HTTP client library for Python |
| **JSON** | JavaScript Object Notation — the standard data format for API communication |
| **LLM** | Large Language Model — an AI model trained on text (GPT-4, Claude, Gemini) |
| **Middleware** | Code that runs on every request/response (e.g., CORS headers) |
| **Mock** | A fake object used in tests to simulate external services (like OpenAI) |
| **Provider fallback** | Automatic switch to a backup AI provider when the primary is rate-limited or unavailable |
| **Pydantic** | Python library for data validation using type hints |
| **Rate limiting** | API quota restrictions that cap how many requests you can make per time period (e.g., 429 errors) |
| **REST** | Representational State Transfer — an API design pattern using HTTP methods (GET, POST, etc.) |
| **SerpAPI** | A service that performs Google searches via API and returns structured results |
| **Severity score** | 0.0 (no damage) to 1.0 (destroyed) — our standardized damage measurement |
| **Streamlit** | Python framework for building web UIs with just Python code |
| **Thinking model** | An LLM that uses internal reasoning tokens before producing visible output (e.g., Gemini 2.5 Flash) |
| **Token** | A piece of text (~4 characters) that LLMs process. Pricing is per million tokens |
| **trafilatura** | Python library for extracting readable text from HTML web pages |
| **Vision LLM** | An LLM that can understand both text and images |

---

*Last updated: March 6, 2026. Prices are subject to change — check provider websites for current rates.*
