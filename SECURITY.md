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

## Access control

- **API keys:** set `API_KEYS` (comma-separated). Every `/api/v1/*` route and `/metrics` then needs `X-API-Key` or `Authorization: Bearer`. Keys are compared in constant time and never logged; only a short hash identifies a client. `/healthz` and `/readyz` stay open for orchestrators.
- **Production mode:** `APP_ENV=production` refuses to start without keys, with a wildcard CORS origin, or without `REDACTION_REQUIRED=true`.
- **Rate limits:** per client, per minute, with a tighter bucket for `/analyze` because it spends money on model calls. Limits are per instance (in memory).
- **Browser clients:** a key in the Next.js bundle (`NEXT_PUBLIC_API_KEY`) is visible to users and only deters casual abuse. A public deployment should put a server-side proxy in front of the API that adds the key.
## Untrusted input
- **Scraped pages:** text goes inside a `<page>` fence that the prompt declares untrusted, and that the text itself can't close. Extracted prices must fall within configured bounds and carry a 3-letter currency, so an injected "$0.01" or "$9,999,999" is dropped.
- **Text in photos:** treated as scene content, never as an instruction to the model (prompt v4). Eval cases tagged `prompt_injection` measure whether this holds.
- **Outbound fetches:** https only, every resolved address must be publicly routable, redirects are re-checked per hop, and bodies are capped at 2 MB. A hostname's DNS answer could still change between the check and the connection; pinning the resolved address is the remaining hardening step.

## Handling of secrets and data

- API keys are read from environment variables only. `.env` files are git-ignored, and gitleaks runs in pre-commit and in CI.
- Uploaded photos are redacted (faces and number plates blurred) before storage or any model call, and deleted after 24 h. See `docs/DATA_RETENTION.md` and ADR 0004.

## Supported versions

Only the latest release on `main` receives fixes.
