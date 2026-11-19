"""Eval command line: ``python -m evals <command>`` (run from backend/).

validate                       check labels, images and the manifest
run [--smoke] [--case ID ...]  run the pipeline on the dataset, write results
compare BASE.json CANDIDATE.json   diff two runs against evals/thresholds.yaml
"""

import argparse
import asyncio
import datetime as dt
import sys
from pathlib import Path

from app.core.config import settings
from app.core.llm import CompletionCache, use_completion_cache
from evals import dataset, metrics, results, runner
from evals.pricing import load_pricing
from evals.records import CaseResult

CACHE_ROOT = dataset.EVALS_ROOT / ".cache"


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

    started = dt.datetime.now(dt.UTC)
    cache = CompletionCache(CACHE_ROOT)

    async def go() -> list[CaseResult]:
        if args.no_cache:
            return await runner.run(runnable, args.concurrency)
        with use_completion_cache(cache):
            return await runner.run(runnable, args.concurrency)

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
                cases_skipped_unavailable=len(cases) - len(runnable),
            ),
            prompt_version=settings.prompt_version,
            ai_provider=settings.ai_provider,
            models=models,
            cache=results.CacheInfo(
                enabled=not args.no_cache, hits=cache.hits, misses=cache.misses
            ),
            concurrency=args.concurrency,
        ),
        metrics=metrics.compute(case_results, load_pricing()),
        cases=case_results,
    )
    path = results.write_run(run, Path(args.output_dir))
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

    args = parser.parse_args(argv)
    handlers = {"validate": _validate, "run": _run, "compare": _compare}
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
