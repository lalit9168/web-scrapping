"""
tools/clean.py - Strip noise from raw HTML, return readable plain text.

Pipeline:
  1. Trafilatura (primary) — production-grade readability extraction.
  2. BeautifulSoup fallback — manual noise-tag removal + body text.
  3. Whitespace normalisation.
"""

from __future__ import annotations

import logging
import re

import trafilatura
from bs4 import BeautifulSoup, Comment

logger = logging.getLogger(__name__)

# Tags whose entire subtrees should be removed
_NOISE_TAGS = [
    "script", "style", "noscript",
    "nav", "footer", "header",
    "aside", "form", "button",
    "svg", "canvas", "iframe",
    "figure",                       # often decorative images only
]

# Regex to match ad/cookie/nav class or id names
_NOISE_RE = re.compile(
    r"(nav|navbar|menu|sidebar|footer|header|cookie|banner|popup|modal"
    r"|advertisement|advert|\bad\b|ads|promo|overlay|breadcrumb"
    r"|pagination|share|social|subscribe|newsletter|related|recommended)",
    re.IGNORECASE,
)


def _bs4_fallback(html: str) -> str:
    """BS4-based noise removal and text extraction."""
    soup = BeautifulSoup(html, "lxml")

    # Remove HTML comments
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()

    # Remove noisy tags
    for tag in _NOISE_TAGS:
        for node in soup.find_all(tag):
            node.decompose()

    # Remove noisy class/id nodes
    for node in soup.find_all(True):
        classes = " ".join(node.get("class") or [])
        node_id = node.get("id") or ""
        if _NOISE_RE.search(classes) or _NOISE_RE.search(node_id):
            node.decompose()

    # Prefer <main> or <article>
    main = soup.find("main") or soup.find("article") or soup.body or soup
    return main.get_text(separator="\n", strip=True)


def _normalise(text: str) -> str:
    """Collapse excessive whitespace."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── Public API ─────────────────────────────────────────────────────────────────

def clean_content(html: str, url: str = "") -> str:
    """
    Clean raw HTML and return readable plain text.

    Args:
        html: Raw HTML string.
        url:  Original page URL (helps Trafilatura resolve relative links).

    Returns:
        Clean plain-text string (may be empty if page had no readable content).
    """
    if not html or not html.strip():
        return ""

    # ── Trafilatura primary ──────────────────────────────────────────────────
    extracted = trafilatura.extract(
        html,
        url=url or None,
        include_tables=True,
        include_links=False,
        include_comments=False,
        no_fallback=False,
        favor_recall=True,
    )

    if extracted and len(extracted.strip()) > 80:
        logger.debug("[clean] trafilatura: %d chars", len(extracted))
        return _normalise(extracted)

    # ── BS4 fallback ─────────────────────────────────────────────────────────
    logger.debug("[clean] falling back to BS4 for %s", url)
    fallback = _bs4_fallback(html)
    result = _normalise(fallback)
    logger.debug("[clean] bs4: %d chars", len(result))
    return result
