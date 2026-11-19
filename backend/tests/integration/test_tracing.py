"""Spans per pipeline stage and per model call, correlated with logs (#16)."""

import json
import logging
from collections.abc import Iterator
from io import BytesIO

import pytest
from httpx import AsyncClient
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from PIL import Image
from pydantic import SecretStr

import app.core.llm as llm
from app.core.config import settings
from app.core.logging import JsonFormatter
from app.core.tracing import tracer
from tests.llm_fakes import SchemaClient

pytestmark = pytest.mark.real_triage

_EXPORTER = InMemorySpanExporter()


@pytest.fixture(scope="module", autouse=True)
def _sdk_provider() -> None:
    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
    provider.add_span_processor(SimpleSpanProcessor(_EXPORTER))


@pytest.fixture
def spans() -> Iterator[InMemorySpanExporter]:
    _EXPORTER.clear()
    yield _EXPORTER


def _red_jpeg() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (800, 600), color="red").save(buf, format="JPEG")
    return buf.getvalue()


def _ancestors(span: ReadableSpan, by_id: dict[int, ReadableSpan]) -> list[str]:
    names = []
    while span.parent is not None and span.parent.span_id in by_id:
        span = by_id[span.parent.span_id]
        names.append(span.name)
    return names


async def test_an_assessment_produces_one_trace_with_stage_and_model_spans(
    client: AsyncClient, spans: InMemorySpanExporter, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = SchemaClient()
    monkeypatch.setattr(settings, "openai_api_key", SecretStr(""))
    monkeypatch.setattr(llm, "get_client", lambda _p: fake)
    upload = await client.post(
        "/api/v1/upload", files=[("images", ("car.jpg", _red_jpeg(), "image/jpeg"))]
    )
    spans.clear()

    response = await client.post(
        "/api/v1/analyze", json={"upload_id": upload.json()["upload_id"]}
    )

    assert response.status_code == 200
    finished = spans.get_finished_spans()
    by_id = {s.context.span_id: s for s in finished}
    names = [s.name for s in finished]
    for stage in (
        "assess",
        "stage.triage",
        "stage.vehicle_id",
        "stage.damage_detection",
        "stage.pricing",
        "stage.pricing.component",
        "stage.sanity_check",
    ):
        assert stage in names, stage
    assert names.count("damage.zone") == 3
    assert len({s.context.trace_id for s in finished}) == 1  # one trace

    model_calls = [s for s in finished if s.name == "llm.call"]
    assert {s.attributes["app.llm.task"] for s in model_calls} >= {
        "image_triage",
        "vehicle_id",
        "damage_front",
        "sanity_check",
    }
    call = next(s for s in model_calls if s.attributes["app.llm.task"] == "vehicle_id")
    assert call.attributes["gen_ai.system"] == "gemini"
    assert call.attributes["gen_ai.request.model"] == "fake-model"
    assert call.attributes["gen_ai.usage.input_tokens"] == 500
    assert call.attributes["app.llm.attempts"] == 1
    assert call.attributes["app.prompt_version"] == settings.prompt_version
    assert "stage.vehicle_id" in _ancestors(call, by_id)
    assert "assess" in _ancestors(call, by_id)

    root = next(s for s in finished if s.name == "assess")
    assert root.attributes["app.result"] == "complete"
    assert root.attributes["app.llm_calls"] == len(model_calls)


def test_log_lines_inside_a_span_carry_its_trace_and_span_ids(
    spans: InMemorySpanExporter,
) -> None:
    with tracer.start_as_current_span("unit") as span:
        record = logging.LogRecord("app.t", logging.INFO, __file__, 1, "x", (), None)
        line = json.loads(JsonFormatter().format(record))

    ctx = span.get_span_context()
    assert line["trace_id"] == format(ctx.trace_id, "032x")
    assert line["span_id"] == format(ctx.span_id, "016x")
