# Technology Stack

Reference document for all technologies used in the Car Crash AI project, how they fit together, and how the system works end-to-end.

---

## How the Project Works

### What this project does

Car Crash AI is a web application that takes photos of a damaged vehicle and produces a full repair cost estimate. A user uploads photos, the system identifies the vehicle, detects every damaged component, looks up part prices, calculates labor costs, and returns a complete report — all powered by AI vision models.

### End-to-end flow

```
User uploads photos (Next.js frontend)
        │
        ▼
┌─────────────────────────────────────────────┐
│  1. UPLOAD  (POST /api/v1/upload)            │
│     Validate images (size, format, res)      │
│     Check image quality (blur, brightness)   │
│     Resize to 1024×1024, save as JPEG        │
│     Return upload_id + quality_warnings      │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│  2. VEHICLE ID  (VIN decoder or vision LLM)  │
│     Path A: decode VIN via NHTSA vPIC API    │
│     Path B: send photos to Gemini/OpenAI     │
│       "What make/model/year is this car?"    │
│     If confidence < 70%: ask user            │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│  3. DAMAGE DETECTION  (zone-based passes)    │
│                                              │
│     Zone mode (default):                     │
│       Pass 1: Front zone components          │
│       Pass 2: Rear zone components           │
│       Pass 3: Side zone components           │
│       Merge: worst severity per component    │
│                                              │
│     Consensus mode (high-confidence):        │
│       Run Gemini + OpenAI in parallel        │
│       Average severity, flag divergence>0.25 │
│                                              │
│     Per-component thresholds applied         │
│     (structural parts replace at 0.2;        │
│      cosmetic panels tolerate up to 0.4)     │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│  4. COST ESTIMATION  (per component)         │
│                                              │
│     For each damaged component:              │
│     ┌─ Try live price search (SerpAPI)       │
│     │  Search Google → Fetch pages →         │
│     │  AI extracts prices from text          │
│     ├─ Fallback: static CSV database         │
│     ├─ Fallback: AI price estimation         │
│     └─ Last resort: default $300             │
│                                              │
│     + Labor cost (hours × $75/hr rate)       │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│  5. SANITY CHECK  (second-pass LLM review)   │
│     Review full report for coherence         │
│     Flag: implausible totals, odd combos,    │
│     severity vs cost mismatches              │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│  6. PERSIST + REPORT                         │
│     Save EstimateRecord to PostgreSQL        │
│     (fail-safe: response returned even if    │
│      DB write fails)                         │
│                                              │
│     JSON response + PDF download available  │
│     via GET /api/v1/report/{estimate_id}     │
└─────────────────────────────────────────────┘
        │
        ▼
   User sees results in Next.js UI
   (severity bars, cost table, PDF link)
```

### The AI calls per analysis

| Call | Type | Input | Output | Model |
|------|------|-------|--------|-------|
| **Vehicle ID** | Vision | Photos + prompt | `{"make": "BMW", "model": "3 Series", "year": 2020, "confidence": 0.92}` | gemini-2.5-flash |
| **Damage (zone ×3)** | Vision | Photos + zone prompt | `[{"component": "front_bumper", "severity": 0.7, ...}, ...]` | gemini-2.5-flash |
| **Damage (consensus)** | Vision×2 | Photos + prompt | Merged results from both providers | gemini + gpt-4.1-mini |
| **Price Estimation** | Text | Vehicle + component | `{"price_low": 180, "price_avg": 280, "price_high": 450}` | gemini-2.5-flash |
| **Sanity Check** | Text | Full report summary | `["Warning: total seems low for structural damage"]` | gemini-2.5-flash |

All calls go through `backend/app/core/llm.py`, which handles provider selection, retries, and fallback automatically.

### How the API is used

**Step 1 — Upload images:**
```
POST /api/v1/upload
Content-Type: multipart/form-data
Body: images[] = [photo1.jpg, photo2.jpg]

Response: {
  "upload_id": "a1b2c3d4e5f6",
  "image_count": 2,
  "quality_warnings": [
    {"image_filename": "photo1.jpg", "warning_type": "blur", "message": "Image may be blurry"}
  ]
}
```

