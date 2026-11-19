# Evals

Measures the **production pipeline** (`app.services.assessment.assess`) against human-labelled cases. The harness code is in `backend/evals/`.

| Path | What |
|---|---|
| `LABELLING.md` | how to label; read this first |
| `taxonomy.yaml` | fixed components, damage types, severity levels, tags |
| `dataset/` | cases (`<case_id>/label.json` + committed images) and `manifest.json` (version, smoke subset) |
| `local_images/` | images you may not redistribute (git-ignored) |
| `thresholds.yaml` | how far a run may regress before the eval gate fails |
| `results/` | one `.json` + `.md` per run |
| `.cache/` | cached model replies (git-ignored) |

## Run

```bash
make eval-validate                 # labels, hashes, image limits, smoke list
make eval                          # all cases with images on this machine
make eval-smoke                    # the manifest's smoke subset (what CI runs)
make eval ARGS=--no-cache          # force live model calls
make eval ARGS="--case corolla-front-night-01"
make eval-compare BASE=evals/results/a.json CANDIDATE=evals/results/b.json
```

Each run writes `results/<UTC time>_<prompt version>_<model>.json`, with every per-case prediction and model call, plus a Markdown summary. Each run records:
- the git commit, and whether there were uncommitted changes
- the dataset version and label fingerprint
- the prompt version and the models used
- cache hits and misses

## Metrics

| Metric | Definition |
|---|---|
| Component precision / recall / F1 | Micro-averaged over (case, component) pairs on assessable cases; also per component and per tag |
| Severity exact / within one | On correctly detected components: the model's 0–1 score mapped onto the labelled level, using the prompts' severity bands |
| Triage accuracy | The accept/reject decision matches the label. Also reports reject recall and false-reject rate |
| Vehicle make+model | Case-insensitive match where a vehicle is labelled |
| Cost MAE / within range | Grand total against the labelled range (midpoint for MAE); USD labels only, reported per `basis` |
| Schema-valid first attempt | Model calls that returned schema-valid output on the first try |
| Retry rate / call failure rate | Calls needing more than one attempt / calls that ultimately failed |
| Latency p50 / p95 | Model time per case. Cached replies carry their originally recorded latency, so cached runs stay comparable |
| Cost per request | Tokens × `backend/app/data/model_pricing.yaml` (the service's own price table); "n/a" until every model used is priced |

A metric shows `n/a`, never 0, when there is nothing to measure it on.

## Caching

Replies are cached under a key made of: provider, model, prompt version, output schema, prompt text, image hashes, generation settings, and the position in the re-ask sequence. Errors are never cached.
- Re-running the same prompt version and model on the same images costs nothing.
- Changing a prompt (a new prompt version), the model or an image naturally misses the cache.

## Sweeping model input

Image size and quality sent to the models are settings, so comparing them needs no re-labelling or re-uploading:

```bash
MODEL_IMAGE_MAX_EDGE=768  make eval ARGS=--no-cache
MODEL_IMAGE_MAX_EDGE=1024 make eval ARGS=--no-cache
make eval-compare BASE=evals/results/<1024>.json CANDIDATE=evals/results/<768>.json
```

Both caches key on the bytes actually sent, so each setting gets its own entries.
