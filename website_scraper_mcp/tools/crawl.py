"""
tools/crawl.py - BFS website crawler.

Rules:
  - Only internal (same-domain) links are followed.
  - Each URL is visited at most once.
  - robots.txt is respected.
  - Depth is capped at max_depth.
  - Total pages are capped at settings.max_pages_per_site.
  - A polite delay is inserted between requests.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from website_scraper_mcp.config import get_settings
from website_scraper_mcp.models import ScrapeResult
from website_scraper_mcp.tools.scrape import scrape_website

logger = logging.getLogger(__name__)
settings = get_settings()

_HEADERS = {"User-Agent": settings.user_agent}


# ── robots.txt ─────────────────────────────────────────────────────────────────

async def _load_robots(base_url: str) -> RobotFileParser | None:
    """Download and parse robots.txt. Returns None on any failure."""
    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=10, follow_redirects=True) as client:
            resp = await client.get(robots_url)
            if resp.status_code == 200:
                rp = RobotFileParser()
                rp.parse(resp.text.splitlines())
                logger.debug("[crawl] Loaded robots.txt from %s", robots_url)
                return rp
    except Exception as exc:  # noqa: BLE001
        logger.debug("[crawl] Could not load robots.txt: %s", exc)
    return None


def _allowed(url: str, rp: RobotFileParser | None) -> bool:
    """Return True if robots.txt permits crawling this URL."""
    return rp is None or rp.can_fetch(settings.user_agent, url)


def _same_domain(url: str, netloc: str) -> bool:
    return urlparse(url).netloc == netloc


# ── Public API ─────────────────────────────────────────────────────────────────

_CONCURRENCY = 10   # pages scraped in parallel

async def crawl_website(
    url: str,
    max_depth: int | None = None,
    fast: bool = True,
    max_pages: int | None = None,
) -> tuple[list[ScrapeResult], list[dict[str, str]]]:
    """
    BFS-crawl a website with concurrent page fetching.

    Args:
        url:       Root URL to start crawling from.
        max_depth: How many link-hops deep to follow (default from config).
        fast:      If True, skip Playwright - use httpx only (much faster).
        max_pages: Max pages to scrape (default from config: 20).

    Returns:
        (pages, errors)
    """
    depth_limit = max_depth if max_depth is not None else settings.max_crawl_depth
    page_limit  = max_pages if max_pages is not None else settings.max_pages_per_site
    base_netloc = urlparse(url).netloc

    logger.info("[crawl] Starting BFS from %s  depth=%d  max_pages=%d  concurrency=%d",
                url, depth_limit, page_limit, _CONCURRENCY)

    rp = await _load_robots(url)
    semaphore = asyncio.Semaphore(_CONCURRENCY)

    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(url, 0)])
    pages: list[ScrapeResult] = []
    errors: list[dict[str, str]] = []

    async def fetch_page(current_url: str, depth: int) -> tuple[ScrapeResult | None, str | None]:
        async with semaphore:
            await asyncio.sleep(settings.crawl_delay_seconds)
            try:
                logger.info("[crawl] depth=%d  fetching → %s", depth, current_url)
                result = await scrape_website(current_url, fast=fast)
                return result, None
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                logger.warning("[crawl] Error at %s: %s", current_url, msg)
                return None, msg

    while queue and len(pages) < page_limit:
        # Collect a batch of URLs to fetch concurrently
        batch: list[tuple[str, int]] = []
        while queue and len(batch) < _CONCURRENCY and len(pages) + len(batch) < page_limit:
            current_url, depth = queue.popleft()
            if current_url in visited or not _allowed(current_url, rp):
                continue
            visited.add(current_url)
            batch.append((current_url, depth))

        if not batch:
            break

        # Fetch batch concurrently
        tasks = [fetch_page(u, d) for u, d in batch]
        results = await asyncio.gather(*tasks)

        for (current_url, depth), (result, err) in zip(batch, results):
            if err:
                errors.append({"url": current_url, "error": err})
            elif result:
                pages.append(result)
                # Enqueue child links
                if depth < depth_limit:
                    for link in result.links:
                        if link not in visited and _same_domain(link, base_netloc):
                            queue.append((link, depth + 1))

    logger.info("[crawl] Done: %d pages  %d errors", len(pages), len(errors))
    return pages, errors
