"""Per-model token prices (app/data/model_pricing.yaml).

Prices are entered by hand from the providers' pricing pages, with the source
URL and the date they were checked. They are never estimated: a model without
an entry makes every cost that depends on it None ("unpriced"), not a guess.
"""

import datetime as dt
from decimal import Decimal
from functools import cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

PRICING_PATH = Path(__file__).resolve().parents[1] / "data" / "model_pricing.yaml"
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

    def cost(
        self, provider: str, model: str, input_tokens: int, output_tokens: int
    ) -> Decimal | None:
        price = self.models.get(f"{provider}/{model}")
        return price.cost(input_tokens, output_tokens) if price else None


def load_pricing(path: Path = PRICING_PATH) -> Pricing:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Pricing.model_validate(raw)


@cache
def pricing() -> Pricing:
    """The service's price table, loaded once."""
    return load_pricing()
