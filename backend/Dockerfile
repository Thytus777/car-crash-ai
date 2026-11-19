# syntax=docker/dockerfile:1
# Base images are pinned by digest; Dependabot proposes updates weekly.
ARG PYTHON_IMAGE=python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.9@sha256:d3b601f0c7b118bc1753febf7c41cc80981df678445e0254284eecf84db79a7d

FROM ${UV_IMAGE} AS uv

# --- build: locked dependencies + redaction models --------------------------
FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

# Dependencies first so this layer caches across code changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Redaction models: pinned by sha256, fetched at build time so the service
# never downloads at runtime. Own layer, cached until the pins change.
COPY scripts/fetch_models.py scripts/fetch_models.py
RUN .venv/bin/python scripts/fetch_models.py

# --- runtime: slim, non-root, only what the service needs -------------------
FROM ${PYTHON_IMAGE} AS runtime

# Apply Debian security updates (the pinned base can lag behind fixes; Trivy
# gates the result), then add the shared libraries weasyprint (PDFs) needs.
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 \
        libgdk-pixbuf-2.0-0 libcairo2 libxml2 libxslt1.1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=build --chown=app:app /app/.venv /app/.venv
COPY --from=build --chown=app:app /app/models /app/models
COPY --chown=app:app . .
RUN mkdir -p /app/uploads /app/cache && chown app:app /app/uploads /app/cache

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # The image is what gets deployed: never accept unredacted uploads.
    REDACTION_REQUIRED=true \
    PORT=8000

USER app
EXPOSE 8000

# Cloud Run sets PORT; locally it defaults to 8000.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
