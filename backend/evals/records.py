"""What the runner records per case; the input to every metric."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from evals.schema import CostRange, ExpectedTriage, SeverityLevel, Tag, VehicleLabel

CaseStatus = Literal["assessed", "rejected", "error"]
TriageOutcome = Literal["accepted", "not_a_vehicle", "unusable", "unchecked"]


class CallRecord(BaseModel):
    task: str
    provider: str
    model: str
    ok: bool
    attempts: int
    invalid_outputs: int
    input_tokens: int
    output_tokens: int
    latency_s: float
    cached: bool
    error: str | None = None


class PredictedVehicle(BaseModel):
    make: str
    model: str
    year: int
    confidence: float


class CaseResult(BaseModel):
    case_id: str
    tags: list[Tag]
    status: CaseStatus
    error: str | None = None

    expected_triage: ExpectedTriage
    triage: TriageOutcome | None = None

    expected_vehicle: VehicleLabel | None = None
    predicted_vehicle: PredictedVehicle | None = None
    needed_confirmation: bool = False

    expected_damages: dict[str, SeverityLevel]
    predicted_damages: dict[str, float] = {}  # component -> model severity 0-1

    expected_cost: CostRange | None = None
    predicted_total: Decimal | None = None
    unpriced_components: list[str] = []
    report_status: Literal["complete", "partial"] | None = None

    calls: list[CallRecord] = []
    wall_s: float

    @property
    def assessable(self) -> bool:
        return self.expected_triage.shows_vehicle and self.expected_triage.usable
