# Technology Stack

Reference document for all technologies used in the Car Crash AI project, how they fit together, and how the system works end-to-end.

---

## How the Project Works

### What this project does

Car Crash AI is a web application that takes photos of a damaged vehicle and produces a full repair cost estimate. A user uploads photos, the system identifies the vehicle, detects every damaged component, looks up part prices, calculates labor costs, and returns a complete report — all powered by AI vision models.

### End-to-end flow

When a user clicks "Analyze Damage" in the browser, this is what happens:

```
User uploads photos
        │
        ▼
┌─────────────────────────────────────────┐
│  1. UPLOAD  (POST /api/v1/upload)       │
│     Validate images (size, format, res) │
│     Resize to 1024×1024, save as JPEG   │
│     Return upload_id                    │
└─────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────┐
│  2. VEHICLE ID  (vision LLM call)       │
│     Send photos to Gemini/OpenAI        │
│     "What make/model/year is this car?" │
│     Parse JSON → Vehicle model          │
│     If confidence < 70%: ask user       │
└─────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────┐
│  3. DAMAGE DETECTION  (vision LLM call) │
│     Send photos to Gemini/OpenAI        │
│     "What parts are damaged? How bad?"  │
│     Parse JSON → list of DamageItems    │
│     Each: component, type, severity     │
└─────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────┐
│  4. COST ESTIMATION  (per component)    │
│                                         │
│     For each damaged component:         │
│     ┌─ Try live price search (SerpAPI)  │
│     │  Search Google → Fetch pages →    │
│     │  AI extracts prices from text     │
│     ├─ Fallback: static CSV database    │
│     ├─ Fallback: AI price estimation    │
│     │  "Estimate cost of a BMW hood"    │
│     └─ Last resort: default $300        │
│                                         │
│     + Labor cost (hours × $75/hr rate)  │
└─────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────┐
│  5. REPORT                              │
│     Vehicle info + damage list +        │
│     per-component cost breakdown +      │
│     parts total + labor total +         │
│     grand total + disclaimer            │
└─────────────────────────────────────────┘
        │
        ▼
   User sees results in Streamlit UI
```

### The three AI calls

The system makes up to three types of AI calls per analysis:

| Call | Type | Input | Output | Model |
|------|------|-------|--------|-------|
| **Vehicle ID** | Vision | Photos + prompt | `{"make": "BMW", "model": "3 Series", "year": 2020, "confidence": 0.92}` | gemini-2.5-flash |
| **Damage Detection** | Vision | Photos + prompt | `[{"component": "front_bumper", "severity": 0.7, ...}, ...]` | gemini-2.5-flash |
| **Price Estimation** | Text | Vehicle + component | `{"price_low": 180, "price_avg": 280, "price_high": 450}` | gemini-2.5-flash |

All three go through the same abstraction layer (`backend/app/core/llm.py`), which handles provider selection, retries, and fallback automatically.

### How the API is used

The backend exposes a REST API that the Streamlit frontend calls over HTTP:

**Step 1 — Upload images:**
```
POST /api/v1/upload
Content-Type: multipart/form-data
Body: images[] = [photo1.jpg, photo2.jpg]

Response: { "upload_id": "a1b2c3d4e5f6", "image_count": 2 }
```

**Step 2 — Run analysis:**
```
POST /api/v1/analyze
Content-Type: application/json
Body: { "upload_id": "a1b2c3d4e5f6" }

Response: {
  "vehicle": { "make": "BMW", "model": "3 Series", "year": 2020 },
  "damage_assessment": { "damages": [...] },
  "cost_estimates": [...],
  "totals": { "parts_total": "860.00", "labor_total": "525.00", "grand_total": "1385.00" }
}
```

The user can also skip AI vehicle identification by providing make/model/year in the request:
```json
{ "upload_id": "a1b2c3d4e5f6", "make": "BMW", "model": "3 Series", "year": 2020 }
```

### Price estimation cascade

Part pricing uses a three-tier fallback to always return a result:

