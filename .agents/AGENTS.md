# Car Crash AI — Agent Instructions

## Project Overview

This is a **car crash damage detection and assessment AI** built as a native Swift/SwiftUI iOS app with a Vision LLM (Gemini) for image analysis. The app accepts vehicle photos, identifies the vehicle, detects damage per component, scores severity, and estimates repair/replacement costs — all on-device with direct API calls.

## Architecture

- **Platform:** iOS 17+ / Swift 5.9+
- **UI:** SwiftUI
- **AI:** Gemini Swift SDK for Vision LLM image analysis
- **Networking:** URLSession for all HTTP requests
- **Data:** Local Codable models, static CSV for parts pricing

## Code Conventions

### Swift
- Use Swift 5.9+ with strict concurrency checking enabled
- Follow [Swift API Design Guidelines](https://www.swift.org/documentation/api-design-guidelines/)
- Use `Codable` for all data models
- Use `async/await` for all asynchronous operations
- Use `Decimal` (via Foundation) for all money values — never `Double` for currency
- Use SwiftUI for all views
- Store LLM prompts as `static let` string constants in dedicated files under `Prompts/`
- Configuration via `Config.plist` (never hardcode secrets)
- Group imports: Foundation → framework imports → local/project imports

### AI / Prompts
- Store all LLM prompts as constants in dedicated prompt files (e.g., `Prompts/DamageAssessmentPrompt.swift`)
- Always request structured JSON output from Vision LLMs
- Include the expected JSON schema in every prompt
- Log all LLM inputs/outputs for debugging (redact any PII)

### Data Models
- Severity scores are always `Double` in range `[0.0, 1.0]`
- Cost values are `Decimal` with 2 decimal places (never `Double` for money)
- Vehicle identification: `make`, `model`, `year` (Int), `trim` (optional String)
- All damage assessments reference a standard component list (see PROJECT_PLAN.md §3)

## Testing

- Use **XCTest** for all unit and integration tests
- Mock network calls using `URLProtocol` subclasses
- Test async code with `async` test methods (Swift concurrency)
- Test files mirror source structure: `CarCrashAI/Services/Foo.swift` → `CarCrashAITests/FooTests.swift`
- Minimum: test all service-layer functions and Codable model encoding/decoding

## File Structure Rules

- `CarCrashAI/App/` — App entry point and app-level configuration
- `CarCrashAI/Views/` — SwiftUI views only
- `CarCrashAI/Models/` — Codable data models
- `CarCrashAI/Services/` — Business logic (damage detection, cost estimation, API clients)
- `CarCrashAI/Prompts/` — LLM prompt string constants
- `CarCrashAI/Data/` — Static data files (CSV for parts pricing)
- `CarCrashAITests/` — All tests

## Security

- API keys stored in `Config.plist` (git-ignored) — never hardcode secrets
- Validate image data before sending to LLM (check size, format)
- Never log API keys or tokens
- Sanitize all user input before passing to LLM prompts

## Git Workflow

- **Always ask the user for approval before any git operation** (commit, push, merge, branch creation, etc.)
- **Branching model:** Git Flow with `develop` as the integration branch
  - All feature branches are created from `develop`
  - Branch naming: `feature/<short-description>` (e.g., `feature/image-capture`, `feature/vehicle-identification`)
  - Merge back into `develop` **only when the user confirms** the feature is complete and verified
  - Never merge directly into `main` — `main` is for production releases only
- **Commits:** Use conventional commit messages (e.g., `feat:`, `fix:`, `docs:`, `test:`)
- **Never use `git add -A` or `git add .`** — only stage files directly related to the current task

## Learning & Reference

- **`LEARNING.md`** — Comprehensive guide to all technologies, concepts, and patterns used in this project. Covers SwiftUI, Gemini Swift SDK, prompt engineering, image processing, async/await concurrency, testing with XCTest, and AI model selection with cost comparisons. **Read this file when onboarding or when you need to understand why a technology choice was made.**

## Key Decision Records

- **Severity threshold 0.3** — Damage > 0.3 recommends replacement; ≤ 0.3 recommends repair
- **Vision LLM first** — Use Gemini Vision for MVP to avoid training data requirements
- **Static price DB for MVP** — Real parts API integration deferred to Phase 2
- **Labor rate default** — $75/hr national average until regional rates are implemented
