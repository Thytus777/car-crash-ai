"""Live price search pipeline — Search API → Fetch → AI Extract → Aggregate."""

import asyncio
import logging
from decimal import Decimal

import httpx
import trafilatura

from app.core.config import settings
from app.core.errors import AppError
from app.core.llm import generate
from app.models.estimate import PriceResult
from app.models.llm_outputs import PriceExtraction
from app.prompts import render

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
    """Fetch URLs concurrently and extract clean text. Returns [(domain, text)]."""
    limit = asyncio.Semaphore(settings.price_page_concurrency)

    async with httpx.AsyncClient(
        timeout=FETCH_TIMEOUT, follow_redirects=True
    ) as client:

        async def fetch(url: str) -> tuple[str, str] | None:
            async with limit:
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                except httpx.HTTPError:
                    logger.debug("Failed to fetch: %s", url, exc_info=True)
                    return None
            # HTML-to-text is CPU-bound; keep it off the event loop.
            text = await asyncio.to_thread(trafilatura.extract, response.text) or ""
            if not text:
                return None
            domain = url.split("/")[2] if "/" in url else url
            return domain, text[:2000]

        pages = await asyncio.gather(*(fetch(url) for url in urls))
    return [page for page in pages if page is not None]


async def _extract_prices(
    snippets: list[tuple[str, str]],
    make: str,
    model: str,
    year: int,
    component: str,
) -> list[PriceResult]:
    """Use the LLM to extract a price from each page, concurrently."""
    limit = asyncio.Semaphore(settings.price_page_concurrency)

    async def extract(domain: str, text: str) -> PriceResult | None:
        prompt = render(
            "price_extraction",
            site_domain=domain,
            year=year,
            make=make,
            model=model,
            component=component.replace("_", " "),
            cleaned_text=text,
        )
        async with limit:
            try:
                result = await generate(
                    PriceExtraction,
                    prompt,
                    task="price_extraction",
                    max_output_tokens=200,
                    temperature=0.1,
                )
            except AppError as exc:
                # One page failing just means one fewer price sample.
                logger.info("Price extraction failed for %s: %s", domain, exc.detail)
                return None

        extracted = result.output
        if extracted.price is None:
            return None
        return PriceResult(
            price=Decimal(str(extracted.price)).quantize(Decimal("0.01")),
            currency=extracted.currency,
            part_type=extracted.part_type,
            in_stock=extracted.in_stock,
            product_name=extracted.product_name,
            source_url=f"https://{domain}",
            confidence=extracted.confidence,
        )

    results = await asyncio.gather(*(extract(d, t) for d, t in snippets))
    return [r for r in results if r is not None]
