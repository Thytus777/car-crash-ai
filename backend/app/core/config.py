from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    ai_provider: Literal["gemini", "openai"] = "gemini"
    gemini_model: str = "gemini-3.6-flash"
    openai_vision_model: str = "gpt-4.1-mini"
    openai_text_model: str = "gpt-4.1-nano"
    # Gemini "thinking" tokens count against max_output_tokens, so visible
    # output gets this much extra headroom and thinking is capped separately.
    gemini_thinking_budget: int = 512
    gemini_output_token_padding: int = 8000

    # LLM call policy (see app/core/llm.py)
    llm_timeout_s: float = 45.0  # per attempt
    llm_max_attempts: int = 3  # transient failures (429/5xx/timeout) per provider
    llm_max_invalid_outputs: int = 2  # re-asks after schema-invalid output
    llm_backoff_base_s: float = 1.0
    llm_backoff_max_s: float = 10.0

    openai_api_key: str = ""
    gemini_api_key: str = ""
    google_ai_gemini_api_key: str = ""
    serpapi_key: str = ""

    labor_rate_per_hour: float = 75.00
    price_cache_ttl_hours: int = 24
    severity_replace_threshold: float = 0.3

    upload_dir: Path = Path("uploads")
    max_upload_size_mb: int = 20
    max_images_per_request: int = 10
    min_image_width: int = 640
    min_image_height: int = 480

    cors_origins: list[str] = ["*"]

    # PostgreSQL — asyncpg driver
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/carcrash"


settings = Settings()
