---
name: building-swift
description: "Swift/SwiftUI code conventions, patterns, and best practices for the Car Crash AI iOS app. Use when writing or reviewing Swift code."
---

# Building Swift — Car Crash AI iOS App

## Swift Conventions

- Target **Swift 5.9+** and **iOS 17+** minimum deployment.
- Enable **strict concurrency** checking (`SWIFT_STRICT_CONCURRENCY = complete`).
- Follow the [Swift API Design Guidelines](https://www.swift.org/documentation/api-design-guidelines/).
- Prefer value types (`struct`, `enum`) over reference types (`class`) unless identity semantics are required.
- Use `let` over `var` wherever possible.

## Naming Conventions

| Element               | Convention                          | Example                     |
|-----------------------|-------------------------------------|-----------------------------|
| Types (struct/class)  | PascalCase                          | `DamageReport`              |
| Protocols             | PascalCase (adjective or `-able`)   | `Identifiable`, `Parseable` |
| Properties / Methods  | camelCase                           | `estimatedCost`             |
| Constants             | camelCase                           | `maxRetryCount`             |
| Enums                 | PascalCase type, camelCase cases    | `Severity.moderate`         |
| Type aliases          | PascalCase                          | `ImageData`                 |

## File Organization

- **One primary type per file.** File name matches the type name (e.g., `DamageReport.swift`).
- Group imports in order: Foundation → Apple frameworks → third-party → local modules.
- Use `// MARK: -` comments to separate logical sections:

```swift
import Foundation
import SwiftUI
import GoogleGenerativeAI

// MARK: - DamageReport

struct DamageReport {
    // MARK: - Properties
    // MARK: - Computed Properties
    // MARK: - Methods
}

// MARK: - DamageReport + Codable

extension DamageReport: Codable { }
```

## SwiftUI Patterns

- Use `@State` for view-local state, `@Binding` for parent-owned state.
- Use `@Observable` (Observation framework) for shared/model state — **not** `ObservableObject`/`@Published`.
- Keep `body` short and readable — extract complex subviews into private computed properties or child views.
- Prefer `.task { }` modifier over `onAppear` for async work.

```swift
struct ReportView: View {
    @State private var isLoading = false
    @Bindable var viewModel: ReportViewModel

    var body: some View {
        content
            .task { await viewModel.load() }
    }

    private var content: some View {
        // ...
    }
}
```

## Error Handling

- Define **custom error enums** conforming to `Error` (and `LocalizedError` when user-facing).
- **Never force-unwrap** (`!`) in production code. Use `guard let`, `if let`, or `nil` coalescing.
- Propagate errors with `throws` / `try`; catch at the appropriate boundary.

```swift
enum AnalysisError: Error, LocalizedError {
    case invalidImage
    case networkUnavailable
    case apiFailure(statusCode: Int)

    var errorDescription: String? {
        switch self {
        case .invalidImage: "The selected image could not be processed."
        case .networkUnavailable: "No network connection available."
        case .apiFailure(let code): "API request failed (status \(code))."
        }
    }
}
```

## Data Models

- Use `Codable` structs for all API/persistence models.
- Provide `CodingKeys` when the API uses `snake_case` and Swift uses `camelCase`.
- Use `Decimal` for monetary values (cost estimates, part prices).
- Use `Double` for severity scores and confidence percentages.

```swift
struct RepairEstimate: Codable {
    let partName: String
    let unitCost: Decimal
    let severityScore: Double

    enum CodingKeys: String, CodingKey {
        case partName = "part_name"
        case unitCost = "unit_cost"
        case severityScore = "severity_score"
    }
}
```

## Async Patterns

- **Always** use `async/await` — never use completion handlers or Combine for new code.
- Never block the main thread with synchronous network or file I/O.
- Bridge SwiftUI into async contexts with `Task`:

```swift
Button("Analyze") {
    Task {
        await viewModel.analyzeImage(selectedImage)
    }
}
```

- Use `@MainActor` for view models and any code that updates UI state.
- Use `TaskGroup` for concurrent independent operations (e.g., analyzing multiple images).

## Dependencies

- **GoogleGenerativeAI** — added via Swift Package Manager. Used for Gemini vision/text model calls.
- **No other external dependencies.** Use Foundation, UIKit, and SwiftUI for everything else.
- If a new dependency is truly needed, discuss with the team before adding it.
