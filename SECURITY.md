# Security Policy

## Reporting a vulnerability

Report vulnerabilities through [GitHub private vulnerability reporting](https://github.com/Thytus777/car-crash-ai/security/advisories/new), not through public issues.

Please include the affected endpoint or file, steps to reproduce, and the impact. You'll get an acknowledgement within 7 days.

## Scope

In scope:
- the FastAPI backend (`backend/`)
- the web frontend (`frontend-next/`)
- the CI/CD configuration

Especially relevant, given what the service does:
- prompt injection through image content or scraped web pages
- leaking uploaded photos or API keys
- path traversal through upload identifiers
- abuse that runs up paid model usage

## Handling of secrets and data

- API keys are read from environment variables only. `.env` files are git-ignored, and gitleaks runs in pre-commit and in CI.
- Uploaded vehicle photos can contain faces and number plates. Redaction and the retention policy are tracked in #10.

## Supported versions

Only the latest release on `main` receives fixes.
