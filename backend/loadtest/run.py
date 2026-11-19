"""Run the load test end to end; write loadtest/results/<time>.json and .md.

    python -m loadtest.run [--users 20] [--spawn-rate 5] [--duration 60]
                           [--latency 1.5] [--jitter 0.5]

Starts the fake-provider app with uvicorn, runs Locust headless against it,
reads Locust's CSV stats, and records every setting next to the numbers.
"""

import argparse
import csv
import datetime as dt
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
RESULTS = HERE / "results"
PORT = 8765


def _wait_ready(url: str, timeout_s: float = 60) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"{url} not ready after {timeout_s}s")


def read_stats(csv_prefix: Path) -> dict[str, dict[str, float]]:
    rows: dict[str, dict[str, float]] = {}
    with open(f"{csv_prefix}_stats.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows[row["Name"]] = {
                "requests": int(row["Request Count"]),
                "failures": int(row["Failure Count"]),
                "p50_ms": float(row["50%"]),
                "p95_ms": float(row["95%"]),
                "p99_ms": float(row["99%"]),
                "mean_ms": float(row["Average Response Time"]),
                "rps": float(row["Requests/s"]),
            }
    return rows


def render(record: dict[str, Any]) -> str:
    s = record["settings"]
    lines = [
        f"# Load test {record['started_at'][:16]} UTC "
        f"(commit `{record['git_commit']}`)",
        "",
        f"{s['users']} users for {s['duration']} s; simulated model latency "
        f"{s['latency']} ± {s['jitter']} s per call. {record['note']}",
        "",
        "| Endpoint | Requests | Failures | p50 | p95 | p99 | Throughput |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, r in record["stats"].items():
        lines.append(
            f"| {name} | {r['requests']} | {r['failures']} | "
            f"{r['p50_ms'] / 1000:.2f} s | {r['p95_ms'] / 1000:.2f} s | "
            f"{r['p99_ms'] / 1000:.2f} s | {r['rps']:.2f} req/s |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m loadtest.run")
    parser.add_argument("--users", type=int, default=20)
    parser.add_argument("--spawn-rate", type=float, default=5)
    parser.add_argument("--duration", type=int, default=60, help="seconds")
    parser.add_argument("--latency", type=float, default=1.5, help="model latency, s")
    parser.add_argument("--jitter", type=float, default=0.5, help="+/- uniform, s")
    args = parser.parse_args(argv)

    env = os.environ | {
        "LOADTEST_MODEL_LATENCY_S": str(args.latency),
        "LOADTEST_JITTER_S": str(args.jitter),
        "LOG_LEVEL": "WARNING",
    }
    started = dt.datetime.now(dt.UTC)
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "loadtest.fake_app:app",
            "--port",
            str(PORT),
            "--log-level",
            "warning",
        ],
        cwd=BACKEND,
        env=env,
    )
    try:
        _wait_ready(f"http://127.0.0.1:{PORT}/healthz")
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp) / "locust"
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "locust",
                    "-f",
                    str(HERE / "locustfile.py"),
                    "--headless",
                    "--users",
                    str(args.users),
                    "--spawn-rate",
                    str(args.spawn_rate),
                    "--run-time",
                    f"{args.duration}s",
                    "--host",
                    f"http://127.0.0.1:{PORT}",
                    "--csv",
                    str(prefix),
                    "--only-summary",
                    "--loglevel",
                    "WARNING",
                ],
                cwd=BACKEND,
                check=False,
            )
            stats = read_stats(prefix)
    finally:
        server.terminate()
        server.wait(timeout=30)

    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        cwd=BACKEND,
        check=False,
    ).stdout.strip()
    record: dict[str, Any] = {
        "started_at": started.isoformat(),
        "git_commit": commit,
        "settings": vars(args),
        "machine": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpus": os.cpu_count(),
        },
        "note": "Model calls are simulated (sleep + canned output), so this "
        "measures service overhead and concurrency under model latency, not "
        "real model performance.",
        "stats": stats,
    }
    RESULTS.mkdir(exist_ok=True)
    stem = RESULTS / f"{started:%Y%m%dT%H%M%SZ}"
    stem.with_suffix(".json").write_text(json.dumps(record, indent=2) + "\n", "utf-8")
    stem.with_suffix(".md").write_text(render(record), "utf-8")
    print(render(record))
    return 0


if __name__ == "__main__":
    sys.exit(main())
