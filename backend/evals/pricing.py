"""Per-model token prices (evals/pricing.yaml), entered by hand from the
providers' pricing pages. Never guessed: an unpriced model makes cost per
request None rather than a made-up number."""

import datetime as dt
from decimal import Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from evals.dataset import EVALS_ROOT

PRICING_PATH = EVALS_ROOT / "pricing.yaml"
_PER_TOKEN = Decimal(1_000_000)


class ModelPrice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_usd_per_mtok: Decimal = Field(ge=0)
    output_usd_per_mtok: Decimal = Field(ge=0)
    source: str = Field(min_length=1, description="URL of the pricing page")
    checked: dt.date

    def cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        return (
            self.input_usd_per_mtok * input_tokens
            + self.output_usd_per_mtok * output_tokens
        ) / _PER_TOKEN


class Pricing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    models: dict[str, ModelPrice] = {}  # key: "<provider>/<model>"


def load_pricing(path: Path = PRICING_PATH) -> Pricing:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Pricing.model_validate(raw)
