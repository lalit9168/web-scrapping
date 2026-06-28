"""
app.py - Entry point.

Supports two transport modes:
  1. stdio  (default)   – for MCP-compatible AI agents / clients.
  2. sse               – Server-Sent Events over HTTP (for browser/HTTP clients).

Usage:
  python app.py                  # stdio mode
  python app.py --transport sse  # SSE mode (serves on http://localhost:8000)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from website_scraper_mcp.config import get_settings

settings = get_settings()

# ── Logging setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    stream=sys.stderr,  # keep stdout clean for MCP stdio transport
)
logger = logging.getLogger(__name__)


# ── Runner ─────────────────────────────────────────────────────────────────────

async def run_stdio() -> None:
    """Run the MCP server over stdio (default MCP transport)."""
    from mcp.server.stdio import stdio_server
    from website_scraper_mcp.server import server

    logger.info("Starting %s v%s (stdio transport)", settings.mcp_server_name, settings.mcp_server_version)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


async def run_sse(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Run the MCP server over SSE transport (HTTP) + plain REST API for Postman testing."""
    import json
    import uvicorn
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route
    from starlette.responses import Response, JSONResponse
    from starlette.requests import Request
    from website_scraper_mcp.server import server
    from website_scraper_mcp.tools.scrape import scrape_website
    from website_scraper_mcp.tools.crawl import crawl_website
    from website_scraper_mcp.tools.clean import clean_content
    from website_scraper_mcp.tools.chunk import chunk_content

    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())
        return Response()

    # ── REST API endpoints (easy Postman testing) ──────────────────────────────

    async def api_scrape(request: Request):
        """POST /api/scrape  body: {"url": "https://example.com"}"""
        try:
            body = await request.json()
            url = body.get("url", "").strip()
            if not url:
                return JSONResponse({"error": "url is required"}, status_code=400)
            result = await scrape_website(url)
            return JSONResponse({
                "title": result.title,
                "url": result.url,
                "is_dynamic": result.is_dynamic,
                "content": result.content,
                "links": result.links,
                "metadata": result.metadata,
            })
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    async def api_crawl(request: Request):
        """POST /api/crawl  body: {"url": "https://example.com", "max_depth": 2}"""
        try:
            body = await request.json()
            url = body.get("url", "").strip()
            max_depth = int(body.get("max_depth", 2))
            if not url:
                return JSONResponse({"error": "url is required"}, status_code=400)
            pages, errors = await crawl_website(url, max_depth)
            return JSONResponse({
                "root_url": url,
                "pages_crawled": len(pages),
                "errors": errors,
                "pages": [
                    {"url": p.url, "title": p.title, "content": p.content,
                     "is_dynamic": p.is_dynamic, "links": p.links}
                    for p in pages
                ],
            })
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    async def api_scrape_full_site(request: Request):
        """
        POST /api/scrape-full-site
        body: {
          "url": "https://example.com",
          "max_depth": 1,    -- default 1
          "max_pages": 30,   -- default 10 (fast response)
          "fast": true       -- default true (skip Playwright, httpx only)
        }
        Returns each page separately with full content. No chunks.
        """
        try:
            body = await request.json()
            url       = body.get("url", "").strip()
            max_depth = int(body.get("max_depth", 1))
            max_pages = int(body.get("max_pages", 30))
            fast      = bool(body.get("fast", True))

            if not url:
                return JSONResponse({"error": "url is required"}, status_code=400)

            pages, errors = await crawl_website(url, max_depth, fast=fast, max_pages=max_pages)

            # Simple page-by-page response — no chunks, no links noise
            results = []
            for page in pages:
                text = clean_content(page.raw_html, page.url)
                results.append({
                    "url":     page.url,
                    "title":   page.title,
                    "content": text,
                })

            return JSONResponse({
                "root_url":      url,
                "pages_crawled": len(results),
                "errors":        errors,
                "pages":         results,
            })
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    async def api_health(request: Request):
        """GET /api/health - check server is running"""
        return JSONResponse({"status": "ok", "server": settings.mcp_server_name})

    starlette_app = Starlette(
        routes=[
            # MCP SSE transport
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
            # Plain REST API (for Postman)
            Route("/api/health",           endpoint=api_health,           methods=["GET"]),
            Route("/api/scrape",           endpoint=api_scrape,           methods=["POST"]),
            Route("/api/crawl",            endpoint=api_crawl,            methods=["POST"]),
            Route("/api/scrape-full-site", endpoint=api_scrape_full_site, methods=["POST"]),
        ]
    )

    logger.info(
        "Starting %s v%s (SSE + REST API) on http://%s:%d",
        settings.mcp_server_name, settings.mcp_server_version, host, port,
    )
    logger.info("REST endpoints: /api/health | /api/scrape | /api/crawl | /api/scrape-full-site")
    config = uvicorn.Config(starlette_app, host=host, port=port, log_level=settings.log_level.lower())
    await uvicorn.Server(config).serve()


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Website Scraper MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP transport mode (default: stdio)",
    )
    parser.add_argument("--host", default="0.0.0.0", help="SSE server host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="SSE server port (default: 8000)")
    args = parser.parse_args()

    if args.transport == "sse":
        asyncio.run(run_sse(args.host, args.port))
    else:
        asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
