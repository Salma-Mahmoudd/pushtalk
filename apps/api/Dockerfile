# One image for the API and the one-off migration job (different commands in compose).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.12.22 /uv /bin/uv

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

RUN useradd --system --uid 10001 --no-create-home pushtalk
USER pushtalk

EXPOSE 8000
# Proxy headers: nginx passes the real client address (used for logs and per-IP limits).
CMD ["uvicorn", "pushtalk.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
