# AGENTS.md

Car Crash AI: crash photos go in, a vision LLM identifies damaged components, and the backend returns a structured repair-cost estimate as validated JSON.

## Layout

- `backend/`: FastAPI service, the only place model calls happen. A uv project (`pyproject.toml`, `uv.lock`).
  - `app/api/routes/`: HTTP layer
  - `app/services/`: pipeline stages
  - `app/core/llm.py`: provider abstraction
  - `app/prompts/`: prompt registry; the text lives in `backend/prompts/<version>/*.md`
  - `app/models/`: Pydantic schemas
  - `app/db/`: SQLAlchemy + Alembic
- `frontend-next/`: Next.js app, the primary client.
- `frontend/`: Streamlit demo (`streamlit_app.py`) on top of `api_client.py`, which holds the HTTP calls with no Streamlit dependency. Tests drive `api_client` against the real app through `TestClient`, so the demo can't drift from the API.
- `evals/`: dataset, taxonomy and results; the harness code is in `backend/evals/`.
- `docs/adr/`: architecture decision records. Read the relevant one before reversing a decision, and add one (copy `0000-template.md`) for any decision a reviewer would ask "why?" about.
- The standalone iOS app was retired (ADR 0001). The code is in tag `archive/ios-standalone`.

## Request flow

`POST /api/v1/upload` validates, resizes and stores the images, then returns an `upload_id`. `POST /api/v1/analyze` then runs five stages:

0. **Image triage:** one low-detail call checks that the photos show a usable vehicle; otherwise it returns a 422 with the reason. If triage itself fails, the request continues with an issue.
1. **Vehicle ID:** request override, then VIN (NHTSA), then vision LLM. If confidence is below 0.7 it returns `vehicle_confirmation_needed`.
2. **Damage detection:** three zone prompts run in parallel (front, rear, side), or two-provider consensus.
3. **Pricing per component:** live search (SerpAPI, then fetched pages, then LLM extraction), then the static CSV, then an LLM estimate.
4. **Totals, an LLM sanity check, then persistence.**

All LLM traffic goes through `app/core/llm.py`.

## Commands

`make help` lists every target. Run them from the repo root; CI calls the same targets. Day to day:

- `make setup`: install deps and the git hooks (pre-commit plus commit-msg).
- `make test`: unit suite, the inner loop.
- `make coverage`: unit + integration with the CI coverage gate.
- `make lint typecheck`: ruff, then mypy `--strict`.
- `make security`: pip-audit on the locked runtime deps, plus bandit. CI also runs gitleaks and CodeQL.

Gotchas:
- Dependencies change only through `uv add` / `uv lock` in `backend/`. CI fails if `uv.lock` disagrees with `pyproject.toml`.
- On Windows, `make` comes from `winget install ezwinports.make`.
- `tests/integration/test_analysis.py::test_analyze_with_vehicle_override` is a strict xfail tied to #1. Remove the marker in the PR that fixes #1.

## Conventions

- **Schemas:** Pydantic v2 models for every request, response and LLM output. Money is `Decimal` with 2 places. Severity is a float in `[0, 1]`. Component names come from `STANDARD_COMPONENTS` in `app/models/damage.py`.
- **Types:** the backend passes mypy `--strict` with no per-module exceptions.
- **Prompts:** get prompt text through `render(name, **values)` from `app/prompts`. Versions are immutable (ADR 0002): to change a prompt, copy `backend/prompts/<current>/` to the next version, edit it there, bump `prompt_version`, and add the expected diff to `tests/unit/test_prompts.py`. Every response records `meta.prompt_version`.
- **Untrusted text:** anything not written by us (web pages, OCR-able text in photos) goes into prompts only inside a declared fence (see `prompts/v4/price_extraction.md` and `fence_untrusted()`), and the model's output is bounds-checked in code. Outbound HTTP to URLs we didn't choose must go through `is_public_https()`.
- **Model calls:** every call goes through `generate(schema, prompt, images, task=...)` in `app/core/llm.py`. Its output schema is a Pydantic model in `app/models/llm_outputs.py`; that model is both the provider's structured-output schema and the validator, so a new call means a new model there, not hand parsing. Retries, timeouts and fallback live only in `llm.py`; callers handle the typed `LLM*Error`s. Wrap work in `record_llm_calls()` to collect per-call tokens and attempts.
- **Failures:** a stage that degrades reports it rather than guessing. Services catch only `AppError`s, typed LLM errors included: a failed zone goes in `DamageAssessment.failed_zones`, a part with no price gets `pricing_method="unpriced"` with null costs, and a failed sanity check returns `None`. The route turns these into `AssessmentReport.issues` with `status="partial"`. When nothing usable is left, e.g. every zone failed, the error propagates and becomes a 5xx problem. Never substitute a default value for a failed model call.
- **Logging:** use `logging.getLogger(__name__)` and pass structured fields with `extra={...}`. Lines are JSON and carry the request ID automatically. Never log images, prompts, raw model output or secrets.
- **Tracing:** wrap a new pipeline stage with `@traced("stage.<name>")` from `app/core/tracing.py`. Model calls are traced inside `llm.py`. Spans export only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set; `docker compose up` sends them to the collector and Jaeger at http://localhost:16686.
- **Metrics:** define new series in `app/core/metrics.py` with low-cardinality labels only (route templates, provider, model, task, fixed outcome sets; never IDs or raw paths). SLO queries in `docs/SLO.md` depend on the existing names.
- **Privacy:** images are redacted inside `process_upload()` before anything is stored or sent. A new code path that takes images must go through it. `docs/DATA_RETENTION.md` is the source of truth for what's stored and for how long; update it when that changes. Tests use a no-op redactor unless marked `real_redaction`; the real-model tests skip if `make models` hasn't been run.
- **Secrets:** they come from the environment only (`backend/.env` locally, CI secrets in Actions). `.env.example` files hold the variable names.

