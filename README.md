# Website Scraper MCP Server

A **production-ready MCP (Model Context Protocol) server** that allows any MCP-compatible AI agent to scrape websites, crawl internal pages, clean content, chunk it, and index everything into **Azure AI Search** — all through a clean, typed tool interface.

---

## Table of Contents

- [Architecture](#architecture)
- [Tools](#tools)
- [Installation](#installation)
- [Running Locally](#running-locally)
- [Running with Docker](#running-with-docker)
- [Environment Variables](#environment-variables)
- [Sample MCP Client](#sample-mcp-client)
- [Example API Requests](#example-api-requests)

---

## Architecture

```
website_scraper_mcp/
├── app.py                   ← Entry point (stdio / SSE transport)
├── server.py                ← MCP server + tool dispatcher
├── config.py                ← Pydantic Settings (env vars)
├── models.py                ← Input/Output Pydantic models
└── tools/
    ├── scrape.py            ← Tool 1 – static/dynamic detection + scraping
    ├── crawl.py             ← Tool 2 – BFS crawler, robots.txt aware
    ├── clean.py             ← Tool 3 – Trafilatura + BS4 content cleaning
    ├── chunk.py             ← Tool 4 – sliding window chunking
    └── azure_ai_search.py   ← Tools 5 & 7 – index + search
```

---

## Tools

| # | Tool | Description |
|---|------|-------------|
| 1 | `scrape_website` | Detect static/dynamic, scrape title/content/links |
| 2 | `crawl_website` | BFS crawl with depth limit + robots.txt |
| 3 | `clean_content` | Strip noise HTML, return readable text |
| 4 | `chunk_content` | Sliding window chunks (~1 000 chars, 200 overlap) |
| 5 | `index_to_ai_search` | Upload chunks to Azure AI Search |
| 6 | `index_website` | End-to-end pipeline: crawl → clean → chunk → index |
| 7 | `search_index` | Full-text search on the Azure AI Search index |

---

## Installation

### Prerequisites

- Python 3.11+
- Azure AI Search service (free tier works for testing)

### Steps

```bash
# 1. Clone the repo
git clone https://github.com/your-org/website-scraper-mcp.git
cd website-scraper-mcp

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Playwright browsers (Chromium)
playwright install chromium

# 5. Copy and fill environment variables
cp .env.example .env
# Edit .env with your Azure credentials
```

---

## Running Locally

### stdio mode (default — for MCP clients / AI agents)

```bash
python -m website_scraper_mcp.app
# or
python -m website_scraper_mcp.app --transport stdio
```

### SSE mode (HTTP endpoint for browser-based / HTTP clients)

```bash
python -m website_scraper_mcp.app --transport sse --port 8000
# Server available at http://localhost:8000/sse
```

---

## Running with Docker

```bash
# Build and start in SSE mode
docker compose up --build

# Stop
docker compose down
```

The container exposes port **8000** for SSE transport.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AZURE_SEARCH_ENDPOINT` | *(required)* | Azure AI Search service URL |
| `AZURE_SEARCH_KEY` | *(required)* | Admin API key |
| `AZURE_SEARCH_INDEX_NAME` | `website-content` | Target index name |
| `PLAYWRIGHT_TIMEOUT_MS` | `30000` | Playwright page load timeout (ms) |
| `PLAYWRIGHT_HEADLESS` | `true` | Run Chromium headless |
| `MAX_CRAWL_DEPTH` | `2` | Maximum crawl depth |
| `MAX_PAGES_PER_SITE` | `100` | Hard cap on pages per crawl |
| `CRAWL_DELAY_SECONDS` | `0.5` | Polite delay between requests |
| `CHUNK_SIZE` | `1000` | Characters per chunk |
| `CHUNK_OVERLAP` | `200` | Overlap between consecutive chunks |
| `LOG_LEVEL` | `INFO` | Python logging level |

---

## Sample MCP Client

Run the included example after starting the server in SSE mode:

```bash
python examples/mcp_client_example.py
```

Or configure it in your MCP-compatible agent (e.g. Claude Desktop `mcp_config.json`):

```json
{
  "mcpServers": {
    "website-scraper": {
      "command": "python",
      "args": ["-m", "website_scraper_mcp.app", "--transport", "stdio"],
      "cwd": "/path/to/website-scraper-mcp",
      "env": {
        "AZURE_SEARCH_ENDPOINT": "https://your-service.search.windows.net",
        "AZURE_SEARCH_KEY": "your-key",
        "AZURE_SEARCH_INDEX_NAME": "website-content"
      }
    }
  }
}
```

---

## Example API Requests

### Via MCP client (Python SDK)

```python
import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client

async def demo():
    async with sse_client("http://localhost:8000/sse") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Scrape a single page
            result = await session.call_tool("scrape_website", {"url": "https://example.com"})
            print(result)

            # Full pipeline
            result = await session.call_tool("index_website", {
                "url": "https://example.com",
                "max_depth": 2
            })
            print(result)

            # Search
            result = await session.call_tool("search_index", {
                "query": "What services does the company provide?",
                "top": 5
            })
            print(result)

asyncio.run(demo())
```

### Tool input/output examples

**scrape_website**
```json
// Input
{"url": "https://example.com"}

// Output
{
  "title": "Example Domain",
  "url": "https://example.com",
  "content": "This domain is for use in illustrative examples...",
  "links": ["https://www.iana.org/domains/example"],
  "is_dynamic": false,
  "metadata": {"description": "..."}
}
```

**index_website**
```json
// Input
{"url": "https://example.com", "max_depth": 2}

// Output
{
  "url": "https://example.com",
  "pages_crawled": 4,
  "total_chunks": 38,
  "indexed_documents": 38,
  "failed_documents": 0,
  "status": "success",
  "errors": []
}
```

**search_index**
```json
// Input
{"query": "What services does the company provide?", "top": 5}

// Output
{
  "query": "What services does the company provide?",
  "total_results": 3,
  "hits": [
    {
      "id": "abc123",
      "url": "https://example.com/services",
      "title": "Our Services",
      "content": "We provide cloud, AI, and data services...",
      "chunk_number": 0,
      "score": 9.8
    }
  ]
}
```

---

## Error Handling

The server handles all errors gracefully and returns structured JSON error responses:

```json
{
  "error": "HTTP 404 when fetching https://example.com/missing",
  "tool": "scrape_website"
}
```

Handled errors include: invalid URLs, HTTP 4xx/5xx, timeouts, Playwright failures, Azure Search quota errors, network issues, and duplicate document IDs.

---

## License

MIT
