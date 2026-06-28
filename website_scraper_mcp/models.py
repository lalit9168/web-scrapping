"""
models.py - Pydantic v2 models for all MCP tool inputs and outputs.
No Azure AI Search references.
"""

from typing import Any
from pydantic import BaseModel, Field


# ══════════════════════════════════════════════════════════════════════════════
# Inputs
# ══════════════════════════════════════════════════════════════════════════════

class ScrapeInput(BaseModel):
    """Input for scraping a single page."""
    url: str = Field(..., description="The website URL to scrape.")


class CrawlInput(BaseModel):
    """Input for crawling an entire website."""
    url: str = Field(..., description="Root URL to start crawling from.")
    max_depth: int = Field(2, ge=1, le=10, description="Maximum crawl depth.")


class CleanInput(BaseModel):
    """Input for cleaning raw HTML."""
    html: str = Field(..., description="Raw HTML content to clean.")
    url: str = Field("", description="Optional source URL for context.")


class ChunkInput(BaseModel):
    """Input for splitting text into overlapping chunks."""
    text: str = Field(..., description="Clean text to split into chunks.")
    url: str = Field("", description="Source URL to embed in chunk metadata.")
    title: str = Field("", description="Page title to embed in chunk metadata.")


class ScrapeFullSiteInput(BaseModel):
    """Input for the end-to-end scrape-all-pages pipeline."""
    url: str = Field(..., description="Root website URL.")
    max_depth: int = Field(2, ge=1, le=10, description="Maximum crawl depth.")
    clean: bool = Field(True, description="Whether to clean extracted content.")
    chunk: bool = Field(False, description="Whether to split content into chunks.")


# ══════════════════════════════════════════════════════════════════════════════
# Outputs
# ══════════════════════════════════════════════════════════════════════════════

class ScrapeResult(BaseModel):
    """Result for a single scraped page."""
    title: str
    url: str
    content: str                          # clean text
    raw_html: str                         # original HTML (truncated in API responses)
    links: list[str]
    is_dynamic: bool
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str = ""                       # non-empty if scraping failed


class ChunkItem(BaseModel):
    """A single text chunk."""
    id: str
    chunk: str
    chunk_number: int
    url: str = ""
    title: str = ""


class PageResult(BaseModel):
    """Scraped + optionally cleaned/chunked result for one page."""
    url: str
    title: str
    content: str                          # clean text
    is_dynamic: bool
    links: list[str]
    chunks: list[ChunkItem] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str = ""


class ScrapeFullSiteResult(BaseModel):
    """Result of the full-site scrape pipeline."""
    root_url: str
    pages_crawled: int
    total_chunks: int
    pages: list[PageResult]
    errors: list[dict[str, str]] = Field(default_factory=list)
