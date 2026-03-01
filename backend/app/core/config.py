from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    ai_provider: Literal["gemini", "openai"] = "gemini"

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


settings = Settings()
