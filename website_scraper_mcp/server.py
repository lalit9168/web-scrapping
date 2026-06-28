"""
server.py - MCP server with 5 scraping-only tools.

Tools:
  1. scrape_website      – Scrape a single page (auto static/dynamic).
  2. crawl_website       – BFS-crawl all internal pages.
  3. clean_content       – Strip noise from raw HTML.
  4. chunk_content       – Split text into overlapping chunks.
  5. scrape_full_site    – End-to-end: crawl → clean → (chunk) every page.
"""

from __future__ import annotations

import json
import logging

from mcp.server import Server
from mcp.types import Tool, TextContent

from website_scraper_mcp.config import get_settings
from website_scraper_mcp.models import (
    ScrapeInput,
    CrawlInput,
    CleanInput,
    ChunkInput,
    ScrapeFullSiteInput,
    PageResult,
    ScrapeFullSiteResult,
)
from website_scraper_mcp.tools.scrape import scrape_website
from website_scraper_mcp.tools.crawl import crawl_website
from website_scraper_mcp.tools.clean import clean_content
from website_scraper_mcp.tools.chunk import chunk_content

logger = logging.getLogger(__name__)
settings = get_settings()

server = Server(settings.mcp_server_name)


# ═══════════════════════════════════════════════════════════════════════════════
# list_tools
# ═══════════════════════════════════════════════════════════════════════════════

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        # ── 1. scrape_website ──────────────────────────────────────────────────
        Tool(
            name="scrape_website",
            description=(
                "Scrape a single web page. Automatically detects whether the page is "
                "static (uses httpx + BeautifulSoup) or dynamic/JS-rendered (uses "
                "Playwright headless Chromium). Returns the page title, clean content, "
                "all internal/external links, and page metadata."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full URL of the page to scrape (e.g. https://example.com).",
                    },
                },
                "required": ["url"],
            },
        ),

        # ── 2. crawl_website ───────────────────────────────────────────────────
        Tool(
            name="crawl_website",
            description=(
                "BFS-crawl an entire website starting from the given root URL. "
                "Only follows internal (same-domain) links. Respects robots.txt. "
                "Avoids duplicate URLs. Limits crawl depth and total page count. "
                "Returns every scraped page with title, content, and links."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Root URL to start crawling from.",
                    },
                    "max_depth": {
                        "type": "integer",
                        "default": 2,
                        "minimum": 1,
                        "maximum": 10,
                        "description": "How many link-hops deep to crawl (default 2).",
                    },
                },
                "required": ["url"],
            },
        ),

        # ── 3. clean_content ───────────────────────────────────────────────────
        Tool(
            name="clean_content",
            description=(
                "Clean raw HTML by removing scripts, styles, navigation bars, "
                "footers, cookie banners, ads, and other noise. Returns readable "
                "plain text keeping only main article content, headings, paragraphs, "
                "tables, and lists."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "html": {
                        "type": "string",
                        "description": "Raw HTML string to clean.",
                    },
                    "url": {
                        "type": "string",
                        "default": "",
                        "description": "Optional source URL (helps with relative link resolution).",
                    },
                },
                "required": ["html"],
            },
        ),

        # ── 4. chunk_content ───────────────────────────────────────────────────
        Tool(
            name="chunk_content",
            description=(
                "Split clean text into overlapping chunks (~1 000 characters each, "
                "200-character overlap). Each chunk has a unique deterministic ID "
                "derived from the URL and position. Useful for preparing text for "
                "vector embedding or search indexing."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Clean plain text to split.",
                    },
                    "url": {
                        "type": "string",
                        "default": "",
                        "description": "Source URL to embed in each chunk.",
                    },
                    "title": {
                        "type": "string",
                        "default": "",
                        "description": "Page title to embed in each chunk.",
                    },
                },
                "required": ["text"],
            },
        ),

        # ── 5. scrape_full_site ────────────────────────────────────────────────
        Tool(
            name="scrape_full_site",
            description=(
                "End-to-end pipeline: crawl every internal page of a website, "
                "clean the HTML of each page, and optionally split into chunks. "
                "Returns a structured result with every page's title, clean content, "
                "links, metadata, and (if requested) text chunks. "
                "Handles both static and dynamic pages automatically."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Root website URL to start from.",
                    },
                    "max_depth": {
                        "type": "integer",
                        "default": 2,
                        "minimum": 1,
                        "maximum": 10,
                        "description": "Maximum crawl depth (default 2).",
                    },
                    "clean": {
                        "type": "boolean",
                        "default": True,
                        "description": "Whether to clean HTML before returning content.",
                    },
                    "chunk": {
                        "type": "boolean",
                        "default": False,
                        "description": "Whether to split page content into chunks.",
                    },
                },
                "required": ["url"],
            },
        ),
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# call_tool dispatcher
# ═══════════════════════════════════════════════════════════════════════════════

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    logger.info("[mcp] ► %s  args=%s", name, arguments)
    try:
        result = await _dispatch(name, arguments)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[mcp] ✗ %s raised an exception", name)
        payload = {"error": str(exc), "tool": name}
        return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]

    text = (
        json.dumps(result.model_dump(), ensure_ascii=False, indent=2)
        if hasattr(result, "model_dump")
        else json.dumps(result, ensure_ascii=False, indent=2)
    )
    return [TextContent(type="text", text=text)]


