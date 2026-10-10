# One image for the API, the Celery worker, Flower and the one-off migration job.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.12.22 /uv /bin/uv
# ffmpeg and ffprobe as static binaries (Opus included): upload checks and audio processing.
COPY --from=mwader/static-ffmpeg:9.0.2 /ffmpeg /ffprobe /usr/local/bin/

WORKDIR /app

# Dependencies first: this layer is reused until pyproject.toml or uv.lock change.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY README.md alembic.ini ./
COPY migrations ./migrations
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# The media folder is created here so a new Docker volume starts owned by the app user.
RUN useradd --system --uid 10001 --no-create-home pushtalk \
    && mkdir -p /data/media && chown pushtalk /data/media
USER pushtalk

EXPOSE 8000
# Proxy headers: nginx passes the real client address (used for logs and per-IP limits).
CMD ["uvicorn", "pushtalk.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
