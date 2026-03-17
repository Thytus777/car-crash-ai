# Car Crash Damage Detection & Assessment AI — Project Plan

## Overview

A native iOS app built with Swift and SwiftUI that captures photos of a damaged vehicle, identifies the vehicle via AI, detects damage per component with severity scoring, and estimates repair costs — all on-device with direct API calls to cloud AI providers (no backend server required).

---

## High-Level Flow

```
User takes / selects photos (Camera + PHPicker)
        │
        ▼
┌─────────────────────┐
│  Image Preprocessing │  ← validate, resize, normalize (UIImage / CoreImage)
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ Vehicle Identification│  ← AI detection OR manual entry fallback
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
│ Cost Estimation          │  ← part prices (SerpAPI + CSV fallback) + labor
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Report View              │  ← structured on-screen report (SwiftUI)
└─────────────────────────┘
```

---

## 1. Image Input & Preprocessing

**What it does:** Accept 1–10 images of the damaged vehicle (front, rear, sides, close-ups) via the device camera or photo library.

**Details:**
- **Camera capture:** `AVCaptureSession` via a custom `CameraView` (UIViewControllerRepresentable wrapping UIImagePickerController or AVFoundation)
- **Photo library:** `PHPickerViewController` for multi-image selection
- Supported formats: JPEG, PNG, HEIC (native iOS support — no conversion needed)
- Validate: minimum resolution (640×480), file size limits (≤ 20 MB each)
- Resize to a consistent resolution for the AI model (e.g., 1024×1024) using `CoreGraphics`
- Convert to JPEG `Data` for API upload; strip EXIF where not needed

**Tech:** `UIImage`, `CoreImage`, `CoreGraphics`, `PhotosUI` (PHPicker).

---

## 2. Vehicle Identification

**What it does:** Determine the make, model, year, and trim of the vehicle.

**Approach — Two Paths (try AI first, fall back to user):**

### Path A — Vision AI Auto-Detection
- Send one or more clear images to a Vision LLM (Gemini or OpenAI)
- Prompt: *"Identify the make, model, approximate year, and body style of this vehicle."*
- Parse structured JSON response
- Confidence threshold: if the model returns confidence < 0.7, fall back to Path B

### Path B — User Manual Entry Fallback
- Present a SwiftUI form: "We couldn't confidently identify your vehicle. Please provide: Make, Model, Year"
- Validate against a static vehicle dataset bundled in-app

**Why this matters:** Vehicle identity determines part catalog, part prices, and labor rates.

**Data sources for vehicle data:**

| Source | Cost | Notes |
|--------|------|-------|
| NHTSA VIN Decoder API | Free | Decode VIN → make/model/year (URLSession call) |
| Static dataset (bundled CSV) | Free | Offline reference, bundled in app |

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

Use Google Gemini (default) or OpenAI GPT-4 Vision (fallback) with structured output prompting:

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
> CoreML model for fast on-device damage region detection and feed those crops into the
> Vision LLM for detailed severity scoring (hybrid approach).

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

No single parts database covers every vehicle. Instead, the app searches the web via SerpAPI,
fetches snippets, and uses AI to extract structured pricing data — all from on-device URLSession calls.

#### Architecture: Search → Extract → Aggregate

```
App sends query:  "Toyota Corolla 2018 front bumper"
        │
        ▼
┌──────────────────────────┐
│ Step 1 — Search API       │  SerpAPI via URLSession GET
│                           │  Query: "{year} {make} {model} {component} price buy"
│                           │  Returns: top 5 result URLs + snippets (JSON)
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ Step 2 — AI Price Extract │  Send search snippets to Gemini / OpenAI
│                           │  "Extract the product price, currency, and whether
│                           │   it's OEM or aftermarket from this text."
│                           │  Returns structured JSON per result
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ Step 3 — Aggregate        │  Collect prices from all results
│                           │  Return: { low, avg, high, currency, sources[] }
│                           │  Cache result in UserDefaults (24hr TTL)
└──────────────────────────┘
```

#### Search API

| Provider | Free Tier | Paid | Notes |
|----------|-----------|------|-------|
| **SerpAPI** | 100 searches/mo | $50/mo for 5,000 | Best structured results, called via URLSession |