async def _dispatch(name: str, args: dict):  # noqa: ANN201
    match name:

        # ── 1 ─────────────────────────────────────────────────────────────────
        case "scrape_website":
            inp = ScrapeInput(**args)
            result = await scrape_website(inp.url)
            # Omit raw_html from response to keep payload manageable
            return {
                "title": result.title,
                "url": result.url,
                "content": result.content,
                "links": result.links,
                "is_dynamic": result.is_dynamic,
                "metadata": result.metadata,
            }

        # ── 2 ─────────────────────────────────────────────────────────────────
        case "crawl_website":
            inp = CrawlInput(**args)
            pages, errors = await crawl_website(inp.url, inp.max_depth)
            return {
                "root_url": inp.url,
                "pages_crawled": len(pages),
                "errors": errors,
                "pages": [
                    {
                        "url": p.url,
                        "title": p.title,
                        "content": p.content,
                        "links": p.links,
                        "is_dynamic": p.is_dynamic,
                        "metadata": p.metadata,
                    }
                    for p in pages
                ],
            }

        # ── 3 ─────────────────────────────────────────────────────────────────
        case "clean_content":
            inp = CleanInput(**args)
            cleaned = clean_content(inp.html, inp.url)
            return {"cleaned_text": cleaned, "char_count": len(cleaned)}

        # ── 4 ─────────────────────────────────────────────────────────────────
        case "chunk_content":
            inp = ChunkInput(**args)
            chunks = chunk_content(inp.text, inp.url, inp.title)
            return [c.model_dump() for c in chunks]

        # ── 5 ─────────────────────────────────────────────────────────────────
        case "scrape_full_site":
            return await _full_site_pipeline(args)

        case _:
            raise ValueError(f"Unknown tool: {name!r}")


# ── Full-site pipeline ─────────────────────────────────────────────────────────

async def _full_site_pipeline(args: dict) -> ScrapeFullSiteResult:
    inp = ScrapeFullSiteInput(**args)
    logger.info("[pipeline] Starting full-site scrape → %s  depth=%d", inp.url, inp.max_depth)

    # Step 1 – Crawl all pages
    pages_raw, crawl_errors = await crawl_website(inp.url, inp.max_depth)
    logger.info("[pipeline] Crawled %d pages, %d errors", len(pages_raw), len(crawl_errors))

    results: list[PageResult] = []
    total_chunks = 0

    for page in pages_raw:
        try:
            # Step 2 – Clean
            if inp.clean:
                text = clean_content(page.raw_html, page.url)
            else:
                text = page.content

            # Step 3 – Chunk (optional)
            chunks = []
            if inp.chunk and text:
                chunks = chunk_content(text, page.url, page.title)
                total_chunks += len(chunks)

            results.append(
                PageResult(
                    url=page.url,
                    title=page.title,
                    content=text,
                    is_dynamic=page.is_dynamic,
                    links=page.links,
                    metadata=page.metadata,
                    chunks=chunks,
                )
            )
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            logger.warning("[pipeline] Error processing %s: %s", page.url, msg)
            crawl_errors.append({"url": page.url, "error": msg})

    logger.info("[pipeline] Done: %d pages, %d chunks, %d errors",
                len(results), total_chunks, len(crawl_errors))

    return ScrapeFullSiteResult(
        root_url=inp.url,
        pages_crawled=len(results),
        total_chunks=total_chunks,
        pages=results,
        errors=crawl_errors,
    )
