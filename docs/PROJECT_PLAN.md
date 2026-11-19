# Car Crash Damage Detection & Assessment AI — Project Plan

## Overview

An AI-powered system that accepts multiple images of a vehicle after an accident and produces a complete damage assessment report including vehicle identification, per-component damage severity, repair/replace recommendations, and cost estimates.

---

## High-Level Flow

```
User uploads images (Next.js)
        │
        ▼
┌─────────────────────┐
│  Image Preprocessing │  ← validate, resize, blur/brightness check
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ Vehicle Identification│  ← VIN decode (NHTSA) OR vision LLM
│ (make, model, year)  │
└────────┬────────────┘
         │
         ▼
┌──────────────────────────┐
│ Damage Detection          │
│ Zone passes OR consensus  │  ← per-component severity 0.0–1.0
│ Calibrated thresholds     │     calibrated per component type
└────────┬─────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Cost Estimation          │  ← part prices + labor estimates
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Sanity Check             │  ← second LLM pass reviews full report
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Persist + Report         │  ← PostgreSQL + PDF/HTML via WeasyPrint
└─────────────────────────┘
```

---

## 1. Image Input & Preprocessing

**What it does:** Accept 1–10 images of the damaged vehicle (front, rear, sides, close-ups).

**Implemented:**
- Supported formats: JPEG, PNG, HEIC (convert HEIC → JPEG on ingest)
- Validate: minimum resolution (640×480), file size limits (≤ 20 MB each)
- Resize to 1024×1024 using LANCZOS resampling
- Blur detection via `ImageFilter.FIND_EDGES` + variance (threshold 80.0)
- Brightness check via `ImageStat.Stat` mean (dark < 50, overexposed > 220)
- Angle guidance heuristic (image count vs. expected 4 angles)
- Quality warnings returned in upload response

**Tech:** Python + Pillow (`backend/app/services/image_proc.py`)

---

## 2. Vehicle Identification

**What it does:** Determine the make, model, and year of the vehicle.

**Implemented — Two Paths:**

### Path A — VIN Decode (preferred)
- User provides 17-char VIN in the analyze request
- `vin_decoder.py` calls NHTSA vPIC API (free, no key)
- Returns `Vehicle` with `confidence=1.0`
- Falls back to Path B on `VINDecodeError`

### Path B — Vision AI Auto-Detection
- Photos sent to Gemini/OpenAI vision model
- If confidence < 0.70: `vehicle_confirmation_needed=True` in response, user fills in make/model/year

**Tech:** `backend/app/services/vin_decoder.py`, `backend/app/services/vehicle_id.py`

---

## 3. Damage Detection & Severity Scoring

**What it does:** Identify which components are damaged and score severity from 0.0 to 1.0.

### Zone-based Passes (default)

Three focused LLM passes, each with a constrained component list:

| Zone | Components |
|------|-----------|
| Front | front_bumper, hood, grille, headlights (L/R), front fenders (L/R), windshield_front, a_pillars |
| Rear | rear_bumper, trunk, taillights (L/R), quarter panels (L/R), windshield_rear |
| Side | all doors (FL/FR/RL/RR), mirrors (L/R), rocker panels, b_pillars, roof, all wheels |

Results merged by worst severity per component.

### Consensus Mode (optional, `use_consensus=true`)

Runs Gemini and OpenAI in parallel via `asyncio.gather`. Averages severity scores; flags divergence ≥ 0.25. The higher-severity source's damage type and description are used.

### Calibrated Per-Component Thresholds

| Component type | Replace threshold | Rationale |
|----------------|------------------|-----------|
| Structural (a_pillar, frame) | 0.20 | Safety critical |
| Glass (windshields) | 0.15 | Safety critical |
| Safety lighting | 0.20 | Legal requirement |
| Cosmetic panels (doors, hood) | 0.35 | Industry standard |
| Rocker panels | 0.40 | Cosmetic, hard to access |

### Severity Scale