> **Recommendation:** Start with **SerpAPI** (100 free/mo is enough for development).

#### AI Price Extraction Prompt

```
Given the following search snippets for the car part: {year} {make} {model} {component}.

Text:
---
{snippet_text}
---

Return ONLY valid JSON:
{
  "price": <number or null if not found>,
  "currency": "<3-letter code, e.g. AUD, USD>",
  "part_type": "<oem | aftermarket | unknown>",
  "in_stock": <true | false | null>,
  "product_name": "<exact product name from snippet>",
  "confidence": <0.0 to 1.0>
}
```

#### Caching & Fallback

- **Cache:** Store search results + extracted prices in `UserDefaults` for 24 hours
  - Key: `{make}_{model}_{year}_{component}`
  - Avoids redundant API calls for the same vehicle/part combo
- **Fallback:** If live search fails (API down, no results, all extractions low-confidence):
  - Fall back to the static reference CSV bundled in the app
  - Flag the estimate as "based on reference data, not live pricing"

#### Static Fallback Database

- File: `CarCrashAI/Data/parts_prices.csv`
- Schema: `make,model,year_start,year_end,component,avg_price,currency,source,last_updated`
- Covers top 30 vehicles × 20 common parts = 600 rows
- Updated manually as a baseline safety net

### Labor Cost Estimation

Labor is typically estimated as: `labor_hours × hourly_rate`

- **Labor hours:** Use flat-rate labor guides (e.g., Mitchell, ALLDATA) that define standard hours per repair operation
- **Hourly rate:** Varies by region ($50–$150/hr in the US). Can use:
  - User-input location → regional average
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

## 5. Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **Platform** | iOS 17+ / Swift 5.9+ / SwiftUI | Native performance, camera access, modern declarative UI |
| **AI — Primary** | Google Gemini (`google-generative-ai` Swift SDK) | Vehicle ID + damage detection + price extraction |
| **AI — Fallback** | OpenAI GPT-4 Vision (URLSession REST calls) | Redundancy if Gemini is unavailable |
| **Image Processing** | UIImage / CoreImage / CoreGraphics | Native iOS — resize, compress, format conversion |
| **Camera** | AVFoundation / UIImagePickerController | Photo capture with flash, focus, exposure control |
| **Photo Picker** | PHPickerViewController (PhotosUI) | Multi-image selection from photo library |
| **Price Search** | SerpAPI via URLSession HTTP calls | Live web search for part prices |
| **Static Data** | Bundled CSV (parts_prices.csv) | Fallback price reference, no network needed |
| **Local Storage** | UserDefaults (cache) / SwiftData (Phase 2) | Price cache (24hr TTL), estimate history |
| **Configuration** | Config.plist | API keys and settings (gitignored) |
| **Testing** | XCTest / XCUITest | Unit and UI testing |
| **Build** | Xcode 15+ | Code written on Windows (Swift files), built on Mac |

---

## 6. Project Phases

### Phase 1 — MVP (4–6 weeks)
- [ ] Camera capture view (AVFoundation / UIImagePickerController)
- [ ] Photo library picker (PHPicker, multi-image)
- [ ] Image preprocessing (resize, compress via CoreGraphics)
- [ ] Vehicle identification via Gemini Vision (OpenAI fallback)
- [ ] Damage detection via Gemini Vision with structured JSON output
- [ ] Severity scoring + repair/replace recommendations
- [ ] Live price search pipeline (SerpAPI → AI extract via URLSession)
- [ ] Static parts price CSV as fallback (bundled in app)
- [ ] Simple labor cost estimation (national average $75/hr)
- [ ] Report view in SwiftUI (scrollable damage list + cost breakdown)
- [ ] Config.plist for API keys

### Phase 2 — Enhanced (6–8 weeks)
- [ ] SwiftData persistence for estimate history
- [ ] PDF report export (UIGraphicsPDFRenderer)
- [ ] VIN barcode scanner (AVFoundation + NHTSA API decode)
- [ ] Regional labor rate adjustment (user-selected location)
- [ ] Image annotation (highlight damaged areas with CoreGraphics overlays)
- [ ] Settings screen (labor rate, currency, default AI provider)

