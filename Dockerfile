# Astrophotography Toolkit: container image for Google Cloud Run (also runs anywhere Docker does).
#
#   docker build -t astro-toolkit .
#   docker run --rm -p 8080:8080 astro-toolkit        # then open http://localhost:8080
#
# See docs/DEPLOY_CLOUD_RUN.md for deploying.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=8

WORKDIR /app

# Dependencies first, so code changes don't reinstall them.
COPY requirements.txt .
RUN pip install -r requirements.txt gunicorn==23.0.0

COPY app ./app
COPY static ./static
COPY scripts ./scripts

# Bake the solver index and the catalog sky map into the image, so a cold start only loads them.
RUN python scripts/prebuild.py /app/data/skymap.png

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

# Hosted settings (see app/settings.py). Cloud Run sets PORT.
ENV HOSTED=1 \
    SYNC_JOBS=1 \
    WARMUP_SYNC=1 \
    MAX_UPLOAD_MB=30 \
    ANALYZE_PER_10_MIN=20 \
    SKYMAP_PATH=/app/data/skymap.png \
    PORT=8080

EXPOSE 8080

# One process (jobs and the rate limiter live in memory), a few threads for concurrent requests.
# A photo solve takes a few seconds; the generous timeout covers very large frames.
CMD ["sh", "-c", "exec gunicorn --bind \":${PORT}\" --workers 1 --threads 4 --timeout 120 --graceful-timeout 20 --access-logfile - 'app:create_app()'"]
