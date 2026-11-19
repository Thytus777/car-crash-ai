"""Run the production assessment pipeline over labelled cases."""

import asyncio
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path

from app.core.config import settings
from app.core.errors import AppError, NotAVehicleError, UnusableImagesError
from app.core.llm import LLMCall, record_llm_calls
from app.models.estimate import AssessmentReport, VehicleConfirmNeeded
from app.services.assessment import AssessmentRequest, assess
from app.services.image_proc import process_upload
from evals.dataset import Case
from evals.records import CallRecord, CaseResult, PredictedVehicle, TriageOutcome


def _call_record(call: LLMCall) -> CallRecord:
    return CallRecord(
        task=call.task,
        provider=call.provider,
        model=call.model,
        ok=call.ok,
        attempts=call.attempts,
        invalid_outputs=call.invalid_outputs,
        input_tokens=call.usage.input_tokens,
        output_tokens=call.usage.output_tokens,
        latency_s=call.latency_s,
        cached=call.cached,
        error=call.error,
    )


def _confirmed_request(
    case: Case, upload_id: str, guess: VehicleConfirmNeeded
) -> AssessmentRequest | None:
    """What a user would confirm: the labelled vehicle if known, else the guess."""
    label = case.label.vehicle
    if label and label.year:
        return AssessmentRequest(upload_id, label.make, label.model, label.year)
    g = guess.vehicle_guess
    if g.year:
        return AssessmentRequest(upload_id, g.make, g.model, g.year)
    return None


async def run_case(case: Case) -> CaseResult:
    label = case.label
    result = CaseResult(
        case_id=label.case_id,
        tags=label.tags,
        status="error",
        expected_triage=label.triage,
        expected_vehicle=label.vehicle,
        expected_damages={d.component: d.severity for d in label.damages},
        expected_cost=label.cost,
        wall_s=0.0,
    )
    started = time.perf_counter()
    with record_llm_calls() as calls:
        try:
            files = [(name, data, "") for name, data in case.read_images()]
            upload_id, _, _ = await process_upload(files)
            outcome = await assess(AssessmentRequest(upload_id))
            if isinstance(outcome, VehicleConfirmNeeded):
                result.needed_confirmation = True
                result.predicted_vehicle = PredictedVehicle(
                    **outcome.vehicle_guess.model_dump(
                        include={"make", "model", "year", "confidence"}
                    )
                )
                confirmed = _confirmed_request(case, upload_id, outcome)
                if confirmed is None:
                    raise RuntimeError(
                        "vehicle needs confirmation and no year is known"
                    )
                outcome = await assess(confirmed)
            assert isinstance(outcome, AssessmentReport)
            _record_report(result, outcome)
        except NotAVehicleError:
            result.status, result.triage = "rejected", "not_a_vehicle"
        except UnusableImagesError:
            result.status, result.triage = "rejected", "unusable"
        except AppError as exc:
            result.error = exc.slug
        except Exception as exc:  # one broken case must not abort the run
            result.error = f"{type(exc).__name__}: {exc}"
    result.calls = [_call_record(c) for c in calls]
    result.wall_s = time.perf_counter() - started
    return result


def _record_report(result: CaseResult, report: AssessmentReport) -> None:
    triaged: TriageOutcome = (
        "unchecked"
        if any(i.stage == "image_triage" for i in report.issues)
        else "accepted"
    )
    result.status = "assessed"
    result.triage = triaged
    if result.predicted_vehicle is None:
        result.predicted_vehicle = PredictedVehicle(
            **report.vehicle.model_dump(include={"make", "model", "year", "confidence"})
        )
    result.predicted_damages = {
        d.component: d.severity for d in report.damage_assessment.damages
    }
    result.predicted_total = report.totals.grand_total
    result.unpriced_components = report.totals.unpriced_components
    result.report_status = report.status


async def run(cases: Sequence[Case], concurrency: int = 4) -> list[CaseResult]:
    """Run cases concurrently with uploads in a throwaway directory."""
    limit = asyncio.Semaphore(concurrency)
    original_upload_dir = settings.upload_dir

    async def bounded(case: Case) -> CaseResult:
        async with limit:
            return await run_case(case)

    original_result_cache = settings.result_cache_enabled
    with tempfile.TemporaryDirectory(prefix="car-crash-eval-") as tmp:
        settings.upload_dir = Path(tmp)
        # Every case must run the pipeline. Replays come from the LLM-level
        # CompletionCache, which keeps per-call latency and tokens.
        settings.result_cache_enabled = False
        try:
            return list(await asyncio.gather(*(bounded(c) for c in cases)))
        finally:
            settings.upload_dir = original_upload_dir
            settings.result_cache_enabled = original_result_cache
