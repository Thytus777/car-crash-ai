from app.core.llm import LLMCall, Usage
from app.models.estimate import AssessmentMeta


def _call(provider: str, ok: bool, attempts: int, usage: Usage) -> LLMCall:
    return LLMCall(
        task="t",
        provider=provider,  # type: ignore[arg-type]
        model=f"{provider}-model",
        ok=ok,
        attempts=attempts,
        invalid_outputs=0,
        usage=usage,
        latency_s=0.1,
    )


def test_meta_summarises_calls_including_failed_attempts() -> None:
    calls = [
        _call("gemini", False, 3, Usage(0, 0)),
        _call("openai", True, 1, Usage(100, 20)),
        _call("openai", True, 2, Usage(200, 40)),
    ]

    meta = AssessmentMeta.from_calls("v1", calls)

    assert meta.prompt_version == "v1"
    assert meta.models == ["openai/openai-model"]  # only models that answered
    assert meta.llm_calls == 6
    assert (meta.input_tokens, meta.output_tokens) == (300, 60)