## Testing

- `tests/unit/` (auto-marked `unit`): pure logic, no network, no DB, no real LLM. The whole suite stays under 30 s. Mock LLM and HTTP clients at the boundary, i.e. `app.core.llm` functions and `httpx`.
- `tests/integration/` (auto-marked `integration`): the FastAPI app through `httpx.AsyncClient` with fixture LLM responses.
- Every bug fix lands with a regression test that goes **red** before the fix and green after.
- Fake the LLM with `tests/llm_fakes.py`: `ScriptedClient` replays replies and errors for policy tests, and `llm_result()` wraps an output for patched `generate` calls. The SDKs send over `httpx2`, which respx can't intercept, so mock at the `ProviderClient` seam.
- The coverage floor is `COV_MIN` in the `Makefile`. It only moves up. The target is 80% (#14).
- Evals: the labelled dataset lives in `evals/dataset/` (format: `backend/evals/schema.py`, guide: `evals/LABELLING.md`). Labels come only from a person. Never write or edit `label.json` content yourself, and never invent cases; test the harness with synthetic fixtures in `tmp_path`. `make eval-validate` checks the dataset. `make eval` / `make eval-smoke` run the real pipeline over it (cached replies in `evals/.cache/`), and `make eval-compare` gates regressions against `evals/thresholds.yaml`. CI runs `make eval-gate` on PRs (smoke subset vs the committed `evals/baselines/smoke.json`, result posted as a PR comment) and the full eval nightly. Never commit a baseline you didn't get from a real run's artifact. `evals/README.md` defines every metric. Model prices in `backend/app/data/model_pricing.yaml` come only from the providers' pricing pages.

## Git workflow

Trunk-based: `main` is always deployable and every change arrives by PR. The full process is in `CONTRIBUTING.md`. In short:

- One short-lived branch per logical change, named `<type>/<short-description>`, branched from the latest `main`.
- Conventional Commits, enforced by the commit-msg hook. Write commit subjects in the imperative, ≤ 72 chars. Use the body to explain why. Keep commits small and atomic, with refactors separate from behaviour changes.
- Fill in the PR template. Link the issue (`Closes #N`). Squash-merge once CI is green, then delete the branch.
- Commits and PRs carry the author's name only; add no AI co-author or "generated with" lines.

API contract: `backend/openapi.json` is generated (`make openapi`) and committed. CI fails if it's stale, or if it changed against `main` without bumping `__version__` in `backend/app/__init__.py` (keep `pyproject.toml` in step). Tests also check that every path the Streamlit and Next.js clients call exists in the spec.

Ask the maintainer before:
- adding any paid service or changing the model provider
- force-pushing or rewriting history on `main`
- changing the API contract (needs a `BREAKING CHANGE:` footer and a version bump)

## Roadmap

Work is tracked as GitHub issues labelled by area (`reliability`, `evals`, `security`, …) and priority (`P0`–`P2`). Each issue body names its phase. Check open `P0` issues first.
