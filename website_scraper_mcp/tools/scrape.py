"""
tools/scrape.py - Detect static vs dynamic pages and scrape content.

Detection strategy:
  1. Fetch the page cheaply with httpx.
  2. Scan the HTML for JS-framework fingerprints.
  3. If dynamic fingerprints found → re-render with Playwright (Chromium).
  4. Parse final HTML with BeautifulSoup + Trafilatura.
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

from website_scraper_mcp.config import get_settings
from website_scraper_mcp.models import ScrapeResult

logger = logging.getLogger(__name__)
settings = get_settings()

# JS-framework / SPA fingerprints that indicate a dynamic page
_DYNAMIC_SIGNALS = [
    "__NEXT_DATA__",        # Next.js
    "__nuxt__",             # Nuxt.js
    "window.__",            # generic SPA bootstrap
    "react-root",           # React
    "ng-version",           # Angular
    "data-v-app",           # Vue 3
    "ember-application",    # Ember
    "__gatsby",             # Gatsby
    "svelte-",              # Svelte
    "_app_json",            # generic
]

_REQUEST_HEADERS = {
    "User-Agent": settings.user_agent,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _detect_dynamic(html: str) -> bool:
    """Return True when any SPA fingerprint is detected in the raw HTML."""
    return any(signal in html for signal in _DYNAMIC_SIGNALS)


def _extract_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Resolve all <a href> values and return unique same-domain URLs."""
    base_netloc = urlparse(base_url).netloc
    seen: set[str] = set()
    links: list[str] = []

    for tag in soup.find_all("a", href=True):
        href: str = tag["href"].strip()
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        full = urljoin(base_url, href).split("#")[0]   # strip fragments
        parsed = urlparse(full)
        # Keep only HTTP/HTTPS same-domain links
        if parsed.scheme in ("http", "https") and parsed.netloc == base_netloc:
            if full not in seen:
                seen.add(full)
                links.append(full)

    return links


def _parse_html(html: str, url: str) -> dict:
    """
    Extract structured data from raw HTML.
    Uses Trafilatura for main-content text and BS4 for title/links/metadata.
    """
    soup = BeautifulSoup(html, "lxml")

    # Title
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    # Main content via Trafilatura (best readability extraction available)
    content = trafilatura.extract(
        html,
        url=url or None,
        include_tables=True,
        include_links=False,
        include_comments=False,
        no_fallback=False,
        favor_recall=True,
    ) or ""

    # Fallback: grab body text if Trafilatura yields nothing useful
    if len(content.strip()) < 50:
        body = soup.find("body")
        if body:
            content = body.get_text(separator="\n", strip=True)

    # Metadata
    metadata: dict[str, str] = {}
    for tag in soup.find_all("meta"):
        name = tag.get("name") or tag.get("property") or ""
        value = tag.get("content", "")
        if name and value:
            metadata[name] = value

    links = _extract_links(soup, url)

    return {
        "title": title,
        "content": content,
        "raw_html": html,
        "links": links,
        "metadata": metadata,
    }


# ── Static scraper ─────────────────────────────────────────────────────────────

async def _scrape_static(url: str, probe_html: str) -> ScrapeResult:
    """Use the already-fetched probe HTML to build the result (no extra request)."""
    logger.info("[scrape] static  → %s", url)
    parsed = _parse_html(probe_html, url)
    return ScrapeResult(url=url, is_dynamic=False, **parsed)


# ── Dynamic scraper ────────────────────────────────────────────────────────────

async def _scrape_dynamic(url: str) -> ScrapeResult:
    """Launch headless Chromium, wait for network-idle, grab rendered HTML."""
    logger.info("[scrape] dynamic (Playwright) → %s", url)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=settings.playwright_headless)
        context = await browser.new_context(
            user_agent=settings.user_agent,
            java_script_enabled=True,
        )
        page = await context.new_page()
        try:
            await page.goto(
                url,
                timeout=settings.playwright_timeout_ms,
                wait_until="domcontentloaded",
            )
            await page.wait_for_timeout(3_000)
            html = await page.content()
        except PlaywrightTimeout:
            logger.warning("[scrape] Playwright timeout – using partial DOM for %s", url)
            html = await page.content()
        finally:
            await browser.close()

    parsed = _parse_html(html, url)
    return ScrapeResult(url=url, is_dynamic=True, **parsed)


# ── Public API ─────────────────────────────────────────────────────────────────

async def scrape_website(url: str, fast: bool = False) -> ScrapeResult:
    """
    Scrape a page and return structured data.

    Args:
        url:  Page URL to scrape.
        fast: If True, skip Playwright and always use httpx only (much faster).
              Use for bulk crawling. Dynamic content won't be rendered.
    """
    logger.info("[scrape] start → %s  fast=%s", url, fast)

    # ── Probe / fetch via httpx ────────────────────────────────────────────────
    try:
        async with httpx.AsyncClient(
            headers=_REQUEST_HEADERS,
            timeout=settings.request_timeout_seconds,
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            probe_html = resp.text
    except httpx.HTTPStatusError as exc:
        raise ValueError(
            f"HTTP {exc.response.status_code} fetching {url}"
        ) from exc
    except httpx.RequestError as exc:
        raise ConnectionError(f"Network error fetching {url}: {exc}") from exc

    # ── Decide scraping strategy ──────────────────────────────────────────────
    if fast:
        # Fast mode: always use static scraping — no Playwright, no browser
        result = await _scrape_static(url, probe_html)
    elif _detect_dynamic(probe_html):
        result = await _scrape_dynamic(url)
    else:
        result = await _scrape_static(url, probe_html)

    logger.info(
        "[scrape] done → %s | dynamic=%s | chars=%d | links=%d",
        url, result.is_dynamic, len(result.content), len(result.links),
    )
    return result
