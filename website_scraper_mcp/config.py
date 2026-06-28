"""
config.py - Central configuration using Pydantic Settings and environment variables.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
  # pyrefly: ignore [missing-import]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Playwright ─────────────────────────────────────────────────────────────
    playwright_timeout_ms: int = 60_000   # 60s for heavy JS sites like Atlassian
    playwright_headless: bool = True

    # ── Crawler ────────────────────────────────────────────────────────────────
    max_crawl_depth: int = 1             # default depth 1
    max_pages_per_site: int = 30         # default 20 pages (fast response)
    crawl_delay_seconds: float = 0.1     # minimal delay

    # ── Chunking ───────────────────────────────────────────────────────────────
    chunk_size: int = 1_000
    chunk_overlap: int = 200

    # ── HTTP client ────────────────────────────────────────────────────────────
    request_timeout_seconds: int = 30
    user_agent: str = (
        "Mozilla/5.0 (compatible; WebScraperMCP/1.0)"
    )

    # ── Server ─────────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    mcp_server_name: str = "website-scraper-mcp"
    mcp_server_version: str = "1.0.0"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
