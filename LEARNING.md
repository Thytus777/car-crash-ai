# Car Crash AI — Learning & Concepts Guide (Swift/iOS)

Everything you need to understand about the technologies, patterns, and decisions used in this iOS app. If you're coming from the Python version, each section maps the Python concept to its Swift equivalent.

---

## Table of Contents

1. [Swift & iOS Development](#1-swift--ios-development)
2. [Codable & Data Validation](#2-codable--data-validation)
3. [Vision LLM Integration (Multi-Provider)](#3-vision-llm-integration-multi-provider)
4. [Prompt Engineering for Structured Output](#4-prompt-engineering-for-structured-output)
5. [Image Processing with CoreGraphics](#5-image-processing-with-coregraphics)
6. [Live Price Search Pipeline](#6-live-price-search-pipeline)
7. [Cost Estimation Logic](#7-cost-estimation-logic)
8. [SwiftUI Frontend](#8-swiftui-frontend)
9. [Async Programming (Swift async/await)](#9-async-programming-swift-asyncawait)
10. [Configuration Management](#10-configuration-management)
11. [Testing with XCTest](#11-testing-with-xctest)
12. [AI Model Selection & Cost Guide](#12-ai-model-selection--cost-guide)
13. [Glossary](#13-glossary)

---

## 1. Swift & iOS Development

### Python → Swift mapping

| Python | Swift/iOS |
|--------|-----------|
| FastAPI backend server | No backend — app calls APIs directly |
| Pydantic `BaseModel` | `Codable` structs |
| `async def` / `await` | `async` / `await` (nearly identical syntax) |
| Pillow (PIL) | `UIImage`, `CoreGraphics`, `CoreImage` |
| `httpx.AsyncClient` | `URLSession` |
| `pydantic-settings` (.env) | `Config.plist` + `Bundle.main` |
| pytest | XCTest / Swift Testing |
| Streamlit | SwiftUI |
| google-genai SDK | GoogleGenerativeAI Swift SDK |
| openai SDK | Raw `URLSession` REST calls |

### Why no backend?

The Python version needed a FastAPI server because Streamlit (the frontend) can't call AI APIs directly. On iOS, the app has full network access — it calls Gemini and OpenAI APIs directly via `URLSession`. This eliminates the entire backend layer.

### App entry point — `CarCrashAI/App/CarCrashAIApp.swift`

```swift
import SwiftUI

@main
struct CarCrashAIApp: App {
    var body: some Scene {
        WindowGroup {
            HomeView()
        }
    }
}
```

This replaces both `backend/app/main.py` (FastAPI) and `frontend/streamlit_app.py` (Streamlit) — a single entry point for the entire app.

---

## 2. Codable & Data Validation

### What is Codable?

Swift's `Codable` protocol (combining `Encodable` + `Decodable`) lets you convert between Swift structs and JSON automatically. It replaces Pydantic's `BaseModel`.

### How we use it

**Data models** — `CarCrashAI/Models/`:

```swift
struct Vehicle: Codable {
    let make: String
    let model: String
    let year: Int
    let bodyStyle: String?
    let color: String?
    let confidence: Double

    enum CodingKeys: String, CodingKey {
        case make, model, year, color, confidence
        case bodyStyle = "body_style"
    }
}
```

**Key concepts:**
- `CodingKeys` — Maps Swift's `camelCase` property names to the LLM's `snake_case` JSON keys
- Optional properties (`String?`) — Equivalent to Pydantic's `Optional[str]`
- All properties are type-safe at compile time (no runtime validation needed like Pydantic)

**Damage model:**

```swift
struct DamageItem: Codable {
    let component: String
    let damageType: String
    let severity: Double
    let description: String

    enum CodingKeys: String, CodingKey {
        case component, severity, description
        case damageType = "damage_type"
    }
}
```

**Cost estimate with Decimal for money:**

```swift
import Foundation

struct CostEstimate: Codable {
    let component: String
    let recommendation: Recommendation
    let partCostLow: Decimal
    let partCostAvg: Decimal
    let partCostHigh: Decimal
    let laborHours: Decimal
    let laborRate: Decimal
    let laborCost: Decimal
    let totalEstimate: Decimal

    enum Recommendation: String, Codable {
        case repair
        case replace
    }
}
```

### Why Codable over dictionaries?

- Compile-time type safety (Python only catches type errors at runtime)
- Automatic JSON serialization/deserialization
- IDE autocomplete on all properties
- No external dependencies (Pydantic is a third-party library; Codable is built into Swift)

---

## 3. Vision LLM Integration (Multi-Provider)

### The AI Service Layer (`CarCrashAI/Services/AIService.swift`)

Same concept as the Python `llm.py` abstraction layer. Services call two methods — `visionCompletion()` and `textCompletion()` — and the layer handles provider selection, retries, and fallback.

```swift
final class AIService {
    static let shared = AIService()

    func visionCompletion(prompt: String, images: [Data], maxTokens: Int = 2000) async throws -> String {
        // Try primary provider, fallback to secondary
    }

    func textCompletion(prompt: String, maxTokens: Int = 500) async throws -> String {
        // Try primary provider, fallback to secondary
    }
}
```

### Provider: Gemini (default)

Uses the official `GoogleGenerativeAI` Swift SDK:

```swift
import GoogleGenerativeAI

let model = GenerativeModel(
    name: "gemini-2.5-flash",
    apiKey: Config.shared.geminiAPIKey,
    generationConfig: GenerationConfig(
        temperature: 0.2,
        maxOutputTokens: maxTokens + 8000,  // Padding for thinking tokens
        responseMIMEType: "application/json"
    )
)

// Vision call with images
let response = try await model.generateContent(
    prompt,
    images.map { ModelContent.Part.data(mimetype: "image/jpeg", $0) }
)

let text = response.text ?? ""
```

**Key details:**
- `responseMIMEType: "application/json"` — Forces valid JSON output (same as Python)
- Token padding (+8,000) for Gemini's thinking budget (same as Python)
- Images are passed as `Data` objects (JPEG bytes), not base64 strings

### Provider: OpenAI (fallback)

No official Swift SDK — we use raw `URLSession` REST calls:

```swift
func openAIVisionCompletion(prompt: String, imagesBase64: [String], maxTokens: Int) async throws -> String {
    var request = URLRequest(url: URL(string: "https://api.openai.com/v1/chat/completions")!)
    request.httpMethod = "POST"
    request.setValue("Bearer \(Config.shared.openAIAPIKey)", forHTTPHeaderField: "Authorization")
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")

    // Build content array with text + image_url blocks
    var content: [[String: Any]] = [
        ["type": "text", "text": prompt]
    ]
    for base64 in imagesBase64 {
        content.append([
            "type": "image_url",
            "image_url": [
                "url": "data:image/jpeg;base64,\(base64)",
                "detail": "high"
            ]
        ])
    }

    let body: [String: Any] = [
        "model": "gpt-4.1-mini",
        "messages": [["role": "user", "content": content]],
        "max_tokens": maxTokens,
        "temperature": 0.2
    ]

    request.httpBody = try JSONSerialization.data(withJSONObject: body)
    let (data, _) = try await URLSession.shared.data(for: request)

    // Parse response
    let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
    // Extract choices[0].message.content
    ...
}
```

### Auto-retry and provider fallback

Same logic as Python — retry up to 2 times on rate limits (HTTP 429), then fall back to the other provider:

```swift
private let maxRetries = 2
private let retryBaseDelay: TimeInterval = 10

func withRetryAndFallback<T>(
    primary: () async throws -> T,
    fallback: () async throws -> T
) async throws -> T {
    do {
        return try await withRetry(maxRetries: maxRetries, operation: primary)
    } catch let error as AIServiceError where error == .rateLimited {
        return try await withRetry(maxRetries: maxRetries, operation: fallback)
    }
}
```

---

## 4. Prompt Engineering for Structured Output

### Prompt storage

Prompts are stored as static string constants in `CarCrashAI/Prompts/`:

```swift
// CarCrashAI/Prompts/VehicleIdentification.swift
enum VehiclePrompts {
    static let identification = """
    Analyze the provided images of a vehicle. Return ONLY valid JSON:
    {
      "make": "string (manufacturer, e.g. Toyota)",
      "model": "string (e.g. Camry)",
      "year": integer,
      "body_style": "string (sedan, SUV, truck, coupe, hatchback, van, wagon)",
      "color": "string",
      "confidence": float 0.0-1.0
    }
    """
}
```

```swift
// CarCrashAI/Prompts/DamageAssessment.swift
enum DamagePrompts {
    static let assessment = """
    Analyze the provided images of a damaged vehicle. For each damaged
    component, provide:
    - component: use ONLY names from this list: [\(Components.allNames.joined(separator: ", "))]
    - damage_type: one of [scratch, dent, crack, shatter, crush, deformation, missing]
    - severity: float from 0.0 to 1.0
    - description: brief description

    Return ONLY valid JSON array.
    """
}
```

The prompts are **identical** to the Python versions — LLM prompts are language-agnostic.

### Parsing LLM responses

```swift
func parseVehicle(from jsonString: String) throws -> Vehicle {
    let data = Data(jsonString.utf8)
    return try JSONDecoder().decode(Vehicle.self, from: data)
}

func parseDamageItems(from jsonString: String) throws -> [DamageItem] {
    let data = Data(jsonString.utf8)
    return try JSONDecoder().decode([DamageItem].self, from: data)
}
```

Swift's `JSONDecoder` + `Codable` replaces Python's `json.loads()` + Pydantic validation in a single step.

---

## 5. Image Processing with CoreGraphics

### Python Pillow → iOS equivalents

| Pillow (Python) | iOS (Swift) |
|-----------------|-------------|
| `Image.open(path)` | `UIImage(contentsOfFile: path)` |
| `image.resize((w, h), Image.LANCZOS)` | `UIGraphicsImageRenderer` + `draw(in: rect)` |
| `image.convert("RGB")` | Automatic (JPEG conversion strips alpha) |
| `image.save("out.jpg", quality=90)` | `image.jpegData(compressionQuality: 0.9)` |
| `base64.b64encode(data)` | `data.base64EncodedString()` |
| HEIC handling (manual) | Native — iOS reads HEIC natively |

### Image processing code

```swift
import UIKit

enum ImageProcessor {
    /// Resize image to fit within maxDimension, maintaining aspect ratio
    static func resize(_ image: UIImage, maxDimension: CGFloat = 1024) -> UIImage {
        let size = image.size
        guard max(size.width, size.height) > maxDimension else { return image }

        let scale = maxDimension / max(size.width, size.height)
        let newSize = CGSize(width: size.width * scale, height: size.height * scale)

        let renderer = UIGraphicsImageRenderer(size: newSize)
        return renderer.image { _ in
            image.draw(in: CGRect(origin: .zero, size: newSize))
        }
    }

    /// Convert to JPEG data and base64 encode
    static func toBase64(_ image: UIImage, quality: CGFloat = 0.9) -> String? {
        image.jpegData(compressionQuality: quality)?.base64EncodedString()
    }

    /// Validate image meets minimum requirements
    static func validate(_ image: UIImage) -> Bool {
        let size = image.size
        return size.width >= 640 && size.height >= 480
    }

    /// Full processing pipeline: validate → resize → JPEG data
    static func process(_ image: UIImage) -> Data? {
        guard validate(image) else { return nil }
        let resized = resize(image)
        return resized.jpegData(compressionQuality: 0.9)
    }
}
```

### Camera & Photo Picker

```swift
import PhotosUI

struct PhotoPicker: UIViewControllerRepresentable {
    @Binding var selectedImages: [UIImage]

    func makeUIViewController(context: Context) -> PHPickerViewController {
        var config = PHPickerConfiguration()
        config.selectionLimit = 10  // 1-10 images
        config.filter = .images
        let picker = PHPickerViewController(configuration: config)
        picker.delegate = context.coordinator
        return picker
    }
    // ...
}
```

**Advantages over Python/Pillow:**
- HEIC support is native (no conversion library needed)
- Camera access is built-in
- Image rendering is hardware-accelerated via CoreGraphics

---

## 6. Live Price Search Pipeline

### Same pipeline, different HTTP client

The price search architecture is identical — Search → Fetch → AI Extract → Aggregate. The only difference is using `URLSession` instead of `httpx`.

```swift
enum PriceSearchService {
    /// Step 1: Search SerpAPI
    static func searchPrices(
        vehicle: Vehicle,
        component: String
    ) async throws -> [URL] {
        let query = "\(vehicle.year) \(vehicle.make) \(vehicle.model) \(component) price buy"
            .addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed)!

        let url = URL(string: "https://serpapi.com/search.json?q=\(query)&api_key=\(Config.shared.serpAPIKey)")!
        let (data, _) = try await URLSession.shared.data(from: url)

        let results = try JSONDecoder().decode(SerpAPIResponse.self, from: data)
        return results.organicResults.prefix(5).compactMap { URL(string: $0.link) }
    }

    /// Step 2: Fetch & extract text from pages
    static func fetchPageText(url: URL) async throws -> String {
        var request = URLRequest(url: url)
        request.timeoutInterval = 5
        let (data, _) = try await URLSession.shared.data(for: request)
        let html = String(data: data, encoding: .utf8) ?? ""
        // Basic HTML stripping — send to AI for price extraction
        return html.replacingOccurrences(of: "<[^>]+>", with: " ", options: .regularExpression)
            .prefix(2000)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// Step 3: AI price extraction (same prompt as Python)
    static func extractPrice(from text: String, vehicle: Vehicle, component: String) async throws -> PriceResult? {
        let prompt = """
        Extract pricing info for: \(vehicle.year) \(vehicle.make) \(vehicle.model) \(component).
        Text: \(String(text.prefix(2000)))
        Return ONLY valid JSON: {"price": number, "currency": "USD", "part_type": "oem|aftermarket|unknown", "confidence": 0.0-1.0}
        """
        let response = try await AIService.shared.textCompletion(prompt: prompt, maxTokens: 200)
        let data = Data(response.utf8)
        return try? JSONDecoder().decode(PriceResult.self, from: data)
    }
}
```

### No trafilatura equivalent

Python used `trafilatura` for clean HTML→text extraction. Swift has no equivalent library. Two approaches:
1. **Simple regex strip** — Remove HTML tags with regex (shown above)
2. **Send raw text to AI** — The AI is good at extracting prices from noisy text

We use approach #1 for initial cleaning, then #2 for price extraction. Works just as well.

---

## 7. Cost Estimation Logic

### Same formulas, Swift types

```swift
import Foundation

enum CostEstimation {
    static let defaultLaborRate: Decimal = 75.00
    static let severityReplaceThreshold: Double = 0.3

    /// Determine repair vs replace
    static func recommendation(severity: Double) -> CostEstimate.Recommendation {
        severity > severityReplaceThreshold ? .replace : .repair
    }

    /// Labor hours lookup (same table as Python)
    static func laborHours(component: String, recommendation: CostEstimate.Recommendation) -> Decimal {
        switch (component, recommendation) {
        case ("front_bumper", .replace): return 3.5
        case ("front_bumper", .repair):  return 1.5
        case ("hood", .replace):         return 2.5
        case ("headlight_left", .replace), ("headlight_right", .replace): return 1.0
        // ... full lookup table
        default: return 2.0
        }
    }

    /// Calculate total for one component
    static func estimate(
        component: String,
        severity: Double,
        partPrice: Decimal,
        laborRate: Decimal = defaultLaborRate
    ) -> CostEstimate {
        let rec = recommendation(severity: severity)
        let hours = laborHours(component: component, recommendation: rec)
        let labor = hours * laborRate
        return CostEstimate(
            component: component,
            recommendation: rec,
            partCostAvg: partPrice,
            laborHours: hours,
            laborRate: laborRate,
            laborCost: labor,
            totalEstimate: partPrice + labor
        )
    }
}
```

### Money handling

- All monetary values use `Decimal` (Foundation) — same rule as Python
- Never use `Double` for money (floating-point errors)
- Format for display: `NumberFormatter` with `.currency` style

```swift
let formatter = NumberFormatter()
formatter.numberStyle = .currency
formatter.currencyCode = "USD"
let display = formatter.string(from: estimate.totalEstimate as NSDecimalNumber)
// "$1,234.56"
```

---

## 8. SwiftUI Frontend

### What is SwiftUI?

SwiftUI is Apple's declarative UI framework. You describe *what* the UI should look like, and SwiftUI handles rendering and updates automatically. It replaces Streamlit entirely.

### View structure

```swift
// HomeView.swift — Main screen
struct HomeView: View {
    @State private var selectedImages: [UIImage] = []
    @State private var isAnalyzing = false
    @State private var report: AssessmentReport?

    var body: some View {
        NavigationStack {
            VStack {
                // Photo picker / camera button
                PhotoPickerButton(images: $selectedImages)

                // Analyze button
                Button("🔍 Analyze Damage") {
                    Task { await analyzeDamage() }
                }
                .disabled(selectedImages.isEmpty || isAnalyzing)

                // Results
                if let report {
                    NavigationLink("View Report") {
                        ReportView(report: report)
                    }
                }
            }
            .navigationTitle("Car Crash AI")
        }
    }
}
```

### Key SwiftUI concepts

| Concept | What it does | Python equivalent |
|---------|-------------|-------------------|
| `@State` | Local view state that triggers re-render on change | `st.session_state` |
| `@Binding` | Two-way reference to a parent's `@State` | Passing state between Streamlit components |
| `NavigationStack` | Screen navigation | Streamlit page routing |
| `Task { }` | Run async work from synchronous context | `asyncio.create_task()` |
| `ProgressView()` | Loading spinner | `st.spinner()` |
| `.sheet()` | Modal overlay | `st.dialog()` |

### ReportView example

```swift
struct ReportView: View {
    let report: AssessmentReport

    var body: some View {
        List {
            // Vehicle info
            Section("Vehicle") {
                LabeledContent("Make", value: report.vehicle.make)
                LabeledContent("Model", value: report.vehicle.model)
                LabeledContent("Year", value: "\(report.vehicle.year)")
            }

            // Damage items with severity bars
            Section("Damage Assessment") {
                ForEach(report.damages, id: \.component) { damage in
                    VStack(alignment: .leading) {
                        Text(damage.component.replacingOccurrences(of: "_", with: " ").capitalized)
                            .font(.headline)
                        ProgressView(value: damage.severity)
                            .tint(severityColor(damage.severity))
                        Text(damage.description)
                            .font(.caption)
                    }
                }
            }

            // Cost breakdown
            Section("Cost Estimate") {
                ForEach(report.estimates, id: \.component) { est in
                    HStack {
                        Text(est.component.replacingOccurrences(of: "_", with: " ").capitalized)
                        Spacer()
                        Text(est.totalEstimate, format: .currency(code: "USD"))
                    }
                }
                Divider()
                HStack {
                    Text("Grand Total").bold()
                    Spacer()
                    Text(report.grandTotal, format: .currency(code: "USD")).bold()
                }
            }
        }
        .navigationTitle("Damage Report")
    }

    func severityColor(_ severity: Double) -> Color {
        switch severity {
        case 0..<0.3: return .green
        case 0.3..<0.6: return .yellow
        case 0.6..<0.8: return .orange
        default: return .red
        }
    }
}
```

---

## 9. Async Programming (Swift async/await)

### Python vs Swift async

The syntax is nearly identical:

**Python:**
```python
async def identify_vehicle(images: list[str]) -> Vehicle:
    response = await vision_completion(prompt=PROMPT, images_b64=images)
    return parse_vehicle(response)
```

**Swift:**
```swift
func identifyVehicle(images: [Data]) async throws -> Vehicle {
    let response = try await AIService.shared.visionCompletion(prompt: VehiclePrompts.identification, images: images)
    return try parseVehicle(from: response)
}
```

### Key differences

| Python | Swift |
|--------|-------|
| `async def foo():` | `func foo() async throws {` |
| `await bar()` | `try await bar()` |
| `asyncio.gather(a, b)` | `async let a = ...; async let b = ...` |
| `asyncio.sleep(n)` | `try await Task.sleep(for: .seconds(n))` |
| `try: except:` | `do { try } catch { }` |

### Concurrent AI calls

```swift
func analyzeVehicle(images: [Data]) async throws -> AssessmentReport {
    // Run vehicle ID and damage detection concurrently
    async let vehicle = VehicleIDService.identify(images: images)
    async let damages = DamageDetectService.detect(images: images)

    let v = try await vehicle
    let d = try await damages

    // Cost estimation depends on vehicle + damages
    let estimates = try await CostEstimateService.estimate(vehicle: v, damages: d)

    return AssessmentReport(vehicle: v, damages: d, estimates: estimates)
}
```

### Calling async from SwiftUI

```swift
Button("Analyze") {
    Task {
        isAnalyzing = true
        defer { isAnalyzing = false }
        do {
            report = try await analyzeVehicle(images: processedImages)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
```

---

## 10. Configuration Management

### Python .env → iOS Config.plist

**Python (pydantic-settings):**
```python
class Settings(BaseSettings):
    model_config = {"env_file": ".env"}
    gemini_api_key: str = ""
    ai_provider: str = "gemini"
```

**Swift (Config.plist):**
```swift
enum Config {
    static let shared = Config()

    let geminiAPIKey: String
    let openAIAPIKey: String
    let serpAPIKey: String
    let aiProvider: String
    let laborRatePerHour: Decimal

    private init() {
        guard let path = Bundle.main.path(forResource: "Config", ofType: "plist"),
              let dict = NSDictionary(contentsOfFile: path) as? [String: Any] else {
            fatalError("Config.plist not found")
        }

        geminiAPIKey = dict["GEMINI_API_KEY"] as? String ?? ""
        openAIAPIKey = dict["OPENAI_API_KEY"] as? String ?? ""
        serpAPIKey = dict["SERPAPI_KEY"] as? String ?? ""
        aiProvider = dict["AI_PROVIDER"] as? String ?? "gemini"
        laborRatePerHour = Decimal(dict["LABOR_RATE_PER_HOUR"] as? Double ?? 75.0)
    }
}
```

### Security

- `Config.plist` is added to `.gitignore` — never committed
- For production, use iOS Keychain for API key storage
- A `Config.plist.example` is committed with placeholder values

---

## 11. Testing with XCTest

### Python pytest → Swift XCTest

| pytest (Python) | XCTest (Swift) |
|-----------------|----------------|
| `def test_foo():` | `func testFoo() throws { }` |
| `@pytest.mark.asyncio` | `func testFoo() async throws { }` |
| `assert x == y` | `XCTAssertEqual(x, y)` |
| `with patch(...)` | `URLProtocol` subclass for network mocking |
| `conftest.py` fixtures | `setUp()` / `tearDown()` methods |

### Service test example

```swift
import XCTest
@testable import CarCrashAI

final class VehicleIDTests: XCTestCase {
    func testParseVehicleFromJSON() throws {
        let json = """
        {"make": "Ford", "model": "Mustang", "year": 2022, "confidence": 0.95}
        """
        let vehicle = try JSONDecoder().decode(Vehicle.self, from: Data(json.utf8))
        XCTAssertEqual(vehicle.make, "Ford")
        XCTAssertEqual(vehicle.year, 2022)
        XCTAssertGreaterThan(vehicle.confidence, 0.9)
    }

    func testSeverityThreshold() {
        XCTAssertEqual(CostEstimation.recommendation(severity: 0.2), .repair)
        XCTAssertEqual(CostEstimation.recommendation(severity: 0.5), .replace)
        XCTAssertEqual(CostEstimation.recommendation(severity: 0.3), .repair)  // Edge: ≤ 0.3 = repair
        XCTAssertEqual(CostEstimation.recommendation(severity: 0.31), .replace)
    }
}
```

### Mocking network calls

```swift
class MockURLProtocol: URLProtocol {
    static var mockResponseData: Data?
    static var mockStatusCode: Int = 200

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        let response = HTTPURLResponse(
            url: request.url!, statusCode: Self.mockStatusCode,
            httpVersion: nil, headerFields: nil
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        if let data = Self.mockResponseData {
            client?.urlProtocol(self, didLoad: data)
        }
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}
```

### Test structure

```
CarCrashAITests/
├── ModelTests.swift          # Codable model tests
├── VehicleIDTests.swift      # Vehicle identification
├── DamageDetectTests.swift   # Damage detection
├── CostEstimateTests.swift   # Cost estimation
├── ImageProcessorTests.swift # Image processing
└── AIServiceTests.swift      # AI service layer (mocked network)
```

---

## 12. AI Model Selection & Cost Guide

### Current setup

| Task | Model (default) | Fallback | Why |
|------|----------------|----------|-----|
| Vehicle ID | `gemini-2.5-flash` | `gpt-4.1-mini` | Free tier for dev, excellent vision |
| Damage Detection | `gemini-2.5-flash` | `gpt-4.1-mini` | Same model, high accuracy |
| Price Estimation | `gemini-2.5-flash` | `gpt-4.1-nano` | Text-only, cheapest option |

### Google Gemini

| Model | Input $/1M | Output $/1M | Vision? | Free tier? | Notes |
|-------|-----------|------------|---------|------------|-------|
| **gemini-2.5-flash** | $0.30 | $2.50 | ✅ | ✅ Yes | Default. Thinking model |
| gemini-2.5-flash-lite | $0.10 | $0.40 | ✅ | ✅ Yes | Cheaper, lower quality |

### OpenAI GPT-4.1 family

| Model | Input $/1M | Output $/1M | Vision? | Notes |
|-------|-----------|------------|---------|-------|
| gpt-4.1 | $2.00 | $8.00 | ✅ | Best non-reasoning |
| **gpt-4.1-mini** | $0.40 | $1.60 | ✅ | Vision fallback |
| **gpt-4.1-nano** | $0.10 | $0.40 | ✅ | Text fallback |

### How to switch models

Change values in `Config.plist`:
```xml
<key>AI_PROVIDER</key>
<string>gemini</string>  <!-- or "openai" -->
```

The provider not selected as primary becomes the automatic fallback.

---

## 13. Glossary

| Term | Definition |
|------|-----------|
| **async/await** | Swift's built-in concurrency for non-blocking I/O |
| **Codable** | Swift protocol for automatic JSON encoding/decoding |
| **Config.plist** | Property list file for app configuration (API keys, settings) |
| **CoreGraphics** | Apple's low-level 2D drawing framework (image resize, render) |
| **CoreImage** | Apple's image processing framework (filters, analysis) |
| **Decimal** | Foundation type for exact decimal arithmetic (money) |
| **GenerativeModel** | GoogleGenerativeAI SDK class for calling Gemini models |
| **HEIC** | High Efficiency Image Container — iOS's default photo format |
| **Keychain** | iOS secure storage for credentials (production API keys) |
| **NavigationStack** | SwiftUI container for push/pop screen navigation |
| **PHPicker** | iOS system photo picker (replaces manual gallery access) |
| **SPM** | Swift Package Manager — dependency management (like pip) |
| **SwiftData** | Apple's persistence framework (like SQLAlchemy for iOS) |
| **SwiftUI** | Apple's declarative UI framework |
| **Task** | Swift concurrency primitive for launching async work |
| **UIImage** | UIKit class representing an image in memory |
| **URLProtocol** | Foundation class for intercepting/mocking network requests in tests |
| **URLSession** | Foundation class for HTTP networking (like httpx) |
| **XCTest** | Apple's testing framework (like pytest) |

---

*Last updated: March 17, 2026. AI model prices are subject to change — check provider websites for current rates.*
