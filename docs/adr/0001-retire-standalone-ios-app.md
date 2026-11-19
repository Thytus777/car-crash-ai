# 0001. Retire the standalone iOS app; make the web frontend the primary client

- **Status:** Accepted
- **Date:** 2026-11-19
- **Issue:** #5

## Context

`CarCrashAI/` was a SwiftUI app that re-implemented the whole assessment
pipeline on-device. It had its own prompts, pricing and JSON parsing, and it
called Gemini and OpenAI directly. In practice:

- API keys were read from a `Config.plist` bundled into the app. Anyone can
  extract them from a shipped build.
- It was a second copy of the pipeline (hardcoded `gemini-2.5-flash`) that the
  backend evals would never cover, so its quality could drift unnoticed.
- There was no `.xcodeproj` or `Package.swift` and no tests, so it could not
  be built or tested in CI.

Meanwhile `frontend-next/` already talks to the backend's `/upload`,
`/analyze` and `/estimates` endpoints, and a hosted web page is far easier for
a reviewer to try than an Xcode build.

## Decision

- Tag the last commit containing the app as `archive/ios-standalone` and
  remove `CarCrashAI/`, its setup guide (`docs/SETUP.md`) and the iOS-only
  agent skills from `main`.
- `frontend-next/` (Next.js) is the primary user-facing client.
- `frontend/streamlit_app.py` stays as an internal demo and the base for the
  eval labelling tool.

## Alternatives considered

- **Convert iOS into a thin backend client.** This removes the shipped keys,
  but it still needs an Xcode project, an SPM package, XCTest and a macOS CI
  runner, all for a client most reviewers can't run. It isn't worth the cost
  now.
- **Keep it standalone and add tests.** This keeps the key-in-bundle problem
  and the duplicated pipeline the evals can't cover.

## Consequences

- One pipeline, one schema, one place to evaluate. There are no LLM keys on
  client devices.
- The API contract is only checked against the TypeScript and Streamlit
  clients, so the brief's XCTest contract tests are dropped.
- A native app can come back later as a thin client of `/v1`. The archived
  tag holds the old SwiftUI views for reference.
