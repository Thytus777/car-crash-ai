# Data handling and retention

What the service stores, for how long, and what leaves it. If code changes any row below, update this file in the same PR.

## Redaction happens first

Every uploaded photo is processed in this order:
1. Decode and EXIF-rotate.
2. Resize to at most 1600 px.
3. Detect faces (YuNet) and number plates (YOLOv9 plate detector), then pixelate and blur them.
4. Write the result to disk.

The original bytes are never written anywhere. Everything downstream (disk, model providers, logs, caches, PDFs) only ever sees the redacted image.

When the models aren't installed:
- **`REDACTION_REQUIRED=true`** (the Docker image default): uploads are refused with `503 redaction-unavailable`, and `/readyz` fails.
- **Local development without models:** uploads are stored unredacted, and `/readyz` reports redaction as `DISABLED`. Never run that way with real users.

Detection isn't perfect. The settings favour blurring too much over too little (`REDACTION_PLATE_THRESHOLD=0.25`). See ADR 0004 for what that costs.

## What is stored

| Data | Where | Contains | Kept for | Deleted by |
|---|---|---|---|---|
| Redacted photos | `UPLOAD_DIR/<upload_id>/` | JPEGs ≤ 1600 px, faces and plates blurred | **24 h** (`UPLOAD_RETENTION_HOURS`) | Hourly purge in the API process, plus one at startup |
| Image quality warnings | `UPLOAD_DIR/<upload_id>/quality.json` | Blur/brightness flags per file name | Same as photos | Same |
| Assessment results | Postgres `estimates`, `upload_sessions` | Vehicle make, model and year, **VIN if the user supplied one**, damage, costs, report JSON. No images | Until deleted | Manual: no automatic expiry yet |
| Result cache | `RESULT_CACHE_DIR` | Complete reports keyed by image hashes | 24 h (`RESULT_CACHE_TTL_HOURS`), checked on read | Expired entries are removed when read |
| Logs | stdout (JSON) | Request ID, route, status, timings, model/token counts, stage outcomes | Set by the log platform | Log platform |
| Traces | OTel collector → Jaeger | Span names, durations, model, tokens, cost. No prompts, images or outputs | Set by the trace backend | Trace backend |
| Eval data | `evals/` (repo / local) | Labelled cases, blurred on labelling; scraped images never committed | Versioned with the repo | Maintainer |

**Never logged or traced:** images, prompt text, raw model output, API keys (`SecretStr`), or auth headers (the collector strips them).

## What leaves the service

| Destination | What is sent | Why |
|---|---|---|
| Google Gemini / OpenAI | Redacted photos (≤ 1024 px by default), prompts, vehicle make/model/year | Damage analysis; subject to each provider's API data terms |
| NHTSA vPIC | The VIN, only if the user provides one | Vehicle decoding |
| SerpAPI and the result pages it returns | Search query: year, make, model, part name | Live part prices |

## Known gaps

- **Estimates in Postgres have no automatic expiry, and they keep the VIN.** Add a retention job, or drop the VIN after decoding, before handling real customers.
- **Redaction recall is unmeasured on a labelled set.** Only a 4-photo spot check has been done (ADR 0004).
- **Result-cache entries that are never read again stay on disk until manually cleared.** They contain no images.