**Step 2 — Run analysis:**
```
POST /api/v1/analyze
Content-Type: application/json
Body: {
  "upload_id": "a1b2c3d4e5f6",
  "vin": "1HGBH41JXMN109186",       // optional — triggers NHTSA VIN decode
  "use_consensus": false,             // true = run both LLM providers
  "make": "BMW", "model": "3 Series", "year": 2020  // optional override
}

Response: {
  "vehicle": { "make": "BMW", "model": "3 Series", "year": 2020 },
  "damage_assessment": {
    "damages": [...],
    "assessment_method": "zone_pass",
    "image_quality_warnings": [...],
    "angle_guidance": { "angles_detected": 2, "suggestion": "Add side photos" }
  },
  "cost_estimates": [...],
  "totals": { "parts_total": "860.00", "labor_total": "525.00", "grand_total": "1385.00" },
  "assessment_warnings": []
}
```

**Step 3 — Download PDF report:**
```
GET /api/v1/report/{estimate_id}
Response: PDF bytes (Content-Type: application/pdf)
         or HTML fallback if WeasyPrint not installed
```

**Step 4 — Estimate history:**
```
GET /api/v1/estimates           → last 50 estimates (summary list)
GET /api/v1/estimates/{id}      → full AssessmentReport JSON
```

### Price estimation cascade

| Priority | Method | Source | When used |
|----------|--------|--------|-----------|
| 1st | **Live search** | Google via SerpAPI → scrape pages → AI extracts prices | SerpAPI key set, results found |
| 2nd | **Static CSV** | `backend/app/data/parts_prices.csv` | Vehicle/component match exists in CSV |
| 3rd | **AI estimate** | LLM estimates based on vehicle segment | No live or static data available |

### Architecture overview

The system runs as two separate processes, connected to a shared PostgreSQL database:

| Process | Port | Role |
|---------|------|------|
| **Backend** (FastAPI + Uvicorn) | 8000 | API server — uploads, AI calls, cost calculations, DB writes |
| **Frontend** (Next.js) | 3000 | Web UI — file upload, results display, history |
| **PostgreSQL** | 5432 | Persistent estimate history, upload sessions |

Orchestrated via `docker-compose.yml` in the project root. The backend waits for PostgreSQL healthcheck before starting.

---

## 1. Language & Runtime

| Technology | Version | Purpose |
|---|---|---|
| **Python** | 3.11+ | Backend language |
| **Node.js** | 20+ | Next.js frontend runtime |

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

Async-first web framework with automatic OpenAPI docs and native Pydantic integration. Provides type-safe request/response models out of the box.

**Routers registered in `backend/app/main.py`:**

| Router | Prefix | Description |
|--------|--------|-------------|
| `upload` | `/api/v1/upload` | Image upload + quality validation |
| `analysis` | `/api/v1/analyze` | Full damage analysis pipeline |
| `estimate` | `/api/v1/estimate` | Single estimate retrieval |
| `estimates` | `/api/v1/estimates` | Estimate list + history |
| `report` | `/api/v1/report` | PDF/HTML report download |

---

## 3. AI / LLM Providers

| Package | Version | Models Used | Role |
|---|---|---|---|
| **google-genai** | ≥1.0.0 | `gemini-2.5-flash` | Default provider (vision + text) |
| **openai** | ≥1.60.0 | `gpt-4.1-mini` (vision), `gpt-4.1-nano` (text) | Fallback provider + consensus partner |

### LLM Abstraction Layer (`backend/app/core/llm.py`)

Exposes three public functions:

- `vision_completion(prompt, images_b64, ...)` — single-provider vision call
- `text_completion(prompt, ...)` — single-provider text call
- `dual_vision_completion(prompt, images_b64, ...)` — runs both providers in parallel via `asyncio.gather`, returns `(primary_result, secondary_result | None)`

**Key design decisions:**

- **Multi-provider support** — Gemini free tier for development; OpenAI is automatic fallback on rate limits
- **Automatic retry** — Up to 2 retries with backoff on 429/RESOURCE_EXHAUSTED, parsing `retryDelay` from error responses
- **Thinking model support** — Gemini 2.5 models get +8,000 token padding and 512-token thinking budget
- **Consensus mode** — `dual_vision_completion` enables running both providers for high-stakes assessments

### Consensus Service (`backend/app/services/consensus.py`)

When `use_consensus=True` in the analyze request:

1. Both providers run in parallel via `dual_vision_completion`
2. Severity scores are averaged per component
3. Divergence ≥ 0.25 is flagged as a warning in the response
4. The higher-severity source's `damage_type` and `description` are used
5. `COMPONENT_THRESHOLDS` determines replace/repair cutoff per component type

### Zone-Based Damage Detection (`backend/app/services/damage_detect.py`)

Default mode runs three focused passes instead of one broad prompt:

