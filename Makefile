# Single entry point for local dev and CI. CI calls these same targets.
# Requires: uv (https://docs.astral.sh/uv/) and GNU make.

UV      ?= uv
BACKEND := backend
RUN     := $(UV) run --directory $(BACKEND)
# Tests also cover the Streamlit demo, so they need its dependency group.
TEST    := $(RUN) --group demo pytest
# Floor only ever goes up (issue #14 target of 80 reached).
COV_MIN ?= 84

.DEFAULT_GOAL := help
.PHONY: help setup lock-check lint format format-check typecheck test test-integration openapi openapi-check openapi-version-check \
        test-all coverage eval run run-demo docker pre-commit clean

help: ## List targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-18s %s\n",$$1,$$2}'

setup: ## Install all deps (incl. dev + demo) and git hooks
	$(UV) sync --directory $(BACKEND) --group demo
	$(RUN) pre-commit install --install-hooks -t pre-commit -t commit-msg

lock-check: ## Fail if uv.lock is out of date with pyproject.toml
	$(UV) lock --directory $(BACKEND) --check

lint: ## Ruff lint (backend + Streamlit)
	$(RUN) ruff check ..

format: ## Apply ruff formatting and autofixes
	$(RUN) ruff check .. --fix
	$(RUN) ruff format ..

format-check: ## Fail if anything is not ruff-formatted
	$(RUN) ruff format .. --check

typecheck: ## mypy --strict on the backend package
	$(RUN) mypy

test: ## Unit tests: fast, no network, no real LLM
	$(TEST) -m unit

test-integration: ## Integration tests: FastAPI app with fixture LLM responses
	$(TEST) -m integration

test-all: ## All unit + integration tests
	$(TEST) -m "unit or integration"

coverage: ## Unit + integration with coverage gate; writes backend/coverage.xml
	$(TEST) -m "unit or integration" --cov --cov-report=term --cov-report=xml --cov-fail-under=$(COV_MIN)

openapi: ## Regenerate the committed OpenAPI contract (backend/openapi.json)
	$(RUN) python scripts/openapi.py export

openapi-check: ## Fail if backend/openapi.json is stale
	$(RUN) python scripts/openapi.py check

openapi-version-check: ## Fail if the contract changed vs BASE=<spec.json> without a version bump
	$(RUN) python scripts/openapi.py check-version $(BASE)

eval: ## Run the eval harness (Phase 3, issue #15)
	@echo "Eval harness not implemented yet; tracked in #15." && exit 1

run: ## Start the API on :8000 with reload
	$(RUN) uvicorn app.main:app --reload

run-demo: ## Start the Streamlit demo UI on :8501
	$(UV) run --directory $(BACKEND) --group demo streamlit run ../frontend/streamlit_app.py

docker: ## Build the backend image
	docker build -t car-crash-ai-backend:local $(BACKEND)

pre-commit: ## Run every pre-commit hook against all files
	$(RUN) pre-commit run --all-files

clean: ## Remove caches and local build artefacts
	rm -rf $(BACKEND)/.pytest_cache $(BACKEND)/.mypy_cache $(BACKEND)/.ruff_cache \
	       $(BACKEND)/.coverage $(BACKEND)/coverage.xml $(BACKEND)/htmlcov
