# Service level objectives

> **Status: initial targets, not measurements.** No production traffic has been observed yet. These objectives are set from the pipeline's design: 4–6 sequential stages, 6–10 model calls, a 45 s per-attempt timeout. Revisit them after the first 28 days of real data, and record any change and its reason here.

All SLIs come from the Prometheus metrics at `GET /metrics` (`backend/app/core/metrics.py`). The window is a rolling **28 days**.

## SLO 1: Assessment availability

**99.0%** of `POST /api/v1/analyze` requests don't fail on our side.

- **Good:** any response except 5xx. 4xx responses are client or input problems. 429 means every provider is rate-limiting us; it's tracked separately (below) because it reflects quota, not code.
- **Error budget:** 1% ≈ 7 h 17 min of total failure per 28 days, or 1 in 100 requests.

```promql
1 - (
  sum(rate(http_requests_total{route="/api/v1/analyze", status=~"5.."}[28d]))
  /
  sum(rate(http_requests_total{route="/api/v1/analyze"}[28d]))
)
```

## SLO 2: Assessment latency

**95%** of successful assessments complete within **60 s**; **99%** within **90 s**.

```promql
# Share of successful requests faster than 60 s (needs the 60 s histogram bucket)
sum(rate(http_request_duration_seconds_bucket{route="/api/v1/analyze", le="60"}[28d]))
/
sum(rate(http_request_duration_seconds_count{route="/api/v1/analyze"}[28d]))

# p95 over the last hour, for dashboards
histogram_quantile(0.95,
  sum by (le) (rate(http_request_duration_seconds_bucket{route="/api/v1/analyze"}[1h])))
```

## SLO 3: Upload latency

**99%** of `POST /api/v1/upload` requests complete within **5 s**. There are no model calls here, just validation, resizing and storage.

## SLO 4: Complete results

**95%** of assessments are `complete`, not `partial`. A partial report means a zone, a price or the sanity check degraded (see `issues` in the response).

```promql
sum(rate(assessments_total{result="complete"}[28d]))
/
sum(rate(assessments_total{result=~"complete|partial"}[28d]))
```

## Tracked, not objectives

| Signal | Query | Why it isn't an SLO |
|---|---|---|
| Upstream rate limiting | `rate(http_requests_total{route="/api/v1/analyze",status="429"}[1h])` | Set by provider quotas; the fix is billing or quota, not code |
| Model call failure rate | `sum(rate(llm_calls_total{outcome="failed"}[1h])) / sum(rate(llm_calls_total[1h]))` | Leading indicator for SLOs 1 and 4 |
| Model latency by task | `histogram_quantile(0.95, sum by (le, task) (rate(llm_call_duration_seconds_bucket[1h])))` | Shows which stage is slowing SLO 2 |
| Cost per assessment (USD) | `sum(rate(llm_cost_usd_total[1h])) / sum(rate(assessments_total[1h]))` | Budget, not reliability: over-budget requests are counted in `budget_exceeded_total{budget="cost"}`. Only priced models count; see `app/data/model_pricing.yaml` |
| Over latency budget | `rate(budget_exceeded_total{budget="latency"}[1h])` | Per-request view of SLO 2 (`REQUEST_LATENCY_BUDGET_S`, default 60 s) |
| Detection quality | Component F1 from `make eval` (`evals/results/`) | Measured offline on the labelled set, not from traffic |

## Alerting (multi-window burn rate)

Page when the 1 h **and** 5 min error rates both exceed 14.4× the budget rate. At that pace the month's budget is gone in about 2 days. Open a ticket at 6× over 6 h and 30 min.

```promql
# Page: availability burning fast
(
  sum(rate(http_requests_total{route="/api/v1/analyze",status=~"5.."}[1h]))
  / sum(rate(http_requests_total{route="/api/v1/analyze"}[1h]))
) > (14.4 * 0.01)
and
(
  sum(rate(http_requests_total{route="/api/v1/analyze",status=~"5.."}[5m]))
  / sum(rate(http_requests_total{route="/api/v1/analyze"}[5m]))
) > (14.4 * 0.01)
```

## When the budget is spent

Freeze prompt and model changes; the eval gate in CI also blocks them. Fix reliability first, and use traces (Jaeger, filter on `assess` spans with errors) and `request_id` in the logs to find the failing stage. `docs/RUNBOOK.md` (Phase 7) covers incident triage.
