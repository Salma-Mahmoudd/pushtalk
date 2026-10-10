# Two images from one file:
#   api          the API, the audio worker, Flower and the one-off migration job (default)
#   transcriber  the speech-to-text worker: adds faster-whisper and a model baked in at build time
FROM python:3.12-slim AS base

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
# No dependency groups: dev tools stay out, and only the transcriber adds "transcribe".
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-default-groups --no-install-project

COPY README.md alembic.ini ./
COPY migrations ./migrations
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-default-groups

# The media folder is created here so a new Docker volume starts owned by the app user.
RUN useradd --system --uid 10001 --no-create-home pushtalk \
    && mkdir -p /data/media && chown pushtalk /data/media


FROM base AS transcriber

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-default-groups --group transcribe

# The default model is downloaded now, so the first `docker compose up` needs no download.
# Other sizes (WHISPER_MODEL) are fetched into the same folder on first use.
ARG WHISPER_MODEL=base
ENV WHISPER_MODEL_DIR=/models \
    HF_HOME=/tmp/huggingface
RUN mkdir -p /models \
    && python -c "from faster_whisper.utils import download_model; download_model('${WHISPER_MODEL}', cache_dir='/models')" \
    && chown -R pushtalk /models

USER pushtalk
CMD ["celery", "-A", "pushtalk.worker.celery_app", "worker", "-Q", "transcribe", \
     "--concurrency", "1", "--loglevel", "INFO"]


FROM base AS api

USER pushtalk
EXPOSE 8000
# Proxy headers: nginx passes the real client address (used for logs and per-IP limits).
CMD ["uvicorn", "pushtalk.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
