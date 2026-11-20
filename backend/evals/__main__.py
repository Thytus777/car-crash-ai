"""Eval command line: ``python -m evals <command>`` (run from backend/).

validate                       check labels, images and the manifest
run [--smoke] [--case ID ...]  run the pipeline on the dataset, write results
compare BASE.json CANDIDATE.json   diff two runs against evals/thresholds.yaml
gate --baseline B --comment C  CI: smoke run vs a committed baseline, as a PR comment
"""

import argparse
import asyncio
import datetime as dt
import sys
from pathlib import Path

from app.core.config import settings
from app.core.llm import CompletionCache, _api_key, use_completion_cache
from evals import dataset, metrics, results, runner
from evals.dataset import Case
from evals.pricing import load_pricing
from evals.records import CaseResult

CACHE_ROOT = dataset.EVALS_ROOT / ".cache"
BASELINE_PATH = dataset.EVALS_ROOT / "baselines" / "smoke.json"
BASELINE_REL = "evals/baselines/smoke.json"
GATE_MARKER = "<!-- eval-gate -->"


def _validate(_: argparse.Namespace) -> int:
    report = dataset.validate()
    for warning in report.warnings:
        print(f"warning: {warning}")
    for error in report.errors:
        print(f"error: {error}")
    if report.ok:
        print(f"dataset OK: {dataset.dumps(dataset.summary())}")
        return 0
    print(f"{len(report.errors)} error(s)")
    return 1


def _execute(
    runnable: list[Case],
    selected: int,
    subset: str,
    concurrency: int,
    no_cache: bool,
    output_dir: Path,
) -> tuple[results.EvalRun, Path]:
    """Run the pipeline over ``runnable`` and write the result files."""
    manifest = dataset.load_manifest()
    started = dt.datetime.now(dt.UTC)
    cache = CompletionCache(CACHE_ROOT)

    async def go() -> list[CaseResult]:
        if no_cache:
            return await runner.run(runnable, concurrency)
        with use_completion_cache(cache):
            return await runner.run(runnable, concurrency)

    case_results = asyncio.run(go())
    commit, dirty = results.git_state()
    models = sorted(
        {f"{c.provider}/{c.model}" for r in case_results for c in r.calls if c.ok}
    )
    run = results.EvalRun(
        run=results.RunInfo(
            started_at=started,
            git_commit=commit,
            git_dirty=dirty,
            subset=subset,  # type: ignore[arg-type]
            dataset=results.DatasetInfo(
                version=manifest.version,
                fingerprint=dataset.fingerprint(),
                cases_run=len(runnable),
                cases_skipped_unavailable=selected - len(runnable),
            ),
            prompt_version=settings.prompt_version,
            ai_provider=settings.ai_provider,
            models=models,
            cache=results.CacheInfo(
                enabled=not no_cache, hits=cache.hits, misses=cache.misses
            ),
            concurrency=concurrency,
        ),
        metrics=metrics.compute(case_results, load_pricing()),
        cases=case_results,
    )
    return run, results.write_run(run, output_dir)


def _run(args: argparse.Namespace) -> int:
    report = dataset.validate()
    if not report.ok:
        print("dataset is invalid; run `make eval-validate`")
        return 1
    manifest = dataset.load_manifest()
    cases = dataset.load_cases()
    if args.case:
        cases = [c for c in cases if c.case_id in set(args.case)]
        subset = "custom"
    elif args.smoke:
        cases = [c for c in cases if c.case_id in set(manifest.smoke)]
        subset = "smoke"
    else:
        subset = "full"
    runnable = [c for c in cases if c.available()]
    if not runnable:
        print(f"no runnable cases ({len(cases)} selected, none with images here)")
        return 1

    run, path = _execute(
        runnable,
        len(cases),
        subset,
        args.concurrency,
        args.no_cache,
        Path(args.output_dir),
    )
    print(results.render_markdown(run))
    print(f"wrote {path} (+ .md)")
    return 0


