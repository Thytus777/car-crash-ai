"""Live price search pipeline — Search API → Fetch → AI Extract → Aggregate."""

import asyncio
import ipaddress
import logging
import re
import socket
from decimal import Decimal
from urllib.parse import urljoin, urlsplit

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
MAX_REDIRECTS = 3
MAX_PAGE_BYTES = 2 * 1024 * 1024
_PAGE_TAG = re.compile(r"<\s*/?\s*page\s*>", re.IGNORECASE)
_CURRENCY = re.compile(r"[A-Z]{3}")


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
    if not settings.serpapi_key.get_secret_value():
        logger.warning("SERPAPI_KEY not set, skipping live search")
        return []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://serpapi.com/search.json",
                params={
                    "q": query,
                    "api_key": settings.serpapi_key.get_secret_value(),
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


async def _resolve(host: str) -> list[str]:
    """All addresses a hostname resolves to (indirection for tests)."""
    infos = await asyncio.to_thread(
        socket.getaddrinfo, host, 443, type=socket.SOCK_STREAM
    )
    return [str(info[4][0]) for info in infos]


async def is_public_https(url: str) -> bool:
    """Only https URLs whose every resolved address is publicly routable.

    Blocks loopback, private, link-local (incl. 169.254.169.254 metadata),
    reserved and multicast targets. Search results are attacker-influenced,
    so this is the server-side request forgery guard. (A DNS answer can
    still change between this check and the connect; pinning the address
    would close that gap.)
    """
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        return False
    try:
        addresses = await _resolve(parts.hostname)
    except OSError:
        return False
    return bool(addresses) and all(
        ipaddress.ip_address(a.split("%")[0]).is_global for a in addresses
    )


async def _get_page(client: httpx.AsyncClient, url: str) -> tuple[str, str] | None:
    """Fetch one page safely: re-check every redirect hop, cap the body."""
    for _ in range(MAX_REDIRECTS + 1):
        if not await is_public_https(url):
            logger.info("Skipping non-public or non-https URL: %s", url)
            return None
        async with client.stream("GET", url) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers.get("location", ""))
                continue
            response.raise_for_status()
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body += chunk
                if len(body) > MAX_PAGE_BYTES:
                    logger.info(
                        "Page over %d bytes, truncated: %s", MAX_PAGE_BYTES, url
                    )
                    break
            return url, bytes(body[:MAX_PAGE_BYTES]).decode(
                response.encoding or "utf-8", errors="replace"
            )
    logger.info("Too many redirects: %s", url)
    return None


async def _fetch_and_clean(
    urls: list[str],
) -> list[tuple[str, str]]:
    """Fetch URLs concurrently and extract clean text. Returns [(domain, text)]."""
    limit = asyncio.Semaphore(settings.price_page_concurrency)

    async with httpx.AsyncClient(
        timeout=FETCH_TIMEOUT, follow_redirects=False
    ) as client:

        async def fetch(url: str) -> tuple[str, str] | None:
            async with limit:
                try:
                    page = await _get_page(client, url)
                except httpx.HTTPError:
                    logger.debug("Failed to fetch: %s", url, exc_info=True)
                    return None
            if page is None:
                return None
            final_url, html = page
            # HTML-to-text is CPU-bound; keep it off the event loop.
            text = await asyncio.to_thread(trafilatura.extract, html) or ""
            if not text:
                return None
            return urlsplit(final_url).hostname or final_url, text[:2000]

        pages = await asyncio.gather(*(fetch(url) for url in urls))
    return [page for page in pages if page is not None]


def fence_untrusted(text: str) -> str:
    """Stop page text from closing the prompt's <page> fence early."""
    return _PAGE_TAG.sub("[tag removed]", text)


def plausible(extracted: PriceExtraction) -> bool:
    """Reject prices a manipulated or confused page could talk the model into."""
    if extracted.price is None:
        return False
    if not _CURRENCY.fullmatch(extracted.currency):
        return False
    return settings.min_part_price <= extracted.price <= settings.max_part_price


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
            cleaned_text=fence_untrusted(text),
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
        if not plausible(extracted):
            if extracted.price is not None:
                logger.info("Discarded implausible price from %s", domain)
            return None
        assert extracted.price is not None
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