| Zone | Components Covered |
|------|--------------------|
| **Front** | front_bumper, hood, grille, headlights, front fenders, windshield_front, a_pillars |
| **Rear** | rear_bumper, trunk, taillights, quarter panels, windshield_rear |
| **Side** | all doors, mirrors, rocker panels, b_pillars, roof, all wheels |

Each pass gives the model a narrow component list, improving per-component accuracy. Results are merged by taking the worst severity per component across passes.

### Sanity Check (`backend/app/services/sanity_check.py`)

After building the full `AssessmentReport`, a second LLM call reviews the complete summary for coherence:

- Cost plausibility (grand total vs. severity distribution)
- Severity consistency (e.g., "airbag deployed" but only cosmetic damage)
- Unusual component combinations

Returns a list of warning strings appended to `assessment_warnings` in the response. Empty list means no issues.

---

## 4. Image Processing

| Package | Version | Purpose |
|---|---|---|
| **Pillow (PIL)** | ≥11.0.0 | Image validation, resizing, quality checks |

Used in `backend/app/services/image_proc.py`:

- Validate uploaded images (size limits, minimum resolution 640×480)
- **Blur detection** — `ImageFilter.FIND_EDGES` + `ImageStat.Stat` variance; threshold 80.0
- **Brightness check** — `ImageStat.Stat` mean; dark threshold 50.0, overexposed threshold 220.0
- Resize to 1024×1024 max using LANCZOS resampling
- Convert RGBA → RGB, save as JPEG quality 90
- Encode as base64 for LLM API calls

**Angle guidance** — heuristic based on image count: < 2 images = "missing coverage", 2–3 = "suggest more angles", 4+ = "good coverage". Guidance is included in the response to prompt users to upload better photos.

---

## 5. Web Scraping & Search

| Package | Version | Purpose |
|---|---|---|
| **google-search-results** (SerpAPI) | ≥2.4.2 | Live part price search via Google |
| **httpx** | ≥0.28.0 | Async HTTP client for fetching pages + API calls |
| **trafilatura** | ≥2.0.0 | Text extraction from HTML pages |
| **beautifulsoup4** | ≥4.12.0 | HTML parsing (available as alternative) |

---

## 6. VIN Decoder (`backend/app/services/vin_decoder.py`)

Integrates the **NHTSA vPIC API** (free, no key required):

```
GET https://vpic.nhtsa.dot.gov/api/vehicles/decodevinvalues/{vin}?format=json
```

- Validates 17-char VIN format
- Decodes make, model, year, body style from official NHTSA database
- Returns a `Vehicle` model with `confidence=1.0` (authoritative decode)
- Raises `VINDecodeError` on invalid VIN or API failure
- Analysis endpoint falls back to vision-based ID on `VINDecodeError`

Body style strings from NHTSA are normalized to standard values (`sedan`, `suv`, `coupe`, etc.) via `_normalise_body_style()`.

---

## 7. Database (`backend/app/db/`)

| Package | Version | Purpose |
|---|---|---|
| **SQLAlchemy** | ≥2.0.0 | ORM + async engine |
| **asyncpg** | ≥0.30.0 | PostgreSQL async driver |
| **alembic** | ≥1.14.0 | Database migrations |
| **PostgreSQL** | 16 | Primary database |

### Session management (`backend/app/db/session.py`)

```python
engine = create_async_engine(settings.database_url, pool_size=5, max_overflow=10)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
```

Dependency injection via `get_db() -> AsyncGenerator[AsyncSession, None]` — commits on success, rolls back on exception.

### Database models (`backend/app/db/models.py`)

| Table | Key columns | Purpose |
|-------|-------------|---------|
| `upload_sessions` | id (str 12), created_at, image_count, quality_warnings_json | Track uploads |
| `estimates` | id (autoincrement), upload_id (FK), vehicle fields, parts/labor/grand totals, report_json | Persist full reports |

### Migrations (`backend/alembic/`)

`001_initial_schema.py` creates both tables. Run with:
```bash
cd backend && alembic upgrade head
```

---

## 8. PDF Reports (`backend/app/services/report_pdf.py`)

| Package | Version | Purpose |
|---|---|---|
| **Jinja2** | ≥3.1.0 | HTML report template rendering |
| **WeasyPrint** | ≥62.0 | HTML → PDF conversion |

Template at `backend/app/templates/report.html` includes:

- Severity bars (color-coded: red ≥ 0.6, yellow ≥ 0.3, green < 0.3)
- Damage table with replace/repair badges
- Cost breakdown with totals
- Quality warnings, angle guidance, sanity check flags
- Disclaimer section