def _compare(args: argparse.Namespace) -> int:
    base, candidate = results.load_run(args.base), results.load_run(args.candidate)
    cmp = results.compare(base, candidate, results.load_thresholds(args.thresholds))
    print(results.render_comparison(cmp, args.base.stem, args.candidate.stem))
    if cmp.regressions:
        print(f"{len(cmp.regressions)} metric(s) regressed past evals/thresholds.yaml")
        return 1
    return 0


def _gate(args: argparse.Namespace) -> int:
    """Smoke-run the pipeline and compare it with the committed baseline.

    Writes a Markdown PR comment and fails only on a regression. Every way
    the gate can't run says so in the comment, so a skip never reads as a
    pass.
    """

    def comment(title: str, body: str) -> None:
        text = f"{GATE_MARKER}\n### Eval gate: {title}\n\n{body}\n"
        Path(args.comment).write_text(text, encoding="utf-8")
        print(text)

    if not any(_api_key(p) for p in ("gemini", "openai")):
        comment(
            "Skipped",
            "There's no model API key: the `EVAL_GEMINI_API_KEY` secret isn't "
            "set, or this PR comes from a fork.",
        )
        return 0
    report = dataset.validate()
    if not report.ok:
        comment("Failed", "The dataset is invalid; run `make eval-validate`.")
        return 1
    smoke = set(dataset.load_manifest().smoke)
    cases = [c for c in dataset.load_cases() if c.case_id in smoke]
    runnable = [c for c in cases if c.available()]
    if not runnable:
        comment(
            "Skipped",
            f"There are no runnable smoke cases ({len(cases)} listed in the "
            "manifest with images in git). Label some and list them under "
            "`smoke` in `evals/dataset/manifest.json` (see `evals/LABELLING.md`).",
        )
        return 0

    run, path = _execute(
        runnable, len(cases), "smoke", args.concurrency, False, Path(args.output_dir)
    )
    summary = results.render_markdown(run)
    baseline = Path(args.baseline)
    if not baseline.exists():
        comment(
            "No baseline",
            "Nothing to compare against yet. If these numbers are right, adopt "
            f"them by committing this run as `{BASELINE_REL}` "
            f"(the `eval-smoke` artifact has `{path.name}`).\n\n{summary}",
        )
        return 0

    cmp = results.compare(
        results.load_run(baseline), run, results.load_thresholds(args.thresholds)
    )
    table = results.render_comparison(cmp, "baseline", "this PR")
    if cmp.regressions:
        comment(
            "Regressed",
            f"{len(cmp.regressions)} metric(s) fell past `evals/thresholds.yaml`. "
            "If the change is intended, update the baseline in this PR and say "
            f"why.\n\n{table}",
        )
        return 1
    comment("Passed", table)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate", help="check labels, images and the manifest")

    run = commands.add_parser("run", help="run the pipeline over the dataset")
    run.add_argument(
        "--smoke", action="store_true", help="only the manifest's smoke cases"
    )
    run.add_argument("--case", action="append", help="run only this case (repeatable)")
    run.add_argument("--concurrency", type=int, default=4)
    run.add_argument("--no-cache", action="store_true", help="always call the models")
    run.add_argument("--output-dir", default=str(results.RESULTS_ROOT))

    cmp = commands.add_parser("compare", help="compare two result files")
    cmp.add_argument("base", type=Path)
    cmp.add_argument("candidate", type=Path)
    cmp.add_argument("--thresholds", type=Path, default=results.THRESHOLDS_PATH)

    gate = commands.add_parser("gate", help="CI: smoke run vs the committed baseline")
    gate.add_argument("--baseline", type=Path, default=BASELINE_PATH)
    gate.add_argument("--comment", type=Path, required=True, help="Markdown output")
    gate.add_argument("--thresholds", type=Path, default=results.THRESHOLDS_PATH)
    gate.add_argument("--concurrency", type=int, default=4)
    gate.add_argument("--output-dir", default=str(results.RESULTS_ROOT))

    args = parser.parse_args(argv)
    handlers = {
        "validate": _validate,
        "run": _run,
        "compare": _compare,
        "gate": _gate,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
