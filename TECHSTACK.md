# Technology Stack

Reference document for all technologies used in the Car Crash AI project, how they fit together, and how the system works end-to-end.

---

## How the Project Works

### What this project does

Car Crash AI is a native iOS application that takes photos of a damaged vehicle and produces a full repair cost estimate. A user captures or selects photos, the app identifies the vehicle, detects every damaged component, looks up part prices, calculates labor costs, and returns a complete report — all powered by AI vision models called directly from the device.

### End-to-end flow

When a user taps "Analyze Damage" in the app, this is what happens:

```
User takes/selects photos
   (PHPicker / Camera)
        │
        ▼
┌─────────────────────────────────────────┐
│  1. IMAGE PREPROCESSING                │
│     CoreGraphics resize to 1024×1024   │
│     JPEG compress (quality 0.9)        │
│     Base64-encode for API payloads     │
└─────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────┐
│  2. VEHICLE ID  (vision LLM call)      │
│     Send photos to Gemini/OpenAI       │
│     "What make/model/year is this car?"│
│     Decode JSON → Vehicle model        │
│     If confidence < 70%: ask user      │
└─────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────┐
│  3. DAMAGE DETECTION  (vision LLM call)│
│     Send photos to Gemini/OpenAI       │
│     "What parts are damaged? How bad?" │
│     Decode JSON → [DamageItem]         │
│     Each: component, type, severity    │
└─────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────┐
│  4. COST ESTIMATION  (per component)   │
│                                        │
│     For each damaged component:        │
│     ┌─ Try live price search (SerpAPI) │
│     │  Search Google → Fetch pages →   │
│     │  AI extracts prices from text    │
│     ├─ Fallback: bundled CSV database  │
│     ├─ Fallback: AI price estimation   │
│     │  "Estimate cost of a BMW hood"   │
│     └─ Last resort: default $300       │
│                                        │
│     + Labor cost (hours × $75/hr rate) │
└─────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────┐
│  5. REPORT                             │
│     SwiftUI ReportView                 │
│     Vehicle info + damage list +       │
│     per-component cost breakdown +     │
│     parts total + labor total +        │
│     grand total + disclaimer           │
└─────────────────────────────────────────┘
        │
        ▼
   User sees results in ReportView
```

### The three AI calls

The app makes up to three types of AI calls per analysis:

| Call | Type | Input | Output | Model |
|------|------|-------|--------|-------|
| **Vehicle ID** | Vision | Photos + prompt | `{"make": "BMW", "model": "3 Series", "year": 2020, "confidence": 0.92}` | gemini-2.5-flash |
| **Damage Detection** | Vision | Photos + prompt | `[{"component": "front_bumper", "severity": 0.7, ...}, ...]` | gemini-2.5-flash |
| **Price Estimation** | Text | Vehicle + component | `{"price_low": 180, "price_avg": 280, "price_high": 450}` | gemini-2.5-flash |

All three go through the same abstraction layer (`AIService.swift`), which handles provider selection, retries, and fallback automatically.

### On-device architecture

There is no backend server. The app calls all external APIs (Gemini, OpenAI, SerpAPI) directly from the device via URLSession. This eliminates server costs, simplifies deployment, and keeps the architecture as a single iOS target.

### Price estimation cascade

Part pricing uses a three-tier fallback to always return a result:

| Priority | Method | Source | When used |
|----------|--------|--------|-----------|
| 1st | **Live search** | Google via SerpAPI → fetch pages → AI extracts prices | SerpAPI key set, results found |
| 2nd | **Static CSV** | Bundled `parts_prices.csv` in app bundle | Vehicle/component match exists in CSV |
| 3rd | **AI estimate** | LLM estimates based on vehicle segment | No live or static data available |

The AI estimate is vehicle-aware — it knows a BMW hood costs more than a Toyota hood, and a mirror costs less than a quarter panel.

---

## 1. Language & Platform

| Technology | Version | Purpose |
|---|---|---|
| **Swift** | 5.9+ | Primary language |
| **iOS** | 17.0+ | Target platform |
| **SwiftUI** | — | Declarative UI framework |
| **Xcode** | 15+ | IDE and build system |

