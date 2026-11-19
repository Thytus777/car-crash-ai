"""OpenTelemetry tracing: one span per pipeline stage and per model call.

Tracing is always on through the OpenTelemetry API. Spans are exported only
when OTEL_EXPORTER_OTLP_ENDPOINT is set (docker-compose points it at the local
collector, which forwards to Jaeger); otherwise they cost almost nothing.
"""

import functools
from collections.abc import Awaitable, Callable

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app import __version__
from app.core.config import settings

tracer = trace.get_tracer("car-crash-ai")

# Span attribute names, following the OpenTelemetry GenAI conventions where
# they exist (gen_ai.*) and an app namespace otherwise.
GEN_AI_SYSTEM = "gen_ai.system"
GEN_AI_MODEL = "gen_ai.request.model"
GEN_AI_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"


def traced[**P, R](
    name: str,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Run an async function inside a span; exceptions are recorded on it."""

    def decorate(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @functools.wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            with tracer.start_as_current_span(name):
                return await fn(*args, **kwargs)

        return wrapper

    return decorate


def configure_tracing(app: FastAPI) -> None:
    """Install an exporting provider if an OTLP endpoint is configured."""
    endpoint = settings.otel_exporter_otlp_endpoint
    if endpoint:
        provider = TracerProvider(
            resource=Resource.create(
                {"service.name": "car-crash-ai", "service.version": __version__}
            )
        )
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"))
        )
        trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,readyz,health")


def current_trace_ids() -> tuple[str, str] | None:
    """(trace_id, span_id) as hex for log correlation, if a span is active."""
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return None
    return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")
