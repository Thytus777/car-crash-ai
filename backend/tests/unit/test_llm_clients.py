"""Provider adapters: request shaping and response parsing at the SDK boundary."""

import base64
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import types as genai_types
from pydantic import BaseModel

from app.core.config import settings
from app.core.llm import GeminiClient, OpenAIClient, Usage


class Answer(BaseModel):
    value: int


class _Recorder:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.kwargs: dict[str, Any] = {}

    async def __call__(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self.response


async def test_gemini_client_sends_schema_and_images_and_reads_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "gemini_model", "gemini-test")
    response = genai_types.GenerateContentResponse(
        candidates=[
            genai_types.Candidate(
                content=genai_types.Content(
                    role="model", parts=[genai_types.Part(text='{"value": 1}')]
                )
            )
        ],
        usage_metadata=genai_types.GenerateContentResponseUsageMetadata(
            prompt_token_count=11, candidates_token_count=3, thoughts_token_count=4
        ),
    )
    generate_content = _Recorder(response)
    sdk = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )

    completion = await GeminiClient(sdk).complete(
        schema=Answer,
        prompt="describe",
        images=[b"\xff\xd8jpeg"],
        max_output_tokens=100,
        temperature=0.2,
        image_detail="high",
    )

    sent = generate_content.kwargs
    config: genai_types.GenerateContentConfig = sent["config"]
    assert sent["model"] == "gemini-test"
    assert sent["contents"][0] == "describe"
    assert sent["contents"][1].inline_data.data == b"\xff\xd8jpeg"
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == Answer.model_json_schema()
    assert config.max_output_tokens == 100 + settings.gemini_output_token_padding
    assert completion.text == '{"value": 1}'
    assert completion.usage == Usage(input_tokens=11, output_tokens=7)


async def test_openai_client_uses_structured_parse_with_image_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openai_vision_model", "gpt-vision-test")
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"value": 2}'))],
        usage=SimpleNamespace(prompt_tokens=20, completion_tokens=6),
    )
    parse = _Recorder(response)
    sdk = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(parse=parse))
    )

    completion = await OpenAIClient(sdk).complete(
        schema=Answer,
        prompt="describe",
        images=[b"jpeg"],
        max_output_tokens=50,
        temperature=0.1,
        image_detail="low",
    )

    sent = parse.kwargs
    content = sent["messages"][0]["content"]
    assert sent["model"] == "gpt-vision-test"
    assert sent["response_format"] is Answer
    assert sent["max_completion_tokens"] == 50
    assert content[0] == {"type": "text", "text": "describe"}
    assert content[1]["image_url"] == {
        "url": "data:image/jpeg;base64," + base64.b64encode(b"jpeg").decode(),
        "detail": "low",
    }
    assert completion.usage == Usage(input_tokens=20, output_tokens=6)


async def test_openai_text_only_calls_use_the_text_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openai_text_model", "gpt-text-test")
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=None))], usage=None
    )
    parse = _Recorder(response)
    sdk = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(parse=parse))
    )

    completion = await OpenAIClient(sdk).complete(
        schema=Answer,
        prompt="q",
        images=[],
        max_output_tokens=10,
        temperature=0.0,
        image_detail="high",
    )

    assert parse.kwargs["model"] == "gpt-text-test"
    assert completion.text == "" and completion.usage == Usage()