**Why Swift/iOS native:** Direct access to camera and photo library APIs, first-class async/await concurrency, strong type safety with Codable for JSON parsing, and no server infrastructure required — the app calls AI APIs directly from the device.

---

## 2. AI / LLM Providers

| Package | Version | Models Used | Role |
|---|---|---|---|
| **google-generative-ai** (Swift SDK) | ≥0.5.0 | `gemini-2.5-flash` | Default provider (vision + text) |
| **OpenAI REST API** (via URLSession) | — | `gpt-4.1-mini` (vision), `gpt-4.1-nano` (text) | Fallback provider |

### Provider Architecture

A custom abstraction layer in `AIService.swift` exposes two async methods:

- `visionCompletion(prompt:imagesBase64:...) async throws -> String` — for damage analysis from photos
- `textCompletion(prompt:...) async throws -> String` — for price extraction from fetched text

**Key design decisions:**

- **Multi-provider support** — Gemini is the default (free tier available for development); OpenAI is the automatic fallback when Gemini is rate-limited
- **Automatic retry** — Up to 2 retries with exponential backoff on 429/RESOURCE_EXHAUSTED errors, parsing `retryDelay` from error responses
- **Seamless fallback** — If the primary provider exhausts retries, the system switches to the other provider transparently
- **Thinking model support** — Gemini 2.5 models get extra token padding (+8,000 tokens) and a thinking budget (512 tokens) since reasoning tokens count against output limits
- **Provider switching** — Controlled via `Config.plist` key `AIProvider` (`"gemini"` or `"openai"`)
- **OpenAI without SDK** — OpenAI calls use raw URLSession with manually constructed JSON payloads, avoiding a third-party dependency for the fallback provider

---

## 3. Image Processing

| Technology | Purpose |
|---|---|
| **UIImage** | Loading and representing images from camera/picker |
| **CoreImage** | Image filtering and adjustments |
| **CoreGraphics** | Resize, crop, and pixel-level manipulation |

Used in the image preprocessing pipeline to:

- Validate selected images (size limits, minimum resolution 640×480, format check)
- Resize to 1024×1024 max using `CGContext` with high-quality interpolation
- Convert to JPEG representation (compression quality 0.9)
- Encode processed images as base64 strings for LLM API calls

---

## 4. Camera & Photo Selection

| Technology | Purpose |
|---|---|
| **PHPickerViewController** | Modern photo library picker (iOS 14+), multi-select, no permissions prompt for read-only |
| **UIImagePickerController** | Camera capture for taking new photos |

**Why both:** PHPicker handles gallery selection without requiring photo library permissions (privacy-first). UIImagePickerController provides the camera interface. Both are wrapped in SwiftUI via `UIViewControllerRepresentable` for seamless integration.

---

## 5. Networking & Web Scraping

| Technology | Purpose |
|---|---|
| **URLSession** | All HTTP requests (AI APIs, SerpAPI, web page fetching) |

Used in the live price search pipeline:

1. **Search** — URLSession calls SerpAPI with query `"{year} {make} {model} {component} price buy"`, returns top 5 URLs
2. **Fetch** — URLSession fetches each URL with 5s timeout and redirect following
3. **Extract** — Raw HTML text is extracted via Swift string processing (strip tags, decode entities, truncate to 2,000 chars per page)
4. **Price parsing** — LLM `textCompletion` extracts structured price data (price, currency, part type, stock status) from each snippet
5. **Filter** — Results below 50% confidence are discarded

**Why URLSession over Alamofire:** URLSession's native async/await API (`data(for:)`) is clean and sufficient. No need for a third-party HTTP library when all calls are straightforward REST requests with JSON bodies.

**Why no trafilatura equivalent:** Swift has no mature HTML-to-text extraction library comparable to trafilatura. Instead, the raw fetched HTML is stripped of tags via string processing and the AI model handles content extraction from the cleaned text — the LLM is robust enough to parse useful information from imperfect text.

---

## 6. Data Validation

| Technology | Purpose |
|---|---|
| **Codable** (Swift protocol) | JSON encoding/decoding for all API request and response models |
| **JSONDecoder / JSONEncoder** | Configured with `.convertFromSnakeCase` key strategy |

