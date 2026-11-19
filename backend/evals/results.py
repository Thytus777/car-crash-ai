"""Eval run files (evals/results/*.json + .md) and run-to-run comparison."""

import datetime as dt
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from evals.dataset import EVALS_ROOT
from evals.metrics import Metrics
from evals.records import CaseResult

RESULTS_ROOT = EVALS_ROOT / "results"
THRESHOLDS_PATH = EVALS_ROOT / "thresholds.yaml"


class DatasetInfo(BaseModel):
    version: str
    fingerprint: str
    cases_run: int
    cases_skipped_unavailable: int


class CacheInfo(BaseModel):
    enabled: bool
    hits: int = 0
    misses: int = 0


class RunInfo(BaseModel):
    started_at: dt.datetime
    git_commit: str
    git_dirty: bool
    subset: Literal["full", "smoke", "custom"]
    dataset: DatasetInfo
    prompt_version: str
    ai_provider: str
    models: list[str]
    cache: CacheInfo
    concurrency: int


class EvalRun(BaseModel):
    run: RunInfo
    metrics: Metrics
    cases: list[CaseResult]


def git_state() -> tuple[str, bool]:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, check=False, cwd=EVALS_ROOT
        ).stdout.strip()

    return git("rev-parse", "--short", "HEAD") or "unknown", bool(
        git("status", "--porcelain")
    )


def write_run(run: EvalRun, out_dir: Path = RESULTS_ROOT) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    model = re.sub(
        r"[^A-Za-z0-9.-]+", "-", run.run.models[0] if run.run.models else "none"
    )
    stem = f"{run.run.started_at:%Y%m%dT%H%M%SZ}_{run.run.prompt_version}_{model}"
    path = out_dir / f"{stem}.json"
    path.write_text(run.model_dump_json(indent=2) + "\n", "utf-8")
    path.with_suffix(".md").write_text(render_markdown(run), "utf-8")
    return path


def load_run(path: Path) -> EvalRun:
    return EvalRun.model_validate_json(path.read_text("utf-8"))


# --- Headline metrics -------------------------------------------------------

Getter = Callable[[Metrics], float | None]

HEADLINE: dict[str, tuple[str, Getter]] = {
    "component_f1": ("Component F1", lambda m: m.detection.overall.f1),
    "component_precision": (
        "Component precision",
        lambda m: m.detection.overall.precision,
    ),
    "component_recall": ("Component recall", lambda m: m.detection.overall.recall),
    "severity_exact": ("Severity exact", lambda m: m.severity.exact),
    "severity_within_one": (
        "Severity within one level",
        lambda m: m.severity.within_one,
    ),
    "triage_accuracy": ("Triage accuracy", lambda m: m.triage.accuracy),
    "vehicle_accuracy": ("Vehicle make+model", lambda m: m.vehicle.make_model_accuracy),
    "cost_within_range": ("Cost within reference range", lambda m: m.cost.within_range),
    "cost_mae_usd": ("Cost MAE (USD)", lambda m: m.cost.mae),
    "schema_valid_first_attempt": (
        "Schema-valid first attempt",
        lambda m: m.reliability.schema_valid_first_attempt,
    ),
    "retry_rate": ("Retry rate", lambda m: m.reliability.retry_rate),
    "call_failure_rate": (
        "Model call failure rate",
        lambda m: m.reliability.call_failure_rate,
    ),
    "case_error_rate": ("Case error rate", lambda m: m.reliability.case_error_rate),
    "latency_p50_s": ("Latency p50 (s)", lambda m: m.latency.p50_s),
    "latency_p95_s": ("Latency p95 (s)", lambda m: m.latency.p95_s),
    "cost_per_request_usd": (
        "Cost per request (USD)",
        lambda m: m.spend.per_request_usd,
    ),
}

_RATES = {k for k in HEADLINE if not k.endswith(("_s", "_usd")) and k != "cost_mae_usd"}


def fmt(key: str, value: float | None) -> str:
    if value is None:
        return "n/a"
    if key in _RATES:
        return f"{value:.1%}"
    if key == "cost_per_request_usd":
        return f"${value:.4f}"
    return f"{value:,.2f}"


