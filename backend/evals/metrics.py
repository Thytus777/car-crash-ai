"""Eval metrics, computed only from CaseResults (pure; no I/O, no model calls).

A metric is None, never 0, when there is nothing to measure it on, e.g. cost
MAE with no cost-labelled cases. That keeps reports honest on small datasets.
"""

import statistics
from collections import defaultdict
from collections.abc import Iterable, Sequence
from decimal import Decimal
from typing import get_args

from pydantic import BaseModel

from evals.pricing import Pricing
from evals.records import CaseResult
from evals.schema import SeverityLevel, severity_level

_LEVELS: tuple[SeverityLevel, ...] = get_args(SeverityLevel)
ESTIMATE_CURRENCY = "USD"  # the prompts price parts in USD


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


class PRF(BaseModel):
    tp: int
    fp: int
    fn: int
    precision: float | None
    recall: float | None
    f1: float | None

    @classmethod
    def of(cls, tp: int, fp: int, fn: int) -> "PRF":
        precision = _ratio(tp, tp + fp)
        recall = _ratio(tp, tp + fn)
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision is not None and recall is not None and precision + recall
            else (0.0 if tp + fp + fn else None)
        )
        return cls(tp=tp, fp=fp, fn=fn, precision=precision, recall=recall, f1=f1)


class Detection(BaseModel):
    overall: PRF  # micro-averaged over components
    per_component: dict[str, PRF]
    cases: int


class Severity(BaseModel):
    exact: float | None  # predicted level == labelled level (true positives)
    within_one: float | None
    n: int


class Triage(BaseModel):
    accuracy: float | None  # accept/reject decision matches the label
    reject_recall: float | None  # of cases that should be rejected, share rejected
    false_reject_rate: float | None  # of assessable cases, share wrongly rejected
    unchecked: int  # triage couldn't run
    n: int


class Vehicle(BaseModel):
    make_model_accuracy: float | None
    confirmation_rate: float | None
    n: int


class Cost(BaseModel):
    mae: float | None  # vs the midpoint of the labelled range, in USD
    within_range: float | None
    n: int
    skipped_other_currency: int
    by_basis: dict[str, "Cost"] = {}


class Reliability(BaseModel):
    calls: int
    schema_valid_first_attempt: float | None
    retry_rate: float | None  # calls needing more than one attempt
    call_failure_rate: float | None
    case_error_rate: float | None
    partial_report_rate: float | None


class Latency(BaseModel):
    p50_s: float | None
    p95_s: float | None
    n: int
    cached_fraction: float | None  # calls served from the eval cache


class Spend(BaseModel):
    per_request_usd: float | None  # None until every model used is priced
    input_tokens_per_request: float | None
    output_tokens_per_request: float | None
    unpriced_models: list[str]


class TagSlice(BaseModel):
    n: int
    component_f1: float | None
    triage_accuracy: float | None


class Metrics(BaseModel):
    cases: int
    detection: Detection
    severity: Severity
    triage: Triage
    vehicle: Vehicle
    cost: Cost
    reliability: Reliability
    latency: Latency
    spend: Spend
    by_tag: dict[str, TagSlice]


def detection(cases: Sequence[CaseResult]) -> Detection:
    scored = [c for c in cases if c.assessable and c.status == "assessed"]
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for case in scored:
        expected, predicted = set(case.expected_damages), set(case.predicted_damages)
        for comp in expected & predicted:
            counts[comp][0] += 1
        for comp in predicted - expected:
            counts[comp][1] += 1
        for comp in expected - predicted:
            counts[comp][2] += 1
    totals = [sum(v[i] for v in counts.values()) for i in range(3)]
    return Detection(
        overall=PRF.of(*totals),
        per_component={k: PRF.of(*v) for k, v in sorted(counts.items())},
        cases=len(scored),
    )


def severity(cases: Sequence[CaseResult]) -> Severity:
    exact = within_one = n = 0
    for case in cases:
        if case.status != "assessed":
            continue
        for comp, label in case.expected_damages.items():
            if comp not in case.predicted_damages:
                continue
            predicted = severity_level(case.predicted_damages[comp])
            gap = abs(_LEVELS.index(predicted) - _LEVELS.index(label))
            n += 1
            exact += gap == 0
            within_one += gap <= 1
    return Severity(exact=_ratio(exact, n), within_one=_ratio(within_one, n), n=n)


def triage(cases: Sequence[CaseResult]) -> Triage:
    decided = [
        c for c in cases if c.triage in ("accepted", "not_a_vehicle", "unusable")
    ]
    correct = sum((c.triage == "accepted") == c.assessable for c in decided)
    should_reject = [c for c in decided if not c.assessable]
    should_accept = [c for c in decided if c.assessable]
    return Triage(
        accuracy=_ratio(correct, len(decided)),
        reject_recall=_ratio(
            sum(c.triage != "accepted" for c in should_reject), len(should_reject)
        ),
        false_reject_rate=_ratio(
            sum(c.triage != "accepted" for c in should_accept), len(should_accept)
        ),
        unchecked=sum(c.triage == "unchecked" for c in cases),
        n=len(decided),
    )


