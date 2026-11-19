# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Makefile entry point; CI runs the same targets.
- uv-managed dependencies with a committed `uv.lock` and Python 3.12 pin.
- ruff (lint + format), mypy `--strict`, pre-commit hooks (gitleaks, Conventional Commits).
- CI jobs: lint, typecheck, unit + integration tests with a coverage gate, Docker build.
- Contributor docs: `AGENTS.md`, `CONTRIBUTING.md`, `SECURITY.md`, PR and issue templates, CODEOWNERS.
- Architecture decision records in `docs/adr/`.

### Changed
- Trunk-based workflow on `main`; the `develop` branch is retired.
- Tests split into `tests/unit` and `tests/integration` with pytest markers.

### Removed
- Standalone iOS app ([ADR 0001](docs/adr/0001-retire-standalone-ios-app.md)); archived in tag `archive/ios-standalone`.
- Unused dependencies `beautifulsoup4` and `google-search-results`.

### Security
- `backend/.dockerignore` keeps `.env` files and local virtualenvs out of Docker images.

## [0.1.0]

Initial prototype: FastAPI backend with vision-LLM vehicle identification, zone-based damage detection, live/static/AI part pricing, PostgreSQL persistence, PDF reports, Streamlit and Next.js frontends.
