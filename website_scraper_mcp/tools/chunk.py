"""
tools/chunk.py - Split clean text into overlapping chunks with deterministic IDs.
"""

from __future__ import annotations

import hashlib
import logging

from website_scraper_mcp.config import get_settings
from website_scraper_mcp.models import ChunkItem

logger = logging.getLogger(__name__)
settings = get_settings()


def _chunk_id(url: str, index: int, text_snippet: str) -> str:
    """SHA-256 based deterministic ID (first 32 hex chars)."""
    raw = f"{url}::{index}::{text_snippet[:64]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def chunk_content(
    text: str,
    url: str = "",
    title: str = "",
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[ChunkItem]:
    """
    Split *text* into overlapping chunks.

    Args:
        text:          Clean plain text to chunk.
        url:           Source URL embedded in each chunk.
        title:         Page title embedded in each chunk.
        chunk_size:    Characters per chunk (default: settings.chunk_size).
        chunk_overlap: Overlap characters between chunks (default: settings.chunk_overlap).

    Returns:
        List of ChunkItem objects.
    """
    size = chunk_size if chunk_size is not None else settings.chunk_size
    overlap = chunk_overlap if chunk_overlap is not None else settings.chunk_overlap

    if not text or not text.strip():
        logger.warning("[chunk] Empty text – no chunks produced")
        return []

    if size <= overlap:
        raise ValueError(
            f"chunk_size ({size}) must be greater than chunk_overlap ({overlap})"
        )

    chunks: list[ChunkItem] = []
    start = 0
    index = 0

    while start < len(text):
        end = min(start + size, len(text))
        piece = text[start:end].strip()
        if piece:
            chunks.append(
                ChunkItem(
                    id=_chunk_id(url, index, piece),
                    chunk=piece,
                    chunk_number=index,
                    url=url,
                    title=title,
                )
            )
            index += 1
        start += size - overlap

    logger.info("[chunk] %d chunks  size=%d  overlap=%d  url=%s",
                len(chunks), size, overlap, url)
    return chunks
