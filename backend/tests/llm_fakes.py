"""Test doubles for the LLM layer (app.core.llm)."""

from collections.abc import Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel

from app.core.llm import Completion, ImageDetail, LLMCall, LLMResult, Provider, Usage


def llm_result[T: BaseModel](output: T, task: str = "test") -> LLMResult[T]:
    """Wrap a parsed output the way generate() returns it."""
    call = LLMCall(
        task=task,
        provider="gemini",
        model="fake-model",
        ok=True,
        attempts=1,
        invalid_outputs=0,
        usage=Usage(10, 5),
        latency_s=0.01,
    )
    return LLMResult(output=output, call=call)


@dataclass
class ScriptedClient:
    """ProviderClient that replays a script of replies or exceptions."""

    provider: Provider
    script: list[str | BaseException]
    usage: Usage = field(default_factory=lambda: Usage(100, 20))
    requests: list[dict[str, object]] = field(default_factory=list)

    def model_for(self, *, vision: bool) -> str:
        return f"{self.provider}-{'vision' if vision else 'text'}"

    async def complete(
        self,
        *,
        schema: type[BaseModel],
        prompt: str,
        images: Sequence[bytes],
        max_output_tokens: int,
        temperature: float,
        image_detail: ImageDetail,
    ) -> Completion:
        self.requests.append(
            {"schema": schema, "prompt": prompt, "images": list(images)}
        )
        step = self.script.pop(0)
        if isinstance(step, BaseException):
            raise step
        return Completion(
            text=step, usage=self.usage, model=self.model_for(vision=bool(images))
        )
