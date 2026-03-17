# Setup Guide — iOS Native App

Setup steps for the Car Crash AI iOS application. Development happens in two phases: **writing Swift files on Windows**, then **building and running in Xcode on Mac**.

---

## 1. Prerequisites (One-Time Setup)

### macOS & Xcode

- **macOS 14 (Sonoma)** or later
- **Xcode 15+** — install from the [Mac App Store](https://apps.apple.com/app/xcode/id497799835)
- After installing, open Xcode once and accept the license agreement
- Install command-line tools if prompted:
  ```bash
  xcode-select --install
  ```

### Apple Developer Account

- A free Apple ID is sufficient for running on a physical device during development
- Sign in at **Xcode → Settings → Accounts → Add Apple ID**
- A paid Apple Developer Program membership ($99/year) is only required for App Store distribution

### iOS Device

- **iOS 17+** device for on-device testing
- Enable **Developer Mode** on your device:
  **Settings → Privacy & Security → Developer Mode → On** (restart required)

### API Keys

| Key | Required | Where to get it |
|-----|----------|-----------------|
| `GEMINI_API_KEY` | ✅ Yes | Free at [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| `OPENAI_API_KEY` | ❌ Optional | Fallback provider — [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `SERPAPI_KEY` | ❌ Optional | Live part pricing — [serpapi.com](https://serpapi.com) |

---

## 2. Clone & Open in Xcode

```bash
# Clone the repository
git clone https://github.com/thytus777/car-crash-ai.git
cd car-crash-ai
```

On your Mac, open the Xcode project:

```bash
open CarCrashAI.xcodeproj
```

Or from Xcode: **File → Open → navigate to the cloned folder → select `CarCrashAI.xcodeproj`**

> **Windows workflow:** Edit Swift files on Windows using your editor of choice, commit and push, then pull on Mac to build in Xcode.

---

## 3. Configure API Keys

API keys are stored in a `Config.plist` file at the project root. This file is **git-ignored** — each developer creates their own.

### Create `Config.plist`

Create a file named `Config.plist` in the Xcode project root with the following contents:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>GEMINI_API_KEY</key>
    <string>your-gemini-key-here</string>
    <key>OPENAI_API_KEY</key>
    <string></string>
    <key>SERPAPI_KEY</key>
    <string></string>
    <key>AI_PROVIDER</key>
    <string>gemini</string>
    <key>LABOR_RATE_PER_HOUR</key>
    <real>75.0</real>
</dict>
</plist>
```

### Add `Config.plist` to the Xcode project

1. In Xcode, right-click the project navigator → **Add Files to "CarCrashAI"**
2. Select `Config.plist`
3. Ensure **"Copy items if needed"** is unchecked (the file is already in the project folder)
4. Confirm it appears in the project navigator

### Verify it's git-ignored

`Config.plist` should already be listed in `.gitignore`. Confirm with:

```bash
git check-ignore Config.plist
# Should output: Config.plist
```

---

## 4. Add Swift Package Dependencies

The project uses **Swift Package Manager (SPM)** for dependency management.

### GoogleGenerativeAI SDK

The primary AI dependency is the [google-generative-ai-swift](https://github.com/google-gemini/generative-ai-swift) SDK.

To add it in Xcode:

1. **File → Add Package Dependencies...**
2. Enter the repository URL:
   ```
   https://github.com/google-gemini/generative-ai-swift
   ```
3. Set the dependency rule to **Up to Next Major Version**
4. Click **Add Package**
5. In the "Choose Package Products" dialog, ensure **GoogleGenerativeAI** is checked and added to the `CarCrashAI` target
6. Click **Add Package**

The package will appear under **Package Dependencies** in the project navigator.

### Verify the import

In any Swift file, confirm the import resolves without errors:

```swift
import GoogleGenerativeAI
```

Build with **⌘B** to verify.

---

## 5. Build & Run

### Simulator

1. Select a simulator target from the scheme toolbar (e.g., **iPhone 15 Pro**)
2. Press **⌘R** or click the ▶️ button
3. The app should build and launch in the iOS Simulator

### Physical Device

1. Connect your iOS device via USB (or pair wirelessly via **Window → Devices and Simulators**)
2. Select your device from the scheme toolbar
3. On first run, Xcode may prompt you to:
   - Trust the developer certificate on the device: **Settings → General → VPN & Device Management → Trust**
   - Set a development team: **Project → Signing & Capabilities → Team → select your Apple ID**
4. Press **⌘R** to build and run on-device

### Common build issues

| Issue | Fix |
|-------|-----|
| "No such module 'GoogleGenerativeAI'" | Re-add the SPM package (step 4) and clean build folder (**⇧⌘K**) |
| Signing errors | Set a valid team in **Signing & Capabilities** |
| "Untrusted Developer" on device | Trust the profile in device Settings |
| Minimum deployment target error | Set **iOS 17.0** in project settings → General → Minimum Deployments |

---

## Per-Feature Setup

> Each feature section below is added when the feature is developed.
> Check this file after pulling new feature branches.

### Feature: Project Scaffolding (`feature/project-scaffolding`)

**Branch:** `feature/project-scaffolding`

**Setup steps:**

1. Open `CarCrashAI.xcodeproj` in Xcode
2. Add the `GoogleGenerativeAI` SPM package (see [step 4](#4-add-swift-package-dependencies))
3. Create your `Config.plist` with API keys (see [step 3](#3-configure-api-keys))
4. Build and run on simulator: **⌘R**

**What was created:**
- Xcode project with SwiftUI app entry point
- Config loader that reads `Config.plist` at runtime
- Service protocol stubs: `ImageProcessingService`, `VehicleIDService`, `DamageDetectionService`, `CostEstimationService`
- Data models: `Vehicle`, `DamageItem`, `DamageAssessment`, `PriceResult`, `CostEstimate`, `AssessmentReport`
- LLM prompt templates: vehicle identification, damage assessment, price extraction
- Unit test target with sample tests

### Feature: Camera & Photo Upload (`feature/camera-upload`)

**Setup steps:**

1. Pull the branch and open in Xcode
2. **Camera permission:** The `Info.plist` entry `NSCameraUsageDescription` is already set. No manual action needed.
3. **Photo Library permission:** The `Info.plist` entry `NSPhotoLibraryUsageDescription` is already set.
4. Build and run on a **physical device** to test camera capture (simulator only supports photo library)

**What was created:**
- `PhotoPicker` view using `PhotosUI` framework
- Camera capture view using `AVFoundation`
- Image preprocessing (resize, orientation fix) before sending to AI

### Feature: AI Damage Analysis (`feature/ai-analysis`)

**Setup steps:**

1. Ensure `GEMINI_API_KEY` is set in `Config.plist`
2. Pull the branch, resolve any SPM packages (**File → Packages → Resolve Package Versions**)
3. Build and run

**⚠️ Manual setup required:**
- A valid `GEMINI_API_KEY` must be present in `Config.plist` for AI analysis to work
- Set `AI_PROVIDER` to `openai` and provide `OPENAI_API_KEY` if you want to use OpenAI as a fallback

**What was created:**
- `GeminiService` wrapping the GoogleGenerativeAI SDK
- Vision model integration for image-based damage detection
- Structured JSON parsing of AI responses into Swift models
- Error handling with user-facing alerts

### Feature: Cost Estimation (`feature/cost-estimation`)

**Setup steps:**

1. Pull the branch and build
2. Optionally set `SERPAPI_KEY` in `Config.plist` for live part pricing
3. Without `SERPAPI_KEY`, the app falls back to the bundled static price database

**What was created:**
- Cost calculation engine with parts + labor breakdown
- Bundled CSV price database as an app resource
- Optional live price search via SerpAPI
- Formatted cost report view with severity indicators