All data models (`Vehicle`, `DamageItem`, `CostEstimate`, `AnalysisReport`) conform to `Codable`. LLM responses are decoded from JSON strings using `JSONDecoder`, with validation handled by Swift's strong typing — malformed responses throw `DecodingError` and trigger retries.

---

## 7. Configuration & Secrets

| Storage | Purpose |
|---|---|
| **Config.plist** | Development API keys, model names, labor rate, feature flags |
| **Keychain** (via Security framework) | Production API key storage (encrypted, persistent) |
| **UserDefaults** | Non-sensitive preferences (selected provider, last-used settings) |

**Why Config.plist + Keychain:** Plist files provide typed, structured configuration that Xcode supports natively. Keychain provides OS-level encryption for production API keys, which should never live in plaintext plist files shipped in the app bundle. The app reads from Keychain first, falling back to Config.plist for development convenience.

---

## 8. Frontend (UI)

| Technology | Purpose |
|---|---|
| **SwiftUI** | All views and navigation |

**Why SwiftUI:** Declarative syntax reduces boilerplate, native support for async state management with `@State` and `@Observable`, built-in animations and transitions for loading states and result presentation. iOS 17+ minimum allows use of the latest SwiftUI features including `@Observable` macro and `NavigationStack`.

Key views:

- **PhotoSelectionView** — Multi-image selection (1–10) via PHPicker, camera capture option, image preview grid
- **AnalysisView** — Progress indicators for each pipeline step, optional vehicle info override
- **ReportView** — Vehicle info, damage list with severity indicators, per-component cost breakdown, parts/labor/grand totals, disclaimer
- **SettingsView** — Provider selection, API key entry (stored in Keychain), labor rate configuration

---

## 9. Data & Storage

| Storage | Format | Purpose |
|---|---|---|
| **Bundled CSV** | `.csv` | Static parts price database (compiled into app bundle) |
| **SwiftData** | SQLite (managed) | Cached analysis results and price lookups |
| **UserDefaults** | Key-value | User preferences and non-sensitive settings |

**Why no remote database:** The app calls APIs directly from the device. All state is local — SwiftData provides lightweight persistence for caching previous estimates and price lookups. The bundled CSV ships with the app and can be updated with app releases.

---

## 10. Testing

| Framework | Purpose |
|---|---|
| **XCTest** | Unit tests, UI tests, performance tests |
| **Swift Testing** | Modern test framework with `@Test` macro and `#expect` assertions |
| **URLProtocol** | Mocking network requests by intercepting URLSession traffic |

Tests mock all external API calls using custom `URLProtocol` subclasses registered with test URLSession configurations. No real API calls are made during testing.

---

## 11. Architecture Decisions

| Decision | Rationale |
|---|---|
| **No backend server** | Eliminates server costs and infrastructure. All API calls go directly from device to provider. API keys stored securely in Keychain |
| **Multi-provider LLM** | Cost optimization (Gemini free tier for dev), reliability (automatic fallback on rate limits), no vendor lock-in |
| **Swift async/await** | All operations are I/O-bound (LLM API calls, web fetching). Structured concurrency with async/await keeps code readable and handles concurrent requests naturally |
| **SwiftUI over UIKit** | Declarative UI reduces boilerplate, native state management, modern iOS development standard. iOS 17+ minimum allows full use of `@Observable` and `NavigationStack` |
| **No Alamofire** | URLSession's native async API is sufficient for REST calls with JSON payloads. Avoids unnecessary dependency for straightforward HTTP requests |
| **Codable over manual parsing** | Swift's type system catches malformed API responses at compile time. Codable provides automatic JSON serialization with zero boilerplate |
| **SerpAPI over direct scraping** | Reliable Google results without anti-bot issues. Pay-per-search pricing aligns with usage patterns |
| **AI text extraction over HTML parser** | No Swift equivalent to trafilatura exists. The LLM handles noisy text well enough, and this avoids maintaining a fragile HTML extraction pipeline |
| **Config.plist + Keychain** | Plist for structured dev config, Keychain for encrypted production secrets. Standard iOS patterns, no third-party config libraries needed |
| **SwiftData over Core Data** | Modern Swift-native persistence with less boilerplate. Sufficient for caching estimates and price lookups. iOS 17+ minimum makes this viable |
