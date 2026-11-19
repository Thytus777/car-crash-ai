# 0003. Cheap-first model routing for damage detection

- **Status:** Proposed. Implemented behind `ROUTING_ENABLED` (off). Accept or reject from eval results.
- **Date:** 2026-11-19
- **Issue:** #51

## Context

Damage detection is the most expensive stage: three vision calls per assessment (one per zone), each sending every photo at high detail. Most zones in most photos are undamaged, or damaged far from any repair/replace threshold. Those are cases where a cheaper, faster model may reach the same decision.

The risk runs one way. A cheaper model is more likely to **miss** damage (lower recall) or misjudge severity near a threshold, which flips the repair/replace call and moves the estimate the most.

## Decision (proposed)

Run each zone pass on the provider's fast model first (`GEMINI_FAST_MODEL` / `OPENAI_FAST_MODEL`). Escalate that zone to the strong model when:

1. the fast call fails (timeout, quota, schema-invalid after re-asks), or
2. any finding's severity is within `ROUTING_ESCALATION_MARGIN` (0.1) of its component's repair/replace threshold, or
3. optionally (`ROUTING_ESCALATE_EMPTY_ZONES`), the fast model found no damage at all.

Every decision is counted in `damage_routing_total{decision}`, and each zone span records its tier.

## How it gets accepted or rejected

Run the eval twice on the same dataset version and prompt version, live (`--no-cache`):

```bash
make eval ARGS=--no-cache                                                          # baseline
ROUTING_ENABLED=true GEMINI_FAST_MODEL=<candidate> make eval ARGS=--no-cache       # routed
make eval-compare BASE=<baseline>.json CANDIDATE=<routed>.json
```

**Accept** only if all of these hold:
- component recall drops by no more than `evals/thresholds.yaml` allows (0.05), and F1 by no more than 0.03;
- severity exact-match drops by no more than 0.05;
- cost per request falls by at least **25%**, and p95 latency doesn't rise. Both need the candidate and strong models priced in `app/data/model_pricing.yaml`;
- recall on the `night` and `partial_view` tags doesn't drop by more than the overall threshold. These are where a weaker model is likeliest to miss.

If recall fails but cost passes, try `ROUTING_ESCALATE_EMPTY_ZONES=true` before rejecting. It gives up much of the saving but bounds the miss risk.

Record the comparison table and the chosen fast model here, and set the status to Accepted or Rejected.

## Alternatives considered

- **Always the strong model.** The current default: simplest and highest quality, and the most expensive.
- **Always the fast model.** Cheapest, but the miss risk is unbounded and nothing checks it.
- **Route on the vehicle-ID confidence instead.** Vehicle confidence says little about how hard the damage is to judge.
- **Fine-tuned or self-hosted detector (e.g. YOLO) for the first pass.** Needs a much larger labelled set than this project has. Revisit after the dataset grows.

## Consequences

- With routing on, a request's model calls vary from 3 (all zones accepted fast) to 6 (all escalated) for damage detection. Latency and cost become bimodal, which the per-request budgets and metrics already surface.
- Prompt text is shared between tiers, so a prompt change affects both, and both must be re-evaluated.
- Until this is accepted, the flag stays off in every environment.