### Phase 3 — Production (8–12 weeks)
- [ ] On-device CoreML model for fast damage region detection
- [ ] Hybrid approach (CoreML detection + LLM severity assessment)
- [ ] Apple Pay integration for premium features
- [ ] Share sheet (UIActivityViewController for sharing reports)
- [ ] Push notifications (estimate ready, price updates)
- [ ] Multi-language support (String Catalogs / Localizable)
- [ ] App Store submission + TestFlight beta

---

## 7. Key Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Vision LLM inaccuracy on severity | Wrong cost estimates | Calibrate with real assessor data; allow user override in ReportView |
| Part price data staleness | Incorrect quotes | Refresh prices via SerpAPI; show date of last update; CSV fallback |
| Legal liability of estimates | User relies on incorrect estimate | Add disclaimers: "Estimate only, not a quote" |
| API cost at scale | High operating cost per user | Migrate to on-device CoreML model in Phase 3 |
| Poor image quality from phone camera | Bad analysis | Validate image quality before upload; guide user on photo angles with overlay hints |
| API keys exposed in app binary | Security risk | Store keys in Config.plist (gitignored); consider App Attest + server proxy for production |
| No network connectivity | App unusable without APIs | Graceful offline fallback: static CSV prices, cached estimates via UserDefaults |
| App Store review rejection | Delayed launch | Follow Apple Human Interface Guidelines; no private API usage |

---

## 8. Directory Structure

```
car-crash-ai/
├── CarCrashAI/
│   ├── App/
│   │   └── CarCrashAIApp.swift         # @main App entry point
│   ├── Views/
│   │   ├── HomeView.swift              # Landing screen, start new assessment
│   │   ├── CameraView.swift            # Camera capture + PHPicker
│   │   ├── AnalysisView.swift          # Progress view during AI analysis
│   │   └── ReportView.swift            # Damage report + cost breakdown
│   ├── Models/
│   │   ├── Vehicle.swift               # Vehicle data model (make, model, year)
│   │   ├── DamageItem.swift            # Per-component damage (severity, type)
│   │   └── CostEstimate.swift          # Cost breakdown (parts, labor, totals)
│   ├── Services/
│   │   ├── AIService.swift             # AI provider abstraction (Gemini + OpenAI)
│   │   ├── VehicleIDService.swift      # Vehicle identification pipeline
│   │   ├── DamageDetectService.swift   # Damage detection pipeline
│   │   ├── CostEstimateService.swift   # Cost estimation pipeline
│   │   ├── PriceSearchService.swift    # SerpAPI search + AI price extraction
│   │   └── ImageProcessor.swift        # Resize, compress, format conversion
│   ├── Prompts/
│   │   ├── VehicleIdentification.swift # Prompt templates for vehicle ID
│   │   └── DamageAssessment.swift      # Prompt templates for damage detection
│   ├── Data/
│   │   └── parts_prices.csv            # Static fallback parts price reference
│   └── Resources/
│       └── Config.plist                # API keys (gitignored)
├── CarCrashAITests/                    # XCTest unit tests
├── .agents/skills/                     # Amp agent skills
├── PROJECT_PLAN.md
├── TECHSTACK.md
├── LEARNING.md
├── SETUP.md
└── README.md
```

---

## 9. Getting Started (Next Steps)

1. **Create the Xcode project skeleton** — Set up `CarCrashAI` target with SwiftUI lifecycle, folder structure, and `Config.plist`
2. **Build CameraView** — Implement camera capture and PHPicker for multi-image selection
3. **Integrate Google Gemini** — Add `google-generative-ai` Swift SDK via SPM; implement `AIService` with Gemini as default provider
4. **Add OpenAI fallback** — Implement raw URLSession REST calls to OpenAI Vision API in `AIService`
5. **Build the prompt engineering** — Iterate on prompts in `Prompts/` to get reliable structured JSON output
6. **Create the static parts database** — Populate `parts_prices.csv` with prices for common vehicles/parts
7. **Wire up the full pipeline** — HomeView → CameraView → AnalysisView → ReportView
8. **Test with real crash images** — Validate accuracy on Mac via Xcode Simulator, tune severity thresholds