def render_markdown(run: EvalRun) -> str:
    info, m = run.run, run.metrics
    lines = [
        f"# Eval run {info.started_at:%Y-%m-%d %H:%M} UTC",
        "",
        f"- Commit `{info.git_commit}`"
        + (" (uncommitted changes)" if info.git_dirty else ""),
        f"- Dataset v{info.dataset.version} (`{info.dataset.fingerprint}`), "
        f"{info.subset}: {info.dataset.cases_run} cases"
        + (
            f", {info.dataset.cases_skipped_unavailable} skipped "
            "(images not on this machine)"
            if info.dataset.cases_skipped_unavailable
            else ""
        ),
        f"- Prompt `{info.prompt_version}`; models: {', '.join(info.models) or 'none'}",
        f"- Cache: {'on' if info.cache.enabled else 'off'}"
        + (
            f" ({info.cache.hits} hits, {info.cache.misses} misses)"
            if info.cache.enabled
            else ""
        ),
        "",
        "| Metric | Value |",
        "|---|---|",
    ]
    lines += [f"| {label} | {fmt(k, get(m))} |" for k, (label, get) in HEADLINE.items()]
    if m.spend.unpriced_models:
        lines += [
            "",
            "Unpriced models (add to evals/pricing.yaml): "
            + ", ".join(m.spend.unpriced_models),
        ]
    if m.by_tag:
        lines += [
            "",
            "| Tag | Cases | Component F1 | Triage accuracy |",
            "|---|---|---|---|",
        ]
        lines += [
            f"| {tag} | {s.n} | {fmt('component_f1', s.component_f1)} | "
            f"{fmt('triage_accuracy', s.triage_accuracy)} |"
            for tag, s in m.by_tag.items()
        ]
    errors = [c for c in run.cases if c.status == "error"]
    if errors:
        lines += ["", "Errors:"] + [f"- `{c.case_id}`: {c.error}" for c in errors]
    return "\n".join(lines) + "\n"


# --- Comparison -------------------------------------------------------------


class Thresholds(BaseModel):
    max_drop: dict[str, float] = {}
    max_rise: dict[str, float] = {}
    max_increase_pct: dict[str, float] = {}


def load_thresholds(path: Path = THRESHOLDS_PATH) -> Thresholds:
    return Thresholds.model_validate(yaml.safe_load(path.read_text("utf-8")) or {})


class Row(BaseModel):
    key: str
    label: str
    base: float | None
    candidate: float | None
    regressed: bool | None  # None: not gated or not measurable


class Comparison(BaseModel):
    rows: list[Row]
    dataset_mismatch: bool

    @property
    def regressions(self) -> list[Row]:
        return [r for r in self.rows if r.regressed]


def compare(base: EvalRun, candidate: EvalRun, thresholds: Thresholds) -> Comparison:
    rows = []
    for key, (label, get) in HEADLINE.items():
        b, c = get(base.metrics), get(candidate.metrics)
        regressed: bool | None = None
        if b is not None and c is not None:
            if key in thresholds.max_drop:
                regressed = b - c > thresholds.max_drop[key]
            elif key in thresholds.max_rise:
                regressed = c - b > thresholds.max_rise[key]
            elif key in thresholds.max_increase_pct:
                allowed = abs(b) * thresholds.max_increase_pct[key] / 100
                regressed = c - b > allowed
        rows.append(Row(key=key, label=label, base=b, candidate=c, regressed=regressed))
    return Comparison(
        rows=rows,
        dataset_mismatch=base.run.dataset.fingerprint
        != candidate.run.dataset.fingerprint,
    )


def render_comparison(cmp: Comparison, base_name: str, candidate_name: str) -> str:
    lines = [
        f"| Metric | Baseline (`{base_name}`) "
        f"| Candidate (`{candidate_name}`) | Δ | Gate |",
        "|---|---|---|---|---|",
    ]
    for r in cmp.rows:
        delta = (
            "n/a"
            if r.base is None or r.candidate is None
            else (
                f"{r.candidate - r.base:+.1%}"
                if r.key in _RATES
                else f"{r.candidate - r.base:+,.4f}"
            )
        )
        gate = {True: "❌ regressed", False: "✅", None: "–"}[r.regressed]
        lines.append(
            f"| {r.label} | {fmt(r.key, r.base)} | "
            f"{fmt(r.key, r.candidate)} | {delta} | {gate} |"
        )
    if cmp.dataset_mismatch:
        lines += [
            "",
            "⚠️ The runs used different dataset versions; "
            "deltas mix label changes with model changes.",
        ]
    return "\n".join(lines) + "\n"
