"""Test doubles for the LLM layer (app.core.llm)."""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from io import BytesIO

from PIL import Image
from pydantic import BaseModel

from app.core.llm import Completion, ImageDetail, LLMCall, LLMResult, Provider, Usage
from app.models.llm_outputs import (
    DamageFindings,
    ImageTriage,
    PriceEstimate,
    SanityReview,
    VehicleIdentification,
)


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

    def model_for(self, *, vision: bool, tier: str = "strong") -> str:
        kind = "vision" if vision else "text"
        return f"{self.provider}-{kind}" + ("-fast" if tier == "fast" else "")

    async def complete(
        self,
        *,
        schema: type[BaseModel],
        prompt: str,
        images: Sequence[bytes],
        max_output_tokens: int,
        temperature: float,
        image_detail: ImageDetail,
        tier: str = "strong",
    ) -> Completion:
        self.requests.append(
            {"schema": schema, "prompt": prompt, "images": list(images), "tier": tier}
        )
        step = self.script.pop(0)
        if isinstance(step, BaseException):
            raise step
        return Completion(
            text=step,
            usage=self.usage,
            model=self.model_for(vision=bool(images), tier=tier),
        )


FAKE_REPLIES: dict[type[BaseModel], str] = {
    VehicleIdentification: json.dumps(
        {
            "make": "Toyota",
            "model": "Camry",
            "year": 2020,
            "body_style": "sedan",
            "color": "grey",
            "confidence": 0.95,
        }
    ),
    SanityReview: json.dumps({"looks_reasonable": True, "warnings": []}),
    PriceEstimate: json.dumps(
        {"price_low": 100, "price_avg": 200, "price_high": 300, "confidence": 0.5}
    ),
}


class SchemaClient:
    """Fake provider: a fixed reply per schema; triage rejects grey-on-grey."""

    provider = "gemini"

    def __init__(self) -> None:
        self.requests = 0

    def model_for(self, *, vision: bool, tier: str = "strong") -> str:
        return "fake-fast-model" if tier == "fast" else "fake-model"

    async def complete(
        self,
        *,
        schema: type[BaseModel],
        prompt: str,
        images: Sequence[bytes],
        max_output_tokens: int,
        temperature: float,
        image_detail: ImageDetail,
        tier: str = "strong",
    ) -> Completion:
        self.requests += 1
        if schema is ImageTriage:
            is_car = all(_is_red(i) for i in images)
            text = json.dumps(
                {"shows_vehicle": is_car, "usable": is_car, "reason": "synthetic"}
            )
        elif schema is DamageFindings:
            damages = (
                [
                    {
                        "component": "hood",
                        "damage_type": "dent",
                        "severity": 0.5,
                        "description": "synthetic",
                    }
                ]
                if "FRONT ZONE" in prompt
                else []
            )
            text = json.dumps({"damages": damages})
        else:
            text = FAKE_REPLIES[schema]
        return Completion(text=text, usage=Usage(500, 50), model="fake-model")


def _is_red(jpeg: bytes) -> bool:
    r, g, _ = Image.open(BytesIO(jpeg)).convert("RGB").getpixel((10, 10))  # type: ignore[misc]
    return bool(r > 150 and g < 100)
