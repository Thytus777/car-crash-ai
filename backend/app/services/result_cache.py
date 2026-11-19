"""Cache of complete assessment reports, keyed by what determines them.

The key covers the processed images' hashes, the prompt version, the
configured models and every request option. A new upload of the same photos
with the same settings returns the stored report without model calls.

Only ``complete`` reports are stored: a partial report reflects a transient
failure, so replaying it would replay the failure. Entries expire after
``result_cache_ttl_hours``, because part prices drift.

Storage is one JSON file per key on local disk, so the cache is per
instance. A multi-instance deployment would back this with a shared store.
"""

import hashlib
import json
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import ValidationError

from app import __version__
from app.core.config import settings
from app.core.metrics import RESULT_CACHE
from app.models.estimate import AssessmentReport


def cache_key(images: Sequence[bytes], options: Mapping[str, object]) -> str:
    material = {
        "api_version": __version__,
        "prompt_version": settings.prompt_version,
        "ai_provider": settings.ai_provider,
        "models": [
            settings.gemini_model,
            settings.openai_vision_model,
            settings.openai_text_model,
        ],
        "images": sorted(hashlib.sha256(i).hexdigest() for i in images),
        "options": dict(options),
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()


def _path(key: str) -> Path:
    return Path(settings.result_cache_dir) / f"{key}.json"


def get(key: str) -> AssessmentReport | None:
    path = _path(key)
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - stored["stored_at"] > settings.result_cache_ttl_hours * 3600:
            path.unlink(missing_ok=True)
            RESULT_CACHE.labels("expired").inc()
            return None
        report = AssessmentReport.model_validate(stored["report"])
    except (OSError, KeyError, ValueError, ValidationError):
        RESULT_CACHE.labels("miss").inc()
        return None
    RESULT_CACHE.labels("hit").inc()
    return report


def put(key: str, report: AssessmentReport) -> None:
    if report.status != "complete":
        return
    path = _path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"stored_at": time.time(), "report": report.model_dump(mode="json")}
    path.write_text(json.dumps(record), encoding="utf-8")
    RESULT_CACHE.labels("store").inc()
