"""
examples/mcp_client_example.py - Sample MCP client exercising all 5 tools.

Start the server first:
    python -m website_scraper_mcp.app --transport sse --port 8000

Then run this script in a second terminal:
    python examples/mcp_client_example.py
"""

from __future__ import annotations

import asyncio
import json

from mcp import ClientSession
from mcp.client.sse import sse_client

SERVER_URL = "http://localhost:8000/sse"
TARGET_URL = "https://example.com"


async def call(session: ClientSession, tool: str, **kwargs) -> None:
    print(f"\n{'=' * 70}")
    print(f"TOOL : {tool}")
    print(f"INPUT: {json.dumps(kwargs, indent=2)}")
    print("-" * 70)
    result = await session.call_tool(tool, kwargs)
    for content in result.content:
        try:
            data = json.loads(content.text)
            print(json.dumps(data, indent=2)[:3000])
        except Exception:
            print(content.text[:3000])


async def main() -> None:
    async with sse_client(SERVER_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # ── Tool 1: Scrape a single page ──────────────────────────────────
            await call(session, "scrape_website", url=TARGET_URL)

            # ── Tool 2: Crawl the entire site (shallow) ───────────────────────
            await call(session, "crawl_website", url=TARGET_URL, max_depth=1)

            # ── Tool 3: Clean a small HTML snippet ───────────────────────────
            html_snippet = (
                "<html><body>"
                "<nav>Skip nav</nav>"
                "<main><h1>Hello World</h1><p>This is the main content.</p>"
                "<table><tr><td>Cell 1</td><td>Cell 2</td></tr></table></main>"
                "<footer>Footer text</footer>"
                "</body></html>"
            )
            await call(session, "clean_content", html=html_snippet, url=TARGET_URL)

            # ── Tool 4: Chunk some text ───────────────────────────────────────
            long_text = "This is sample content. " * 100
            await call(session, "chunk_content",
                       text=long_text,
                       url=TARGET_URL,
                       title="Sample Page")

            # ── Tool 5: Full pipeline — crawl + clean + chunk ─────────────────
            await call(session, "scrape_full_site",
                       url=TARGET_URL,
                       max_depth=1,
                       clean=True,
                       chunk=True)


if __name__ == "__main__":
    asyncio.run(main())
