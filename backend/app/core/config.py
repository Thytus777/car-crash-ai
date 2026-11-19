import re
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings

# Values like 'sk-your-key-here' copied from .env.example mean "not set".
_PLACEHOLDER = re.compile(r"(sk-)?your[-_].*[-_]here", re.IGNORECASE)


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    ai_provider: Literal["gemini", "openai"] = "gemini"
    # Directory under backend/prompts/; recorded in every analysis response.
    prompt_version: str = "v3"
    log_level: str = "INFO"
    # e.g. http://otel-collector:4318; empty disables span export.
    otel_exporter_otlp_endpoint: str = ""
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

    # Cheap-first routing for damage zones (ADR 0003, status: proposed).
    # Off until evals show the quality/cost trade-off is acceptable.
    routing_enabled: bool = False
    gemini_fast_model: str = ""  # empty: no fast tier, routing is skipped
    openai_fast_model: str = ""
    routing_escalation_margin: float = 0.1  # |severity - threshold|
    routing_escalate_empty_zones: bool = False

    # Per-request budgets. Exceeding one is logged, counted
    # (budget_exceeded_total) and listed in meta.budget_exceeded; the
    # request still succeeds. Latency matches the p95 SLO (docs/SLO.md).
    request_cost_budget_usd: float | None = None  # None: no cost budget
    request_latency_budget_s: float = 60.0

    # Secrets render as '**********' in repr/str/logs; read with .get_secret_value().
    openai_api_key: SecretStr = SecretStr("")
    gemini_api_key: SecretStr = SecretStr("")
    google_ai_gemini_api_key: SecretStr = SecretStr("")
    serpapi_key: SecretStr = SecretStr("")

    labor_rate_per_hour: float = 75.00
    pricing_concurrency: int = 4  # damaged components priced at once
    price_page_concurrency: int = 5  # pages fetched/extracted at once per part
    price_search_deadline_s: float = 20.0  # then fall back to static/AI price
    # Complete reports for identical photos + settings are reused (see
    # app/services/result_cache.py); prices drift, hence the TTL.
    result_cache_enabled: bool = True
    result_cache_dir: Path = Path("cache/results")
    result_cache_ttl_hours: float = 24
    severity_replace_threshold: float = 0.3

    upload_dir: Path = Path("uploads")
    max_upload_size_mb: float = 20  # per file
    max_upload_total_mb: float = 40  # all files in one request
    max_images_per_request: int = 10
    min_image_width: int = 640
    min_image_height: int = 480
    # Faces and number plates are blurred at upload (app/services/redaction.py).
    # Production must set REDACTION_REQUIRED so a missing model refuses uploads.
    redaction_required: bool = False
    redaction_models_dir: Path = Path(__file__).resolve().parents[2] / "models"
    redaction_plate_threshold: float = 0.25
    redaction_face_threshold: float = 0.6
    # Uploaded (redacted) photos are deleted after this; see docs/DATA_RETENTION.md.
    upload_retention_hours: float = 24
    # Uploads are stored at up to this long edge (JPEG, STORED_IMAGE_QUALITY)...
    stored_image_max_edge: int = 1600
    stored_image_quality: int = 90
    # ...and downscaled to this when sent to the models. Eval sweeps change
    # these without re-uploading; both caches key on the bytes actually sent.
    model_image_max_edge: int = 1024
    model_image_jpeg_quality: int = 90

    cors_origins: list[str] = ["*"]

    # PostgreSQL — asyncpg driver
    database_url: SecretStr = SecretStr(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/carcrash"
    )

    @field_validator(
        "openai_api_key",
        "gemini_api_key",
        "google_ai_gemini_api_key",
        "serpapi_key",
        mode="before",
    )
    @classmethod
    def _blank_placeholders(cls, value: object) -> object:
        if isinstance(value, str) and _PLACEHOLDER.fullmatch(value.strip()):
            return ""
        return value


settings = Settings()
