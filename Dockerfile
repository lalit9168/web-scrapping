# ────────────────────────────────────────────────────────────────────────────────
# Stage 1 – Build image with Playwright browsers baked in
# ────────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

# System deps required by Playwright / lxml / BeautifulSoup
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libxml2-dev libxslt-dev \
    # Playwright system deps
    libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (Chromium only to keep image small)
RUN playwright install chromium --with-deps

# ────────────────────────────────────────────────────────────────────────────────
# Stage 2 – Copy application code
# ────────────────────────────────────────────────────────────────────────────────
COPY website_scraper_mcp/ ./website_scraper_mcp/
COPY examples/           ./examples/

# Expose SSE port (only needed for SSE transport mode)
EXPOSE 8000

# Default: SSE transport for deployment (agent connects via HTTP)
ENTRYPOINT ["python", "-m", "website_scraper_mcp.app"]
CMD ["--transport", "sse", "--host", "0.0.0.0", "--port", "8000"]
