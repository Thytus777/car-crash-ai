"""API-key auth, per-client rate limits, and production safety checks.

Auth is on whenever API_KEYS is set (comma-separated). APP_ENV=production
refuses to start without keys, with a wildcard CORS origin, or without
required redaction. Health probes stay open; everything else needs a key.

Rate limits are token buckets per API key (or per client IP when auth is
off), held in process memory: per instance, like the result cache. A shared
store would be needed to enforce a global limit across replicas.
"""

import hashlib
import hmac
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import FastAPI, Request, Response

from app.api.problems import problem_response_for
from app.core.config import Settings, settings
from app.core.errors import RateLimitedError, UnauthorizedError

OPEN_PATHS = frozenset({"/healthz", "/readyz", "/health"})
EXPENSIVE_PATHS = frozenset({"/api/v1/analyze"})  # paid model calls


def check_production_settings(config: Settings) -> None:
    """Refuse to run a production instance with unsafe settings."""
    if config.app_env != "production":
        return
    problems = []
    if not config.api_keys:
        problems.append("API_KEYS must be set")
    if "*" in config.cors_origins:
        problems.append("CORS_ORIGINS must list explicit origins, not '*'")
    if not config.redaction_required:
        problems.append("REDACTION_REQUIRED must be true")
    if problems:
        raise RuntimeError("Unsafe production settings: " + "; ".join(problems))


def _presented_key(request: Request) -> str:
    key = request.headers.get("x-api-key", "")
    if not key:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() == "bearer":
            key = token.strip()
    return key


def _matches(presented: str) -> str | None:
    """Return a stable, non-reversible ID for a valid key, else None."""
    for configured in settings.api_keys:
        secret = configured.get_secret_value()
        # Constant-time comparison; check every key to avoid timing leaks.
        if presented and hmac.compare_digest(presented.encode(), secret.encode()):
            return "key-" + hashlib.sha256(secret.encode()).hexdigest()[:10]
    return None


@dataclass
class _Bucket:
    tokens: float
    updated: float


_buckets: dict[tuple[str, str], _Bucket] = {}


def reset_rate_limits() -> None:
    _buckets.clear()


def _take(client: str, scope: str, per_minute: int) -> float:
    """Spend one token; return 0 if allowed, else seconds until the next one."""
    now = time.monotonic()
    bucket = _buckets.setdefault((client, scope), _Bucket(per_minute, now))
    refill = (now - bucket.updated) * per_minute / 60
    bucket.tokens = min(per_minute, bucket.tokens + refill)
    bucket.updated = now
    if bucket.tokens >= 1:
        bucket.tokens -= 1
        return 0.0
    return (1 - bucket.tokens) * 60 / per_minute


def install_access_control(app: FastAPI) -> None:
    @app.middleware("http")
    async def access_control(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        if path in OPEN_PATHS or request.method == "OPTIONS":
            return await call_next(request)

        if settings.api_keys:
            client = _matches(_presented_key(request))
            if client is None:
                response = problem_response_for(
                    request, UnauthorizedError("A valid API key is required.")
                )
                response.headers["WWW-Authenticate"] = 'Bearer realm="car-crash-ai"'
                return response
        else:
            client = "ip-" + (request.client.host if request.client else "unknown")
        request.state.client_id = client

        checks = [("all", settings.rate_limit_per_minute)]
        if path in EXPENSIVE_PATHS:
            checks.append(("analyze", settings.analyze_rate_limit_per_minute))
        for scope, limit in checks:
            wait = _take(client, scope, limit)
            if wait:
                response = problem_response_for(
                    request,
                    RateLimitedError(
                        f"Rate limit of {limit} requests per minute exceeded "
                        f"for {scope}."
                    ),
                )
                response.headers["Retry-After"] = str(max(1, math.ceil(wait)))
                return response
        return await call_next(request)