| Severity | Description | Recommendation |
|----------|-------------|----------------|
| 0.0–0.1 | Cosmetic (light scratch) | Minor repair |
| 0.1–0.3 | Minor (small dent, chip) | Repair |
| 0.3–0.6 | Moderate (significant damage) | Replace recommended |
| 0.6–0.8 | Severe (large deformation) | Replace required |
| 0.8–1.0 | Destroyed | Replace required |

**Tech:** `backend/app/services/damage_detect.py`, `backend/app/services/consensus.py`, `backend/app/prompts/damage_assessment.py`

---

## 4. Sanity Check

**What it does:** Second LLM pass that reviews the full assembled report for coherence.

**Implemented:**
- Sends full damage summary + grand total + vehicle info to LLM
- Checks: cost plausibility, severity consistency, unusual component combinations
- Returns list of warning strings appended to `assessment_warnings`

**Tech:** `backend/app/services/sanity_check.py`

---

## 5. Cost Estimation

**What it does:** Estimate total repair cost: part cost + labor cost per component.

### Part Pricing Cascade

| Priority | Method | Source |
|----------|--------|--------|
| 1st | **Live search** | SerpAPI → httpx fetch → AI price extraction |
| 2nd | **Static CSV** | `backend/app/data/parts_prices.csv` |
| 3rd | **AI estimate** | LLM estimates by vehicle market segment |

### Labor Cost

`labor_hours × labor_rate` where rate defaults to $75/hr (configurable via `.env`). Labor hours come from a static lookup dict in `cost_estimate.py`.

**Tech:** `backend/app/services/cost_estimate.py`, `backend/app/services/price_search.py`

---

## 6. Report Generation

**What it does:** Produce a human-readable PDF report.

**Implemented:**
- `report_pdf.py` renders `templates/report.html` via Jinja2
- WeasyPrint converts HTML → PDF; returns HTML bytes if WeasyPrint unavailable
- `GET /api/v1/report/{estimate_id}` endpoint
- Report includes: severity bars, cost table, totals, all warnings, disclaimer

**Tech:** `backend/app/services/report_pdf.py`, `backend/app/templates/report.html`

---

## 7. Project Phases

### Phase 0 — Pre-YOLO Reliability ✅ DONE

Improvements that increase accuracy without requiring training data:

- [x] Zone-based damage prompts (3 focused passes instead of 1 broad prompt)
- [x] Multi-model consensus mode (dual provider parallel runs)
- [x] Calibrated per-component replace/repair thresholds
- [x] Image quality gates (blur + brightness detection)
- [x] Second-pass sanity check on assembled report

### Phase 1 — Production Foundation ✅ DONE

- [x] PostgreSQL + SQLAlchemy async + Alembic migrations (`feature/phase1-database`)
- [x] Docker + docker-compose with PostgreSQL service (`feature/phase1-docker`)
- [x] PDF report generation via WeasyPrint + Jinja2 (`feature/phase1-pdf-reports`)
- [x] Next.js 15 + React 19 + TypeScript + Tailwind frontend scaffold (`feature/phase1-nextjs-frontend`)
- [x] Estimate history endpoints (`GET /api/v1/estimates`, `GET /api/v1/estimates/{id}`)
- [x] Fail-safe DB persistence (response returned even on DB error)
- [x] Image quality warnings in upload response
- [x] Angle guidance heuristic

### Phase 2 — AI Accuracy + Vehicle Data ✅ PARTIALLY DONE

- [x] VIN decoder integration — NHTSA vPIC API, free, no key (`feature/phase2-vin-decoder`)
- [x] Consensus mode — dual-provider parallel assessment
- [ ] Regional labor rate adjustment (use user location → BLS data)
- [ ] User accounts + authentication (JWT)
- [ ] Accuracy validation loop (compare estimates to real invoices)
- [ ] Image annotation (highlight damaged regions with bounding boxes)

### Phase 3 — Production Scale (planned)

- [ ] Custom YOLO model trained on car damage dataset
- [ ] Hybrid approach (YOLO region detection + LLM severity scoring per crop)
- [ ] Multi-language support
- [ ] Insurance-grade reporting format
- [ ] Admin dashboard for price database management
- [ ] A/B testing for model accuracy improvements
- [ ] Mobile-responsive frontend or dedicated mobile app
- [ ] Price result caching (24hr TTL in PostgreSQL)
- [ ] iOS/Android app

