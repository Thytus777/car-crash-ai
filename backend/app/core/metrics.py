"""Prometheus metrics (GET /metrics). SLO queries live in docs/SLO.md.

Labels are low-cardinality only: route templates (never raw paths), provider,
model, task, and fixed outcome sets.
"""

from prometheus_client import Counter, Histogram

# Assessments take tens of seconds (several model calls), so buckets reach 2 min.
_REQUEST_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 30, 45, 60, 90, 120)
_MODEL_BUCKETS = (0.25, 0.5, 1, 2, 4, 8, 15, 30, 45, 60)

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "HTTP requests by route template, method and status code",
    ["route", "method", "status"],
)
HTTP_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency by route template",
    ["route", "method"],
    buckets=_REQUEST_BUCKETS,
)
ASSESSMENTS = Counter(
    "assessments_total",
    "Assessments by result: complete, partial, vehicle_confirmation_needed, "
    "rejected (triage) or error",
    ["result"],
)
LLM_CALLS = Counter(
    "llm_calls_total",
    "Model calls (one per generate() attempt sequence) by outcome",
    ["provider", "model", "task", "outcome", "cached"],
)
LLM_TOKENS = Counter(
    "llm_tokens_total",
    "Model tokens by direction (input / output incl. reasoning)",
    ["provider", "model", "direction"],
)
LLM_COST = Counter(
    "llm_cost_usd_total",
    "Model spend in USD, for models with a price in app/data/model_pricing.yaml",
    ["provider", "model"],
)
BUDGET_EXCEEDED = Counter(
    "budget_exceeded_total",
    "Assessments over a per-request budget",
    ["budget"],
)
RESULT_CACHE = Counter(
    "result_cache_total",
    "Assessment result cache lookups and stores",
    ["outcome"],  # hit | miss | expired | store
)
DAMAGE_ROUTING = Counter(
    "damage_routing_total",
    "Cheap-first routing decisions per damage zone",
    ["decision"],  # fast_accepted | escalated_failure | _borderline | _empty
)
LLM_DURATION = Histogram(
    "llm_call_duration_seconds",
    "Model time per call, including retries",
    ["provider", "task"],
    buckets=_MODEL_BUCKETS,
)