def vehicle(cases: Sequence[CaseResult]) -> Vehicle:
    pairs = [
        (c.expected_vehicle, c.predicted_vehicle)
        for c in cases
        if c.expected_vehicle and c.predicted_vehicle
    ]
    matches = sum(
        e.make.casefold() == p.make.casefold()
        and e.model.casefold() == p.model.casefold()
        for e, p in pairs
        if e and p
    )
    identified = [c for c in cases if c.predicted_vehicle]
    return Vehicle(
        make_model_accuracy=_ratio(matches, len(pairs)),
        confirmation_rate=_ratio(
            sum(c.needed_confirmation for c in identified), len(identified)
        ),
        n=len(pairs),
    )


def _cost(cases: Iterable[CaseResult]) -> Cost:
    errors: list[float] = []
    inside = skipped = 0
    for case in cases:
        label, total = case.expected_cost, case.predicted_total
        if label is None or total is None or case.status != "assessed":
            continue
        if label.currency != ESTIMATE_CURRENCY:
            skipped += 1
            continue
        midpoint = (label.low + label.high) / 2
        errors.append(float(abs(total - midpoint)))
        inside += label.low <= total <= label.high
    return Cost(
        mae=statistics.fmean(errors) if errors else None,
        within_range=_ratio(inside, len(errors)),
        n=len(errors),
        skipped_other_currency=skipped,
    )


def cost(cases: Sequence[CaseResult]) -> Cost:
    overall = _cost(cases)
    bases = sorted({c.expected_cost.basis for c in cases if c.expected_cost})
    overall.by_basis = {
        b: _cost(c for c in cases if c.expected_cost and c.expected_cost.basis == b)
        for b in bases
    }
    return overall


def reliability(cases: Sequence[CaseResult]) -> Reliability:
    calls = [call for c in cases for call in c.calls]
    assessed = [c for c in cases if c.status == "assessed"]
    return Reliability(
        calls=len(calls),
        schema_valid_first_attempt=_ratio(
            sum(c.ok and c.attempts == 1 and c.invalid_outputs == 0 for c in calls),
            len(calls),
        ),
        retry_rate=_ratio(sum(c.attempts > 1 for c in calls), len(calls)),
        call_failure_rate=_ratio(sum(not c.ok for c in calls), len(calls)),
        case_error_rate=_ratio(sum(c.status == "error" for c in cases), len(cases)),
        partial_report_rate=_ratio(
            sum(c.report_status == "partial" for c in assessed), len(assessed)
        ),
    )


def percentile(values: Sequence[float], pct: float) -> float | None:
    """Linear-interpolated percentile; None for no data."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * pct / 100
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def latency(cases: Sequence[CaseResult]) -> Latency:
    finished = [c for c in cases if c.status != "error"]
    calls = [call for c in cases for call in c.calls]
    # Model time per case: the cache replays recorded latencies, so this stays
    # meaningful on cached runs (unlike wall-clock time).
    per_case = [sum(call.latency_s for call in c.calls) for c in finished]
    return Latency(
        p50_s=percentile(per_case, 50),
        p95_s=percentile(per_case, 95),
        n=len(per_case),
        cached_fraction=_ratio(sum(c.cached for c in calls), len(calls)),
    )


def spend(cases: Sequence[CaseResult], pricing: Pricing) -> Spend:
    if not cases:
        return Spend(
            per_request_usd=None,
            input_tokens_per_request=None,
            output_tokens_per_request=None,
            unpriced_models=[],
        )
    calls = [call for c in cases for call in c.calls]
    unpriced = sorted({f"{c.provider}/{c.model}" for c in calls} - set(pricing.models))
    total = Decimal("0")
    for call in calls:
        price = pricing.models.get(f"{call.provider}/{call.model}")
        if price:
            total += price.cost(call.input_tokens, call.output_tokens)
    return Spend(
        per_request_usd=None if unpriced else float(total) / len(cases),
        input_tokens_per_request=sum(c.input_tokens for c in calls) / len(cases),
        output_tokens_per_request=sum(c.output_tokens for c in calls) / len(cases),
        unpriced_models=unpriced,
    )


def by_tag(cases: Sequence[CaseResult]) -> dict[str, TagSlice]:
    tags = sorted({t for c in cases for t in c.tags})
    slices: dict[str, TagSlice] = {}
    for tag in tags:
        subset = [c for c in cases if tag in c.tags]
        slices[tag] = TagSlice(
            n=len(subset),
            component_f1=detection(subset).overall.f1,
            triage_accuracy=triage(subset).accuracy,
        )
    return slices


def compute(cases: Sequence[CaseResult], pricing: Pricing) -> Metrics:
    return Metrics(
        cases=len(cases),
        detection=detection(cases),
        severity=severity(cases),
        triage=triage(cases),
        vehicle=vehicle(cases),
        cost=cost(cases),
        reliability=reliability(cases),
        latency=latency(cases),
        spend=spend(cases, pricing),
        by_tag=by_tag(cases),
    )