---

## 8. Key Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Vision LLM inaccuracy on severity | Wrong cost estimates | Zone prompts + consensus mode + per-component thresholds + sanity check |
| Part price data staleness | Incorrect quotes | Live search first; show pricing method in response |
| Legal liability of estimates | User relies on incorrect estimate | Disclaimer on every report: "Estimate only, not a quote" |
| API cost at scale | High operating cost | Migrate to YOLO hybrid in Phase 3; consensus mode is opt-in |
| Poor image quality | Bad analysis | Blur/brightness gates at upload; angle guidance in response |
| DB failure blocking response | Loss of estimate data | Fail-safe pattern — DB write in try/except, response always returned |

---

## 9. Directory Structure (Current)

```
car-crash-ai/
├── AGENTS.md                       # AI agent instructions + skill invocation guide
├── PROJECT_PLAN.md                 # This file
├── TECHSTACK.md                    # Technology reference
├── LEARNING.md                     # Concepts guide for new contributors
├── docker-compose.yml              # PostgreSQL + backend services
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic/
│   │   └── versions/
│   │       └── 001_initial_schema.py
│   └── app/
│       ├── main.py
│       ├── core/
│       │   ├── config.py           # Settings (includes database_url)
│       │   └── llm.py              # LLM abstraction (vision, text, dual_vision)
│       ├── api/routes/
│       │   ├── upload.py           # POST /upload
│       │   ├── analysis.py         # POST /analyze (VIN + zone/consensus + sanity)
│       │   ├── estimate.py         # GET /estimate/{id}
│       │   ├── estimates.py        # GET /estimates
│       │   └── report.py           # GET /report/{id} (PDF)
│       ├── db/
│       │   ├── session.py          # AsyncSession, get_db dependency
│       │   └── models.py           # UploadSession, EstimateRecord ORM models
│       ├── models/
│       │   ├── vehicle.py          # Vehicle (with vin field)
│       │   ├── damage.py           # DamageItem, DamageAssessment, ImageQualityWarning
│       │   └── estimate.py         # CostEstimate, AssessmentReport (with assessment_warnings)
│       ├── services/
│       │   ├── image_proc.py       # Upload processing + quality checks
│       │   ├── vehicle_id.py       # Vision-based vehicle identification
│       │   ├── vin_decoder.py      # NHTSA VIN decode
│       │   ├── damage_detect.py    # Zone-based damage detection
│       │   ├── consensus.py        # Dual-provider consensus merge
│       │   ├── sanity_check.py     # Post-report coherence check
│       │   ├── cost_estimate.py    # Part + labor cost calculation
│       │   ├── price_search.py     # Live web price search pipeline
│       │   └── report_pdf.py       # Jinja2 + WeasyPrint PDF generation
│       ├── prompts/
│       │   ├── vehicle_identification.py
│       │   └── damage_assessment.py  # Zone prompts + ALL_ZONES dict
│       └── templates/
│           └── report.html           # Jinja2 PDF report template
├── frontend-next/
│   ├── app/
│   │   ├── page.tsx                # Upload + analysis stage machine
│   │   └── history/page.tsx        # Estimate history table
│   ├── components/
│   │   ├── UploadZone.tsx          # Drag-and-drop upload
│   │   └── DamageReport.tsx        # Report display + PDF download
│   ├── lib/
│   │   └── api.ts                  # TypeScript API client
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── package.json
└── frontend/                       # Legacy Streamlit frontend (prototype)
    └── streamlit_app.py
```

---

## 10. Environment Setup

```bash
# 1. Copy env file and add API keys
cp backend/.env.example backend/.env
# Edit: GEMINI_API_KEY, OPENAI_API_KEY (optional), SERPAPI_KEY

# 2. Start services via Docker
docker-compose up --build

# 3. Run migrations (if running backend locally instead of Docker)
cd backend && alembic upgrade head

# 4. Install frontend dependencies
cd frontend-next && npm install && npm run dev

# 5. Run backend tests
cd backend && python -m pytest tests/ -v
```

Backend API docs available at `http://localhost:8000/docs` once running.