`generate_pdf()` checks for WeasyPrint availability at runtime and returns HTML bytes if the system libraries (pango, cairo) aren't installed — detected by checking for `%PDF` magic bytes.

---

## 9. Frontend (`frontend-next/`)

| Package | Version | Purpose |
|---|---|---|
| **Next.js** | 15.1.0 | React framework (App Router) |
| **React** | 19.0.0 | UI library |
| **TypeScript** | 5+ | Type safety |
| **Tailwind CSS** | 3.4+ | Utility-first styling |
| **clsx** | 2.1+ | Conditional class merging |

### Key pages and components

| File | Purpose |
|------|---------|
| `app/page.tsx` | Main upload + analysis flow (stage machine: upload → options → analyzing → result → error) |
| `app/history/page.tsx` | Estimate history table with PDF links |
| `components/UploadZone.tsx` | Drag-and-drop image upload (JPEG/PNG/HEIC filter) |
| `components/DamageReport.tsx` | Results display — severity bars, cost table, PDF download |
| `lib/api.ts` | Typed API client for all backend calls |

### Frontend state flow

```
upload stage    → drag-drop images → call POST /upload → show quality warnings
options stage   → enter VIN / make/model/year / enable consensus mode
analyzing       → call POST /analyze → show loading
result          → render DamageReport with full assessment
error           → show message with retry
```

### API client (`frontend-next/lib/api.ts`)

TypeScript interfaces: `UploadResponse`, `DamageItem`, `CostEstimate`, `AssessmentReport`

Functions:
- `uploadImages(files: File[]): Promise<UploadResponse>`
- `analyzeUpload(uploadId, opts): Promise<AssessmentReport>`
- `reportPdfUrl(estimateId): string`
- `listEstimates(): Promise<EstimateSummary[]>`

---

## 10. Containerization

| File | Purpose |
|------|---------|
| `backend/Dockerfile` | Python 3.11-slim + WeasyPrint system deps |
| `docker-compose.yml` | PostgreSQL 16 + backend service orchestration |

`docker-compose.yml` services:

- **postgres** — `postgres:16-alpine`, healthcheck (`pg_isready`), persistent named volume
- **backend** — builds from `./backend`, runs `alembic upgrade head && uvicorn`, depends on postgres health

WeasyPrint requires system packages (pango, cairo, gdk-pixbuf2) that are installed in the Dockerfile via `apt-get`.

---

## 11. Testing

| Package | Purpose |
|---|---|
| **pytest** | Test runner and assertions |
| **pytest-asyncio** | Async test support |
| **unittest.mock** | Mock LLM calls (`vision_completion`, `text_completion`) |
| **httpx.AsyncClient** | FastAPI endpoint testing via `ASGITransport` |

Mocking strategy: mock at the abstraction layer (`app.core.llm.vision_completion`) rather than SDK internals — provider-agnostic, returns simple strings.

---

## 12. Architecture Decisions

| Decision | Rationale |
|---|---|
| **Zone-based damage prompts** | Three focused passes (front/rear/side) give the model a constrained component list per pass, improving accuracy over one broad prompt |
| **Consensus mode** | Running both providers and averaging severity reduces LLM non-determinism; divergence flag surfaces when models disagree strongly |
| **Per-component thresholds** | Structural/safety parts use a lower replace threshold (0.2) than cosmetic panels (0.35–0.45) — matches real repair shop decisions |
| **Sanity check pass** | Second LLM call reviewing the full report catches hallucinations and implausible cost/severity combinations |
| **Image quality gates** | Blur and brightness checks before analysis prevent bad-input failures that degrade accuracy silently |
| **VIN decode first** | NHTSA VIN decode is free, authoritative, and faster than vision-based ID — used when the user provides a VIN |
| **DB fail-safe pattern** | `EstimateRecord` persistence is wrapped in try/except so a DB failure never blocks the API response |
| **WeasyPrint fallback** | Returns HTML bytes if WeasyPrint system libs aren't installed; detected by checking `%PDF` magic bytes |
| **Multi-provider LLM** | Cost optimization (Gemini free tier for dev), reliability (automatic fallback), no vendor lock-in |
| **Async everywhere** | All operations are I/O-bound (LLM, web scraping, DB). Async lets the server handle concurrent requests without blocking |
| **Next.js over Streamlit** | Production-grade UI with TypeScript type safety, proper routing, and a real component model; Streamlit was the MVP prototype |
| **PostgreSQL + SQLAlchemy async** | Persistent estimate history, type-safe queries, standard ORM migration tooling via Alembic |
