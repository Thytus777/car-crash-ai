# Car Crash AI — Agent Instructions

## Project Overview

This is a **car crash damage detection and assessment AI** built with Python (FastAPI backend) and a Vision LLM for image analysis. The system accepts vehicle images, identifies the vehicle, detects damage per component, scores severity, and estimates repair/replacement costs.

## Architecture

- **Backend:** Python 3.11+ with FastAPI
- **AI:** OpenAI GPT-4 Vision (MVP) → custom YOLO models (production)
- **Database:** PostgreSQL with SQLAlchemy
- **Frontend:** Streamlit (MVP) → Next.js (production)
- **Storage:** S3-compatible object storage for images

## Code Conventions

### Python
- Use Python 3.11+ with type hints on all function signatures
- Follow PEP 8 style, enforced by `ruff`
- Use `pydantic` for all data models (request/response schemas)
- Use `async def` for all FastAPI route handlers
- Organize imports: stdlib → third-party → local (enforced by ruff isort)
- Use `pathlib.Path` over `os.path`
- Environment variables via `pydantic-settings` (never hardcode secrets)

### API Design
- RESTful endpoints under `/api/v1/`
- Return structured JSON with consistent error format: `{"detail": "message"}`
- Use HTTP status codes correctly (200, 201, 400, 422, 500)
- All endpoints must have OpenAPI descriptions

### Testing
- Use `pytest` with `pytest-asyncio` for async tests
- Test files mirror source structure: `app/services/foo.py` → `tests/test_foo.py`
- Use `httpx.AsyncClient` for API endpoint tests
- Minimum: test all API endpoints and service-layer functions

### AI / Prompts
- Store all LLM prompts as constants in dedicated prompt files (e.g., `prompts/damage_assessment.py`)
- Always request structured JSON output from Vision LLMs
- Include the expected JSON schema in every prompt
- Log all LLM inputs/outputs for debugging (redact any PII)

### Data Models
- Severity scores are always `float` in range `[0.0, 1.0]`
- Cost values are `Decimal` with 2 decimal places (never `float` for money)
- Vehicle identification: `make`, `model`, `year` (int), `trim` (optional)
- All damage assessments reference a standard component list (see PROJECT_PLAN.md §3)

## File Structure Rules

- `backend/app/api/routes/` — API endpoint definitions only (thin controllers)
- `backend/app/services/` — Business logic (damage detection, cost estimation, etc.)
- `backend/app/models/` — Pydantic models and DB schemas
- `backend/app/core/` — Configuration, security, shared utilities
- `backend/tests/` — All tests
- `ml/` — ML training scripts and notebooks (Phase 3)

## Security

- Never commit API keys or secrets — use `.env` files (git-ignored)
- Validate all uploaded files: check MIME type, file size, image dimensions
- Rate-limit image upload endpoints
- Sanitize all user input before passing to LLM prompts

## Git Workflow

- **Always ask the user for approval before any git operation** (commit, push, merge, branch creation, etc.)
- **Branching model:** Git Flow with `develop` as the integration branch
  - All feature branches are created from `develop`
  - Branch naming: `feature/<short-description>` (e.g., `feature/image-upload`, `feature/vehicle-identification`)
  - Merge back into `develop` **only when the user confirms** the feature is complete and verified
  - Never merge directly into `main` — `main` is for production releases only
- **Commits:** Use conventional commit messages (e.g., `feat:`, `fix:`, `docs:`, `test:`)
- **Never use `git add -A` or `git add .`** — only stage files directly related to the current task

## Key Decision Records

- **Severity threshold 0.3** — Damage > 0.3 recommends replacement; ≤ 0.3 recommends repair
- **Vision LLM first** — Use GPT-4 Vision for MVP to avoid training data requirements
- **Static price DB for MVP** — Real parts API integration deferred to Phase 2
- **Labor rate default** — $75/hr national average until regional rates are implemented
