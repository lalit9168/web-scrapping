"""
Full site scrape - crawls ALL pages, cleans content, saves to JSON file.
No chunking, no indexing. Pure scraped data ready for later use.

Usage: python test_scrape.py
"""

import asyncio
import sys
import json
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

from website_scraper_mcp.tools.crawl import crawl_website
from website_scraper_mcp.tools.clean import clean_content

# ========================================================
TARGET_URL = "https://www.ilink-digital.com"  # root URL to scrape
MAX_DEPTH  = 1                              # depth 1 = fast (only homepage links)
OUTPUT_FILE = "scraped_data.json"          # output file
# ========================================================

async def main():
    print("=" * 70)
    print(f"SCRAPING: {TARGET_URL}")
    print(f"Depth: {MAX_DEPTH} | Output: {OUTPUT_FILE}")
    print("=" * 70)

    # Step 1 — Crawl all pages
    print("\n[1/2] Crawling all internal pages...")
    pages, errors = await crawl_website(TARGET_URL, MAX_DEPTH)
    print(f"      Found {len(pages)} pages | {len(errors)} errors")

    # Step 2 — Clean each page and collect data
    print("\n[2/2] Cleaning content from each page...")
    results = []
    for i, page in enumerate(pages, 1):
        text = clean_content(page.raw_html, page.url)
        results.append({
            "url":        page.url,
            "title":      page.title,
            "is_dynamic": page.is_dynamic,
            "content":    text,
            "links":      page.links,
            "metadata":   page.metadata,
        })
        print(f"  [{i}/{len(pages)}] {page.title or page.url} ({len(text)} chars)")

    # Step 3 — Save to JSON
    output = {
        "scraped_at":    datetime.now().isoformat(),
        "root_url":      TARGET_URL,
        "total_pages":   len(results),
        "errors":        errors,
        "pages":         results,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 70)
    print(f"DONE!")
    print(f"  Pages scraped : {len(results)}")
    print(f"  Errors        : {len(errors)}")
    print(f"  Saved to      : {OUTPUT_FILE}")
    print("=" * 70)


asyncio.run(main())
