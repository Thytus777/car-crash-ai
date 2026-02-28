"""Static fallback price database loaded from CSV."""

import csv
from decimal import Decimal
from pathlib import Path

_CSV_PATH = Path(__file__).parent.parent / "data" / "parts_prices.csv"
_PRICE_DATA: list[dict] | None = None


def _load_csv() -> list[dict]:
    global _PRICE_DATA
    if _PRICE_DATA is not None:
        return _PRICE_DATA

    with open(_CSV_PATH, newline="") as f:
        reader = csv.DictReader(f)
        _PRICE_DATA = list(reader)

    return _PRICE_DATA


def lookup_static_price(
    make: str, model: str, year: int, component: str
) -> Decimal | None:
    """Look up average part price from the static CSV.

    Returns the price as Decimal, or None if no match found.
    """
    rows = _load_csv()

    make_lower = make.lower()
    model_lower = model.lower()

    for row in rows:
        if (
            row["make"].lower() == make_lower
            and row["model"].lower() == model_lower
            and int(row["year_start"]) <= year <= int(row["year_end"])
            and row["component"] == component
        ):
            return Decimal(row["avg_price"]).quantize(Decimal("0.01"))

    return None
