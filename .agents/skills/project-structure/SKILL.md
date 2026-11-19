---
name: project-structure
description: "Project directory structure and file placement rules for the Car Crash AI iOS app. Use when creating new files or deciding where code belongs."
---

# Project Structure for Car Crash AI

## Directory Layout

```
car-crash-ai/
├── CarCrashAI/                        # Main app source
│   ├── App/                           # App entry point & configuration
│   │   ├── CarCrashAIApp.swift        # @main entry point
│   │   └── Config.swift               # Config.plist reader
│   ├── Views/                         # SwiftUI views ONLY
│   │   ├── HomeView.swift             # Main screen (photo selection + analyze)
│   │   ├── CameraView.swift           # Camera/photo picker wrapper
│   │   ├── AnalysisView.swift         # Progress view during analysis
│   │   └── ReportView.swift           # Damage report display
│   ├── ViewModels/                    # View logic (if needed)
│   │   └── AnalysisViewModel.swift    # Orchestrates the analysis pipeline
│   ├── Models/                        # Codable data models ONLY
│   │   ├── Vehicle.swift              # Vehicle identification model
│   │   ├── DamageItem.swift           # Per-component damage model
│   │   ├── CostEstimate.swift         # Cost estimate model
│   │   └── AssessmentReport.swift     # Full report model
│   ├── Services/                      # Business logic & API calls
│   │   ├── AIService.swift            # LLM abstraction (Gemini + OpenAI)
│   │   ├── VehicleIDService.swift     # Vehicle identification
│   │   ├── DamageDetectService.swift  # Damage detection
│   │   ├── CostEstimateService.swift  # Cost estimation orchestrator
│   │   ├── PriceSearchService.swift   # SerpAPI + price extraction
│   │   └── ImageProcessor.swift       # Image resize/compress/validate
│   ├── Prompts/                       # LLM prompt string constants
│   │   ├── VehicleIdentification.swift
│   │   └── DamageAssessment.swift
│   ├── Data/                          # Static bundled data
│   │   └── parts_prices.csv           # Fallback parts pricing
│   └── Resources/                     # App resources
│       └── Config.plist               # API keys (git-ignored)
├── CarCrashAITests/                   # XCTest suite
│   ├── ModelTests.swift
│   ├── AIServiceTests.swift
│   ├── VehicleIDTests.swift
│   ├── DamageDetectTests.swift
│   ├── CostEstimateTests.swift
│   └── ImageProcessorTests.swift
├── .agents/                           # Amp agent configuration
│   ├── AGENTS.md
│   └── skills/
└── Docs/                              # Project documentation
    ├── PROJECT_PLAN.md
    ├── TECHSTACK.md
    ├── LEARNING.md
    ├── SETUP.md
    └── README.md
```

## File Placement Rules

- **Views/** — SwiftUI View structs ONLY. No business logic, no API calls. Views call ViewModels or Services.
- **ViewModels/** — @Observable classes that orchestrate business logic for views. Optional — simple views can call Services directly.
- **Models/** — Codable structs only. No methods with side effects. Can have computed properties.
- **Services/** — Static methods or singletons. All API calls, data processing, business logic. Never import SwiftUI.
- **Prompts/** — String constants only. No logic. Enums with static let properties.
- **Data/** — Static files bundled with the app. Read-only at runtime.
- **Resources/** — Config files, assets. Config.plist is git-ignored.

## Rules

- One primary type per file
- File name matches the primary type name
- Tests mirror source: `Services/AIService.swift` → `AIServiceTests.swift`
- Never put API keys in source files — always read from Config.plist
