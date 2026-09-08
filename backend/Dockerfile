# DarkNexus backend.
#
# Two things this image exists to solve, beyond "run the Python":
#
#   * Tesseract, with the Punjabi language pack. OCR is the only route by
#     which a phone number written on a photograph reaches the analyser, and
#     on a developer machine it is usually missing - pytesseract installs
#     cleanly while the engine it drives does not, so every image silently
#     returns no text. Installing it here means a container never has that gap.
#
#   * Playwright's Chromium. The surface scraper prefers a real browser and
#     falls back to plain HTTP, so without it the application still runs but
#     collects less from script-rendered pages. It costs roughly 450 MB; the
#     lean build argument below turns it off for deployments that only ever
#     touch Tor and Telegram.
#
# Tor is deliberately NOT installed here. It runs as its own service (see
# docker-compose.yml) so the collector and the anonymity layer can be
# restarted, and have their circuits rotated, independently.

FROM python:3.10-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set to "false" to skip the browser download and its dependencies.
ARG INSTALL_BROWSER=true

WORKDIR /app

# ── System packages ──────────────────────────────────────────────────
# tesseract-ocr-pan is the Punjabi pack: the intelligence this system is
# built to read is frequently written in Gurmukhi, and the English-only
# engine returns nothing useful for it.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-pan \
        tesseract-ocr-hin \
        libmagic1 \
        curl \
        # WeasyPrint renders the Section 65B certificates.
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libffi-dev \
        shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ──────────────────────────────────────────────
# Copied on their own so a source edit does not invalidate this layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Headless browser (optional) ──────────────────────────────────────
# Installed to a shared path rather than the installing user's home. This step
# runs as root, so Playwright's default location is /root/.cache - unreadable
# by the unprivileged user the container actually runs as. Playwright would
# then find no browser and fall back to plain HTTP silently, which looks like
# a scraper that merely collects less rather than a broken image.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN if [ "$INSTALL_BROWSER" = "true" ]; then \
        playwright install --with-deps chromium \
        && chmod -R a+rX /ms-playwright; \
    else \
        mkdir -p /ms-playwright \
        && echo "Skipping Chromium; the surface scraper will use plain HTTP only."; \
    fi

# ── Application ──────────────────────────────────────────────────────
COPY . .

# Evidence, embeddings and generated reports are mounted as volumes in
# compose. Created here so the image also runs standalone without them.
RUN mkdir -p /app/evidence_media /app/chroma_data /app/reports

# The application writes to these paths, so it cannot run as root-only.
RUN useradd --create-home --uid 10001 darknexus \
    && chown -R darknexus:darknexus /app
USER darknexus

EXPOSE 8000

# Reports the application's own health check, not merely that the port is
# open - a process that is listening but failed to reach its database is
# not healthy, and restarting it is the correct response.
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
