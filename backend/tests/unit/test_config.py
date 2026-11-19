"""Secrets never render in clear text; .env.example placeholders are unset (#34)."""

import pytest

import app.core.llm as llm
from app.core.config import Settings, settings

SECRETS = {
    "gemini_api_key": "AIza-real-gemini-key",
    "openai_api_key": "sk-real-openai-key",
    "serpapi_key": "real-serpapi-key",
    "database_url": "postgresql+asyncpg://app:hunter2@db:5432/carcrash",
}


def test_secrets_are_masked_in_repr_and_str() -> None:
    configured = Settings(_env_file=None, **SECRETS)  # type: ignore[call-arg]

    for text in (repr(configured), str(configured)):
        for value in (*SECRETS.values(), "hunter2"):
            assert value not in text


@pytest.mark.parametrize(
    "placeholder", ["sk-your-key-here", "your-gemini-key-here", "your-serpapi-key-here"]
)
def test_env_example_placeholders_are_treated_as_unset(placeholder: str) -> None:
    configured = Settings(  # type: ignore[call-arg]
        _env_file=None,
        openai_api_key=placeholder,
        gemini_api_key=placeholder,
        serpapi_key=placeholder,
    )

    assert configured.openai_api_key.get_secret_value() == ""
    assert configured.gemini_api_key.get_secret_value() == ""
    assert configured.serpapi_key.get_secret_value() == ""


def test_placeholder_openai_key_is_not_used_as_a_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replacement = Settings(  # type: ignore[call-arg]
        _env_file=None, gemini_api_key="AIza-real", openai_api_key="sk-your-key-here"
    )
    monkeypatch.setattr(llm, "settings", replacement)

    assert llm._providers() == ["gemini"]


def test_real_keys_are_readable_where_needed() -> None:
    configured = Settings(_env_file=None, **SECRETS)  # type: ignore[call-arg]

    assert configured.openai_api_key.get_secret_value() == "sk-real-openai-key"
    assert configured.database_url.get_secret_value() == SECRETS["database_url"]
    assert settings is not configured
