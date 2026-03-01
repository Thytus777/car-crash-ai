"""Live price search pipeline — Search API → Fetch → AI Extract → Aggregate."""

import json
import logging
from decimal import Decimal

import httpx
import trafilatura

from app.core.config import settings
from app.core.llm import text_completion
from app.models.estimate import PriceResult
from app.prompts.price_extraction import PRICE_EXTRACTION_PROMPT

logger = logging.getLogger(__name__)

MAX_RESULTS = 5
FETCH_TIMEOUT = 5.0
MIN_CONFIDENCE = 0.5


async def search_part_prices(
    make: str,
    model: str,
    year: int,
    component: str,
) -> list[PriceResult]:
    """Run the full Search → Fetch → Extract pipeline for a car part."""
    query = f"{year} {make} {model} {component.replace('_', ' ')} price buy"

    urls = await _search_web(query)
    if not urls:
        logger.warning("No search results for: %s", query)
        return []

    snippets = await _fetch_and_clean(urls)
    if not snippets:
        logger.warning("No pages successfully fetched for: %s", query)
        return []

    results = await _extract_prices(snippets, make, model, year, component)
    return [r for r in results if r.confidence >= MIN_CONFIDENCE]


async def _search_web(query: str) -> list[str]:
    """Search the web using SerpAPI and return top result URLs."""
    if not settings.serpapi_key:
        logger.warning("SERPAPI_KEY not set, skipping live search")
        return []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://serpapi.com/search.json",
                params={
                    "q": query,
                    "api_key": settings.serpapi_key,
                    "num": MAX_RESULTS,
                    "engine": "google",
                },
            )
            response.raise_for_status()
            data = response.json()

        urls: list[str] = []
        for result in data.get("organic_results", [])[:MAX_RESULTS]:
            link = result.get("link")
            if link:
                urls.append(link)

        logger.info("Search returned %d URLs for: %s", len(urls), query)
        return urls

    except Exception:
        logger.exception("Search API call failed for: %s", query)
        return []


async def _fetch_and_clean(
    urls: list[str],
) -> list[tuple[str, str]]:
    """Fetch each URL and extract clean text. Returns [(domain, text), ...]."""
    results: list[tuple[str, str]] = []

    async with httpx.AsyncClient(
        timeout=FETCH_TIMEOUT, follow_redirects=True
    ) as client:
        for url in urls:
            try:
                response = await client.get(url)
                response.raise_for_status()

                text = trafilatura.extract(response.text) or ""
                if not text:
                    continue

                text = text[:2000]
                domain = url.split("/")[2] if "/" in url else url
                results.append((domain, text))

            except Exception:
                logger.debug("Failed to fetch: %s", url, exc_info=True)
                continue

    return results


async def _extract_prices(
    snippets: list[tuple[str, str]],
    make: str,
    model: str,
    year: int,
    component: str,
) -> list[PriceResult]:
    """Use LLM to extract price data from each cleaned page snippet."""
    results: list[PriceResult] = []

    for domain, text in snippets:
        prompt = PRICE_EXTRACTION_PROMPT.format(
            site_domain=domain,
            year=year,
            make=make,
            model=model,
            component=component.replace("_", " "),
            cleaned_text=text,
        )

        try:
            raw = await text_completion(
                prompt=prompt,
                max_tokens=200,
                temperature=0.1,
            )
            logger.debug("Price extraction from %s: %s", domain, raw)

            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
                cleaned = cleaned.rsplit("```", 1)[0].strip()

            data = json.loads(cleaned)

            if data.get("price") is not None:
                results.append(
                    PriceResult(
                        price=Decimal(str(data["price"])).quantize(Decimal("0.01")),
                        currency=data.get("currency", "USD"),
                        part_type=data.get("part_type", "unknown"),
                        in_stock=data.get("in_stock"),
                        product_name=data.get("product_name", ""),
                        source_url=f"https://{domain}",
                        confidence=float(data.get("confidence", 0.0)),
                    )
                )

        except Exception:
            logger.debug("Price extraction failed for %s", domain, exc_info=True)
            continue

    return results
