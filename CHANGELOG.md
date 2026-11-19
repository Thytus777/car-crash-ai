# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Eval harness: `make eval` runs the production pipeline over the labelled dataset and writes `evals/results/*.json|md`. It reports component P/R/F1 (per component and per tag), severity accuracy, triage and vehicle accuracy, cost MAE and within-range rate, schema-valid-first-attempt, retry and failure rates, p50/p95 latency and cost per request. Model replies are cached for free replays, and `make eval-compare` gates regressions ([#15](https://github.com/Thytus777/car-crash-ai/issues/15)).
- Eval dataset format: a fixed taxonomy, a strict label schema with consistency rules, a labelling guide, a versioned manifest with a smoke subset, and `make eval-validate` (run in CI) checking hashes, image sizes, licences and smoke eligibility ([#15](https://github.com/Thytus777/car-crash-ai/issues/15)).
- A committed OpenAPI contract (`backend/openapi.json`). CI fails if it's stale or changed without an API version bump, and tests check that both clients only call paths in the spec. The API version is now 0.2.0 ([#26](https://github.com/Thytus777/car-crash-ai/issues/26)).
- Input validation: per-file, total and count limits (413), format detected from the file bytes (415, JPEG/PNG/WebP), and an image-triage step that rejects non-vehicle or unusable photos with a reason (422). Prompt v3 adds the triage prompt ([#27](https://github.com/Thytus777/car-crash-ai/issues/27)).
- Makefile entry point; CI runs the same targets.
- uv-managed dependencies with a committed `uv.lock` and Python 3.12 pin.
- ruff (lint + format), mypy `--strict`, pre-commit hooks (gitleaks, Conventional Commits).
- CI jobs: lint, typecheck, unit + integration tests with a coverage gate, Docker build.
- Contributor docs: `AGENTS.md`, `CONTRIBUTING.md`, `SECURITY.md`, PR and issue templates, CODEOWNERS.
- Architecture decision records in `docs/adr/`.

### Changed
- Damaged parts are priced concurrently (bounded by `PRICING_CONCURRENCY`). Each part's page fetches and price extractions also run concurrently, and live search has a deadline (`PRICE_SEARCH_DEADLINE_S`) after which it falls back to static or AI pricing ([#7](https://github.com/Thytus777/car-crash-ai/issues/7)).
- Prompts live in versioned, immutable template files (`backend/prompts/<version>/`). Every analysis response records `meta.prompt_version`, the models used and token counts ([#25](https://github.com/Thytus777/car-crash-ai/issues/25), [ADR 0002](docs/adr/0002-versioned-prompt-files.md)).
- LLM calls use native structured output (Gemini `response_json_schema`, OpenAI `chat.completions.parse`) with Pydantic schemas, per-attempt timeouts, jittered exponential backoff, bounded re-asks on invalid output, and provider fallback ([#6](https://github.com/Thytus777/car-crash-ai/issues/6)).
- Error responses are RFC 9457 `application/problem+json` ([#24](https://github.com/Thytus777/car-crash-ai/issues/24)).
- Trunk-based workflow on `main`; the `develop` branch is retired.
- Tests split into `tests/unit` and `tests/integration` with pytest markers.

### Removed
- Standalone iOS app ([ADR 0001](docs/adr/0001-retire-standalone-ios-app.md)); archived in tag `archive/ios-standalone`.
- Unused dependencies `beautifulsoup4` and `google-search-results`.

### Fixed
- The Streamlit demo called three endpoints removed in an earlier refactor. It now uses `/upload` then `/analyze` and shows the confirmation step, partial-result issues, unpriced parts and the problem `detail` on errors ([#4](https://github.com/Thytus777/car-crash-ai/issues/4)).
- The vehicle-ID prompt was sent unformatted, so the model saw its JSON example with doubled braces. Prompt v2 fixes it ([#25](https://github.com/Thytus777/car-crash-ai/issues/25)).
- Failed LLM stages were reported as success: a failed damage zone read as "no damage", a failed price estimate became a made-up $150/$300/$500, and a failed sanity check read as "no concerns". Reports now carry `status` (`complete`/`partial`) and `issues`. Unpriced parts have null costs and are listed in `totals.unpriced_components`, and if every zone fails the request returns 503 ([#3](https://github.com/Thytus777/car-crash-ai/issues/3)).
- `/analyze` returned 500 whenever saving the estimate failed, and saving always failed on a missing foreign-key parent ([#1](https://github.com/Thytus777/car-crash-ai/issues/1)).
- Path traversal through `upload_id` ([#2](https://github.com/Thytus777/car-crash-ai/issues/2)).
- Unexpected errors no longer leak exception text in responses.

### Security
- API keys and the database URL are `SecretStr`, so they render as `**********` in reprs, tracebacks and logs. Placeholder values from `.env.example` count as unset, instead of triggering doomed OpenAI fallbacks and SerpAPI calls ([#34](https://github.com/Thytus777/car-crash-ai/issues/34)).
- `backend/.dockerignore` keeps `.env` files and local virtualenvs out of Docker images.

## [0.1.0]

Initial prototype: FastAPI backend with vision-LLM vehicle identification, zone-based damage detection, live/static/AI part pricing, PostgreSQL persistence, PDF reports, Streamlit and Next.js frontends.