| Priority | Method | Source | When used |
|----------|--------|--------|-----------|
| 1st | **Live search** | Google via SerpAPI → scrape pages → AI extracts prices | SerpAPI key set, results found |
| 2nd | **Static CSV** | `backend/app/data/parts_prices.csv` | Vehicle/component match exists in CSV |
| 3rd | **AI estimate** | LLM estimates based on vehicle segment | No live or static data available |

The AI estimate is vehicle-aware — it knows a BMW hood costs more than a Toyota hood, and a mirror costs less than a quarter panel.

### Two-process architecture

The system runs as two separate processes:

| Process | Port | Role |
|---------|------|------|
| **Backend** (FastAPI + Uvicorn) | 8000 | API server — handles uploads, AI calls, cost calculations |
| **Frontend** (Streamlit) | 8501 | Web UI — file upload, results display, user interaction |

The frontend calls the backend over HTTP (`http://localhost:8000/api/v1`). CORS middleware on the backend allows cross-origin requests from the Streamlit process.

---

## 1. Language & Runtime

| Technology | Version | Purpose |
|---|---|---|
| **Python** | 3.11+ | Primary language |

**Why Python:** Best-in-class AI/ML ecosystem, native async support, rapid prototyping. Both backend and frontend are Python, keeping the stack simple for a Python-only team.

---

## 2. Backend Framework

| Package | Version | Purpose |
|---|---|---|
| **FastAPI** | ≥0.115.0 | Web framework |
| **Uvicorn** | ≥0.34.0 | ASGI server |
| **Pydantic** | ≥2.10.0 | Data validation & serialization |
| **pydantic-settings** | ≥2.7.0 | Configuration management |
| **python-multipart** | ≥0.0.18 | File upload parsing |

### FastAPI

Async-first web framework with automatic OpenAPI docs and native Pydantic integration. Chosen over Flask (no native async, no built-in validation) and Django (too heavyweight for an API-only service). Provides type-safe request/response models out of the box.

- **Entry point:** `backend/app/main.py` — mounts routers for `/api/v1/upload`, `/api/v1/analyze`, `/api/v1/estimate`
- **Auto-docs:** Available at `/docs` (Swagger) and `/redoc`

### Uvicorn

High-performance ASGI server that runs the FastAPI application. Handles concurrent connections for I/O-bound LLM and web scraping calls.

### Pydantic / pydantic-settings

Pydantic validates all API request/response models. `pydantic-settings` loads configuration from `.env` files with type coercion and defaults.

- **Config:** `backend/app/core/config.py` — `Settings` class with typed fields for API keys, upload limits, labor rates, and CORS origins

---

## 3. AI / LLM Providers

| Package | Version | Models Used | Role |
|---|---|---|---|
| **google-genai** | ≥1.0.0 | `gemini-2.5-flash` | Default provider (vision + text) |
| **openai** | ≥1.60.0 | `gpt-4.1-mini` (vision), `gpt-4.1-nano` (text) | Fallback provider |

### Provider Architecture

A custom abstraction layer in `backend/app/core/llm.py` exposes two functions:

- `vision_completion(prompt, images_b64, ...)` — for damage analysis from photos
- `text_completion(prompt, ...)` — for price extraction from scraped text

**Key design decisions:**

- **Multi-provider support** — Gemini is the default (free tier available for development); OpenAI is the automatic fallback when Gemini is rate-limited
- **Automatic retry** — Up to 2 retries with backoff on 429/RESOURCE_EXHAUSTED errors, parsing `retryDelay` from error responses
- **Seamless fallback** — If the primary provider exhausts retries, the system switches to the other provider transparently
- **Thinking model support** — Gemini 2.5 models get extra token padding (+8,000 tokens) and a thinking budget (512 tokens) since reasoning tokens count against output limits
- **Provider switching** — Controlled via `ai_provider` setting in `.env` (`"gemini"` or `"openai"`)

---

## 4. Image Processing

