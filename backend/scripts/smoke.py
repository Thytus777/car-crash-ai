"""Post-deploy smoke test: python scripts/smoke.py --base-url URL [--api-key KEY].

Checks only what a deploy can break, without paid model calls:
liveness, readiness, auth (when a key is given), and a real upload, which
exercises image processing and redaction end to end. Exits 1 on any failure.
"""

import argparse
import os
import sys
from collections.abc import Callable
from io import BytesIO
from typing import Any

import httpx
from PIL import Image

Check = tuple[str, Callable[[], str | None]]  # (name, returns error or None)


def _photo() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (800, 600), color=(180, 30, 30)).save(buf, format="JPEG")
    return buf.getvalue()


def checks(client: Any, api_key: str | None) -> list[Check]:
    auth = {"X-API-Key": api_key} if api_key else {}

    def healthz() -> str | None:
        r = client.get("/healthz")
        return None if r.status_code == 200 else f"status {r.status_code}"

    def readyz() -> str | None:
        r = client.get("/readyz")
        if r.status_code != 200:
            return f"status {r.status_code}: {r.text[:300]}"
        status = r.json().get("status")
        return None if status in ("ready", "degraded") else f"status {status!r}"

    def rejects_missing_key() -> str | None:
        r = client.get("/api/v1/estimates")
        return None if r.status_code == 401 else f"expected 401, got {r.status_code}"

    def accepts_key() -> str | None:
        r = client.get("/api/v1/estimates", headers=auth)
        return None if r.status_code == 200 else f"status {r.status_code}"

    def upload() -> str | None:
        r = client.post(
            "/api/v1/upload",
            headers=auth,
            files=[("images", ("smoke.jpg", _photo(), "image/jpeg"))],
        )
        if r.status_code != 200:
            return f"status {r.status_code}: {r.text[:300]}"
        image = r.json()["images"][0]
        return None if "redacted_regions" in image else "no redaction field"

    found: list[Check] = [("healthz", healthz), ("readyz", readyz)]
    if api_key:
        found += [
            ("auth rejects missing key", rejects_missing_key),
            ("auth accepts key", accepts_key),
        ]
    found.append(("upload + redaction", upload))
    return found


def run(client: Any, api_key: str | None) -> bool:
    ok = True
    for name, check in checks(client, api_key):
        try:
            error = check()
        except Exception as exc:  # report every check, never stop at the first
            error = f"{type(exc).__name__}: {exc}"
        print(
            f"{'PASS' if error is None else 'FAIL'}  {name}"
            + (f"  ({error})" if error else "")
        )
        ok = ok and error is None
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key", default=os.environ.get("SMOKE_API_KEY"))
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=60) as client:
        return 0 if run(client, args.api_key or None) else 1


if __name__ == "__main__":
    sys.exit(main())
