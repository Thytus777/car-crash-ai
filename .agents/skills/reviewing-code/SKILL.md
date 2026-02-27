---
name: reviewing-code
description: "Reviews code for quality, security, and adherence to project conventions. Use when asked to review a PR, diff, or code changes."
---

# Code Review for Car Crash AI

## Review Checklist

### 1. Python Conventions
- Type hints on all function signatures
- PEP 8 compliance (ruff-compatible)
- Pydantic models for all request/response schemas
- `async def` on all FastAPI route handlers
- `pathlib.Path` over `os.path`
- No hardcoded secrets — environment variables via `pydantic-settings`

### 2. API Design
- Routes under `/api/v1/`
- Consistent error format: `{"detail": "message"}`
- Correct HTTP status codes
- OpenAPI descriptions on all endpoints

### 3. AI / Prompt Quality
- Prompts stored as constants in `prompts/` files, not inline
- Structured JSON output requested in every LLM prompt
- JSON schema included in prompt
- LLM inputs/outputs logged (PII redacted)

### 4. Data Model Correctness
- Severity: `float` in `[0.0, 1.0]`
- Money: `Decimal` with 2 decimal places, never `float`
- Vehicle: `make` (str), `model` (str), `year` (int), `trim` (Optional[str])
- Components reference the standard component list

### 5. Security
- No API keys or secrets in code
- Uploaded files validated (MIME type, size, dimensions)
- User input sanitized before LLM prompt injection
- Rate limiting on upload endpoints

### 6. Testing
- Tests exist for all API endpoints
- Tests exist for all service-layer functions
- Uses `pytest` + `pytest-asyncio`
- Uses `httpx.AsyncClient` for endpoint tests

## Review Process

1. Read all changed files
2. Check each item in the checklist above
3. Flag issues with severity: **critical** (must fix), **warning** (should fix), **nit** (style preference)
4. Verify tests cover the changes
5. Run `ruff check` and `pytest` if possible
