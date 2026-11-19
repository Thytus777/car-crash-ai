from unittest.mock import patch

import pytest

from app.core.config import settings
from app.models.llm_outputs import PriceExtraction
from app.services.price_search import _extract_prices
from tests.concurrency import PeakTracker
from tests.llm_fakes import llm_result


def _extraction(price: float | None) -> PriceExtraction:
    return PriceExtraction(
        price=price,
        currency="AUD",
        part_type="oem",
        in_stock=True,
        product_name="Bumper",
        confidence=0.9,
    )


async def test_pages_are_extracted_concurrently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "price_page_concurrency", 4)
    tracker = PeakTracker()
    fake = tracker.wrap(lambda *a, **k: llm_result(_extraction(100.0)))
    snippets = [(f"shop{i}.example", "text") for i in range(6)]

    with patch("app.services.price_search.generate", side_effect=fake):
        results = await _extract_prices(snippets, "Toyota", "Camry", 2020, "hood")

    assert tracker.peak == 4
    assert [r.source_url for r in results] == [
        f"https://shop{i}.example" for i in range(6)
    ]


async def test_pages_without_a_price_are_skipped() -> None:
    by_domain = {"a.example": _extraction(None), "b.example": _extraction(55.5)}

    async def fake_generate(_schema: object, prompt: str, **_: object) -> object:
        domain = next(d for d in by_domain if d in prompt)
        return llm_result(by_domain[domain])

    with patch("app.services.price_search.generate", side_effect=fake_generate):
        results = await _extract_prices(
            [("a.example", "t"), ("b.example", "t")], "Toyota", "Camry", 2020, "hood"
        )

    assert [str(r.price) for r in results] == ["55.50"]
