---
name: frontend-ui
description: "SwiftUI view patterns, navigation, and UI components for the Car Crash AI iOS app. Use when building or modifying views."
---

# Frontend UI

SwiftUI view development patterns and conventions for the Car Crash AI iOS app.

## View Architecture

The app has 4 main views:

- **HomeView** — Photo selection grid with an analyze button to start AI processing
- **CameraView** — Camera capture and photo picker interface
- **AnalysisView** — Progress indicators displayed during AI analysis calls
- **ReportView** — Final results display with vehicle info, damage, and cost breakdown

## Navigation

- Use `NavigationStack` at the app root
- Use `NavigationLink` for screen-to-screen transitions
- Use `.sheet()` for modals (camera/photo picker)
- Use `.alert()` for error presentation

## State Management

- `@State` for local view state (toggles, text fields, selection)
- `@Binding` for passing state to child views
- `@Observable` for shared state across views (`AnalysisViewModel`)
- `@Environment` for dependency injection (services, formatters)

## Loading States

Display `ProgressView` with descriptive labels during each AI processing stage:

- `"Identifying vehicle..."`
- `"Detecting damage..."`
- `"Estimating costs..."`

Disable all action buttons while analysis is in progress.

## Report Display

Use `List` with sections for structured output:

- **Vehicle Info** — Make, model, year, color
- **Damage Assessment** — Detected damage items with severity indicators
- **Cost Breakdown** — Parts, labor, and total estimates

### Severity Bars

Use `ProgressView` for severity visualization with color coding:

| Severity Range | Color  |
|----------------|--------|
| < 0.3          | Green  |
| 0.3 – 0.6     | Yellow |
| 0.6 – 0.8     | Orange |
| > 0.8          | Red    |

### Currency Formatting

Use `NumberFormatter` with `.currency` style for all cost values.

## Photo Grid

- Use `LazyVGrid` to display selected photos
- Support swipe-to-delete for removing individual photos
- Include an "Add More" button to append additional photos

## Error Handling

- Present errors with the `.alert()` modifier
- Map `AIServiceError` cases to user-friendly messages before display
- Never show raw error descriptions to the user

## Accessibility

- Add VoiceOver labels (`.accessibilityLabel()`) on all interactive elements
- Support Dynamic Type for all text
- Ensure sufficient color contrast ratios (WCAG AA minimum)