| Package | Version | Purpose |
|---|---|---|
| **Pillow (PIL)** | ≥11.0.0 | Image validation, resizing, format conversion |

Used in `backend/app/services/image_proc.py` to:

- Validate uploaded images (size limits, minimum resolution 640×480, format check)
- Resize to 1024×1024 max using LANCZOS resampling
- Convert RGBA → RGB and save as JPEG (quality 90)
- Encode processed images as base64 for LLM API calls

---

## 5. Web Scraping & Search

| Package | Version | Purpose |
|---|---|---|
| **google-search-results** (SerpAPI) | ≥2.4.2 | Programmatic Google search for live part prices |
| **httpx** | ≥0.28.0 | Async HTTP client for fetching web pages |
| **trafilatura** | ≥2.0.0 | Text extraction from HTML pages |
| **beautifulsoup4** | ≥4.12.0 | HTML parsing (available, not primary) |

Used in the live price search pipeline (`backend/app/services/price_search.py`):

1. **Search** — SerpAPI queries Google for `"{year} {make} {model} {component} price buy"`, returns top 5 URLs
2. **Fetch** — `httpx.AsyncClient` fetches each URL with 5s timeout and redirect following
3. **Extract** — `trafilatura.extract()` pulls clean text from HTML (truncated to 2,000 chars per page)
4. **Price parsing** — LLM `text_completion` extracts structured price data (price, currency, part type, stock status) from each snippet
5. **Filter** — Results below 50% confidence are discarded

**Why httpx over requests:** Native async support, required for FastAPI's async handlers. Also used in the Streamlit frontend to call the backend API.

---

## 6. Frontend

| Package | Version | Purpose |
|---|---|---|
| **Streamlit** | ≥1.41.0 | Web UI |

**Why Streamlit:** Enables a fully functional web UI in pure Python — no JavaScript, HTML, or CSS needed. Ideal for MVP speed with a Python-only team. Built-in support for file uploads, image display, metrics, expanders, and JSON views.

- **Entry point:** `frontend/streamlit_app.py`
- **Features:** Multi-image upload (1–10), optional vehicle info override via sidebar, damage severity visualization with progress bars, cost breakdown with metrics, raw JSON report view
- **Communicates with backend** via `httpx` HTTP calls to `http://localhost:8000/api/v1`

---

## 7. Data & Storage

| Storage | Format | Purpose |
|---|---|---|
| CSV files | `.csv` | Static parts price database (version-controlled fallback) |
| File system | JPEG | Processed image uploads (`uploads/{upload_id}/`) |
| `.env` files | Key-value | API keys and configuration |

**Why no database:** MVP simplicity. All state is ephemeral (upload → analyze → respond). A database is planned for Phase 2 (history, user accounts, cached estimates).

---

## 8. Testing

| Package | Purpose |
|---|---|
| **pytest** | Test runner and assertions |
| **pytest-asyncio** | Async test support for `async def` test functions |
| **unittest.mock** | Mocking LLM API calls to avoid real API usage in tests |
| **httpx.AsyncClient** | Testing FastAPI endpoints via `ASGITransport` |

---

## 9. Architecture Decisions

| Decision | Rationale |
|---|---|
| **Multi-provider LLM** | Cost optimization (Gemini free tier for dev), reliability (automatic fallback on rate limits), no vendor lock-in |
| **Async everywhere** | All operations are I/O-bound (LLM API calls, web scraping, file I/O). Async lets the server handle concurrent requests without blocking |
| **Streamlit over React/Vue** | MVP speed — functional UI in ~140 lines of Python. No frontend build pipeline, no JS expertise needed |
| **No database yet** | MVP simplicity — stateless request/response pattern. File system for uploads, `.env` for config, CSV for static prices. Database planned for Phase 2 |
| **SerpAPI over direct scraping** | Reliable Google results without anti-bot issues. Pay-per-search pricing aligns with usage patterns |
| **Trafilatura over BeautifulSoup** | Purpose-built for article/content extraction. Handles boilerplate removal automatically, producing cleaner text for LLM price extraction |
