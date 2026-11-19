# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Cheap-first routing for damage zones, behind `ROUTING_ENABLED` (off): fast model first, escalating to the strong model on failure, near-threshold severity, or (optionally) an empty zone. Decisions are counted in `damage_routing_total`. Proposed in [ADR 0003](docs/adr/0003-cheap-first-model-routing.md), pending eval evidence ([#51](https://github.com/Thytus777/car-crash-ai/issues/51)).
- Result cache: a new upload of identical photos with the same prompt version, models and options returns the stored complete report with no model calls (`meta.cached`, `result_cache_total`). Entries expire after `RESULT_CACHE_TTL_HOURS` (24), and partial reports are never cached. API 0.5.0 ([#49](https://github.com/Thytus777/car-crash-ai/issues/49)).
- Load test (`make loadtest`): Locust against the real app with simulated model latency, writing p50/p95/p99 and throughput, together with the settings and machine, to `backend/loadtest/results/` ([#48](https://github.com/Thytus777/car-crash-ai/issues/48)).
- Cost and latency budgets: model prices live in `backend/app/data/model_pricing.yaml` (shared with the evals). Every model call carries `cost_usd` on its span and in `llm_cost_usd_total`, and every response's `meta` has `cost_usd`, `latency_s` and `budget_exceeded`. Requests over `REQUEST_COST_BUDGET_USD` or `REQUEST_LATENCY_BUDGET_S` are logged and counted in `budget_exceeded_total`, not rejected. API 0.4.0.
- Prometheus metrics at `/metrics`: HTTP requests and latency by route template, assessments by result, and model calls by outcome and cache status, with token and latency series. Initial SLOs with PromQL and burn-rate alerts are in `docs/SLO.md` ([#16](https://github.com/Thytus777/car-crash-ai/issues/16)).
- OpenTelemetry tracing: one trace per request, with spans for every pipeline stage, each damage zone and each priced part. Every model call is a span carrying `gen_ai.*` model and token attributes plus attempts, re-asks, cache status, latency and prompt version. Log lines carry `trace_id`/`span_id`, and docker-compose ships a collector and Jaeger (UI on :16686) ([#16](https://github.com/Thytus777/car-crash-ai/issues/16)).
- Observability: JSON logs (one object per line), a request ID taken from or generated for `X-Request-ID` that appears in every log line, the response header and problem bodies, a per-request access log with duration, and `/healthz` (liveness) plus `/readyz` (readiness with per-check detail). API 0.3.0; `/health` is kept as a deprecated alias ([#16](https://github.com/Thytus777/car-crash-ai/issues/16)).
- Labelling tool (`make label`): a Streamlit page that EXIF-rotates, resizes (≤1600 px, <1 MB) and blurs detected faces and plates plus manual boxes, writes a schema-validated `label.json`, and stores images in git or `evals/local_images/` according to licence ([#15](https://github.com/Thytus777/car-crash-ai/issues/15)).
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
- Uploads are stored at up to 1600 px (`STORED_IMAGE_MAX_EDGE`) and downscaled for the models to `MODEL_IMAGE_MAX_EDGE` (1024) at `MODEL_IMAGE_JPEG_QUALITY` (90), so eval sweeps can change model input without re-uploading. Model input is unchanged by default ([#50](https://github.com/Thytus777/car-crash-ai/issues/50)).
- Damaged parts are priced concurrently (bounded by `PRICING_CONCURRENCY`). Each part's page fetches and price extractions also run concurrently, and live search has a deadline (`PRICE_SEARCH_DEADLINE_S`) after which it falls back to static or AI pricing ([#7](https://github.com/Thytus777/car-crash-ai/issues/7)).
- Prompts live in versioned, immutable template files (`backend/prompts/<version>/`). Every analysis response records `meta.prompt_version`, the models used and token counts ([#25](https://github.com/Thytus777/car-crash-ai/issues/25), [ADR 0002](docs/adr/0002-versioned-prompt-files.md)).
- LLM calls use native structured output (Gemini `response_json_schema`, OpenAI `chat.completions.parse`) with Pydantic schemas, per-attempt timeouts, jittered exponential backoff, bounded re-asks on invalid output, and provider fallback ([#6](https://github.com/Thytus777/car-crash-ai/issues/6)).
- Error responses are RFC 9457 `application/problem+json` ([#24](https://github.com/Thytus777/car-crash-ai/issues/24)).
- Trunk-based workflow on `main`; the `develop` branch is retired.
- Tests split into `tests/unit` and `tests/integration` with pytest markers.

### Removed
- The unused `PRICE_CACHE_TTL_HOURS` setting.
- Standalone iOS app ([ADR 0001](docs/adr/0001-retire-standalone-ios-app.md)); archived in tag `archive/ios-standalone`.
- Unused dependencies `beautifulsoup4` and `google-search-results`.

### Fixed
- The Next.js "Download PDF" links pointed at the Next.js server instead of the API, so they always returned 404. Downloads now fetch from the API, with the key if one is set.
- The Streamlit demo called three endpoints removed in an earlier refactor. It now uses `/upload` then `/analyze` and shows the confirmation step, partial-result issues, unpriced parts and the problem `detail` on errors ([#4](https://github.com/Thytus777/car-crash-ai/issues/4)).
- The vehicle-ID prompt was sent unformatted, so the model saw its JSON example with doubled braces. Prompt v2 fixes it ([#25](https://github.com/Thytus777/car-crash-ai/issues/25)).
- Failed LLM stages were reported as success: a failed damage zone read as "no damage", a failed price estimate became a made-up $150/$300/$500, and a failed sanity check read as "no concerns". Reports now carry `status` (`complete`/`partial`) and `issues`. Unpriced parts have null costs and are listed in `totals.unpriced_components`, and if every zone fails the request returns 503 ([#3](https://github.com/Thytus777/car-crash-ai/issues/3)).
- `/analyze` returned 500 whenever saving the estimate failed, and saving always failed on a missing foreign-key parent ([#1](https://github.com/Thytus777/car-crash-ai/issues/1)).
- Path traversal through `upload_id` ([#2](https://github.com/Thytus777/car-crash-ai/issues/2)).
- Unexpected errors no longer leak exception text in responses.

### Security
- Supply chain: a required `security` CI job runs pip-audit (locked runtime deps, `--strict`), bandit and gitleaks over the full history. CodeQL (security-extended) covers Python and TypeScript on PRs and weekly. Dependabot sends grouped weekly updates for uv, npm, GitHub Actions and Docker.
- API-key auth (`API_KEYS`; `X-API-Key` or Bearer) on `/api/v1/*` and `/metrics`. Per-client token-bucket rate limits, with a tighter one for `/analyze` (429 `rate-limited` with `Retry-After`). CORS no longer combines `*` with credentials; the defaults are the local dev origins. `APP_ENV=production` refuses to start without keys, with wildcard CORS, or without required redaction. API 0.7.0 ([#9](https://github.com/Thytus777/car-crash-ai/issues/9)).
- Untrusted input hardening ([#8](https://github.com/Thytus777/car-crash-ai/issues/8)):
  - Prompt v4 fences scraped page text in `<page>` tags declared as untrusted, and page text can't close the fence.
  - The vision prompts state that text in photos is never an instruction.
  - Extracted prices outside `MIN_PART_PRICE`–`MAX_PART_PRICE`, or with a malformed currency, are discarded.
  - Price pages are fetched only over https from public addresses: every resolved IP is checked and every redirect hop re-checked, blocking loopback, private, link-local and metadata IPs. Bodies are capped at 2 MB.
- Faces and number plates are blurred at upload, before storage or any model call, using pretrained ONNX detectors: a YOLOv9 plate model and OpenCV YuNet for faces. Both are sha256-pinned and fetched at build time. With `REDACTION_REQUIRED` (the Docker default), uploads are refused and readiness fails if the models are missing. Redacted photos are deleted after 24 h; see `docs/DATA_RETENTION.md` and [ADR 0004](docs/adr/0004-redact-faces-and-plates-at-upload.md) ([#10](https://github.com/Thytus777/car-crash-ai/issues/10)).
- Uploaded photos are EXIF-rotated before processing.
- API keys and the database URL are `SecretStr`, so they render as `**********` in reprs, tracebacks and logs. Placeholder values from `.env.example` count as unset, instead of triggering doomed OpenAI fallbacks and SerpAPI calls ([#34](https://github.com/Thytus777/car-crash-ai/issues/34)).
- `backend/.dockerignore` keeps `.env` files and local virtualenvs out of Docker images.

## [0.1.0]

Initial prototype: FastAPI backend with vision-LLM vehicle identification, zone-based damage detection, live/static/AI part pricing, PostgreSQL persistence, PDF reports, Streamlit and Next.js frontends.
