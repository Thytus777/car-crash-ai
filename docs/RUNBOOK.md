# Runbook

How Car Crash AI is shipped, rolled back and debugged in production.

## How a change reaches production

```
PR ──CI green──▶ squash-merge to main
                    │
                    ▼  release.yml (build job)
          build once ─ non-root check ─ Trivy ─ SBOM ─ push ghcr.io/thytus777/car-crash-ai/backend:sha-<commit>
          ─ SLSA provenance attestation
                    │
                    ▼  deploy.yml (staging)
          copy digest to Artifact Registry ─ migrations ─ Cloud Run deploy ─ smoke test
                    │
     release-please PR merged ─▶ GitHub release vX.Y.Z published
                    │
                    ▼  release.yml (resolve + production)
          find the digest built for the tagged commit ─ verify its attestation
          ─ wait for approval on the `production` environment ─ same deploy.yml
```

The image that runs in production has the same digest as the one that was scanned, tested on staging and attested. Nothing is rebuilt for a release.

Every deploy:
1. records the revision serving now
2. runs `alembic upgrade head`
3. deploys the new revision and routes 100% of traffic to it
4. runs `backend/scripts/smoke.py` (health, readyz, auth rejection, an authenticated upload with redaction)
5. **if the smoke test fails, routes traffic back to the recorded revision automatically**

## Rollback

### One command (preferred)

Find the digest that was good, then deploy it again through the normal pipeline (approval, migrations check and smoke test included):

```bash
# The images each environment ran, newest first
gcloud run revisions list --service car-crash-ai-production --region "$REGION" \
  --format='table(metadata.name, spec.containers[0].image, metadata.creationTimestamp)'

gh workflow run release.yml -f environment=production -f digest=sha256:<good digest>
```

The run summary of every deploy also prints the digest it deployed.

### Fastest (seconds, no pipeline)

Shift traffic back to the previous revision, which is still warm on Cloud Run:

```bash
gcloud run services update-traffic car-crash-ai-production --region "$REGION" \
  --to-revisions=<previous-revision>=100
```

The next deploy routes traffic to the new revision again (`--to-latest`), so this pin doesn't need undoing by hand. Follow up with the one-command rollback, or with a fix, so `main` and production agree again.

### Database migrations

Migrations are **expand-only**: add columns and tables, never drop or rename in the same release that stops using them. The previous revision therefore keeps working on the new schema, and a rollback never needs `alembic downgrade`. Removing a column takes two releases: stop using it, then drop it.

## Incident triage

Start broad, then narrow down by request.

1. **Is it up?**
   ```bash
   curl -s https://<service-url>/health       # process alive (Cloud Run reserves /healthz: it returns Google's own 404)
   curl -s https://<service-url>/readyz | jq  # per-check detail: database, redaction models, providers
   ```
   `readyz` names every check. A failed required check (prompts, upload dir, model provider, redaction) makes it `not_ready` with a 503. A failed database check makes it `degraded` with a 200: assessments still work, but estimates aren't saved.

2. **What changed?** Look at the last `release` workflow run and at `gcloud run revisions list` (above). If the problem started with a deploy, roll back first and debug afterwards.

3. **Errors in the logs.** Logs are one JSON object per line. Cloud Logging parses them into `jsonPayload`, with `severity` set from the line's level:
   ```bash
   gcloud logging read \
     'resource.type="cloud_run_revision"
      AND resource.labels.service_name="car-crash-ai-production"
      AND severity>=ERROR' --freshness=1h --limit 50 \
     --format='table(timestamp, jsonPayload.request_id, jsonPayload.logger, jsonPayload.message)'
   ```

4. **One request end to end.** Every response carries `X-Request-ID`, and so does every problem body. Use it to filter:
   ```bash
   gcloud logging read 'jsonPayload.request_id="<id>"' --freshness=1d \
     --format='value(timestamp, jsonPayload.message)'
   ```
   Log lines also carry `trace_id`. Traces are exported only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set (it isn't by default on Cloud Run). With a collector configured, open the trace to see which stage (`stage.*`) or model call (`llm.call`) was slow or failed.

5. **Common problem types** (from `docs/errors.md`):

   | Symptom | Likely cause | Action |
   |---|---|---|
   | many `upstream-*` (502/503/504) | the model provider is failing or rate-limiting | check the provider status page; the fallback provider is used only if its key is configured |
   | `redaction-unavailable` (503) and `readyz` not ready | the image was built without the redaction models | rebuild; `fetch_models.py` runs in the Docker build |
   | `rate-limited` (429) for one client | the client is over its bucket | expected behaviour; limits are per instance |
   | `unauthorized` (401) for everyone | `<env>-api-keys` secret changed or empty | check the secret's latest version |
   | 500 `internal-error` | a bug | find the request ID's stack trace (step 4), roll back if it came with a deploy |

6. **Cost or latency spike.** `meta.cost_usd` and `meta.latency_s` are on every response, and the `budget_exceeded_total`, `llm_cost_usd_total` and request-latency series are on `/metrics` (API key required). SLO queries and burn-rate alerts are in `docs/SLO.md`.

## Secrets and keys

- Stored in Google Secret Manager: `gemini-api-key`, `<env>-api-keys` (comma-separated) and `<env>-database-url`. Cloud Run reads `:latest` at instance start.
- **Rotate an API key:** add a new secret version with old and new keys together, deploy (or wait for new instances), move clients over, then add a version with only the new key.
- **Rotate the Gemini key:** create a new key, add it as a new `gemini-api-key` version, redeploy, then delete the old key in Google AI Studio.
- GitHub reaches Google Cloud through Workload Identity Federation (OIDC). There are no stored service-account keys to rotate.

## First-time setup

`scripts/setup_gcp.sh` walks through the one-off setup: project, APIs, Artifact Registry, service accounts, the Workload Identity pool, secrets, the Neon database URL, and the GitHub variables and environments. Deploy jobs are skipped until it has set `GCP_PROJECT_ID`.
