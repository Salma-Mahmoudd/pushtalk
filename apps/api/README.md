# PushTalk API

FastAPI app and Celery workers, packaged as `pushtalk` (`src/pushtalk/`) and managed with [uv](https://docs.astral.sh/uv/).

## Commands

Run from `apps/api/` (uv and Python versions: see [`../../steps/environment-setup.md`](../../steps/environment-setup.md)).

| Command | What it does |
| --- | --- |
| `uv sync` | Create `.venv` and install dependencies from `uv.lock` |
| `uv run uvicorn pushtalk.main:app --reload` | Development server on <http://localhost:8000> (API docs at `/api/docs`) |
| `uv run pytest` | Tests |
| `uv run ruff check .` | Lint |
| `uv run ruff format .` | Format |
| `uv run mypy` | Strict type check of `src/` and `tests/` |

## Layout

```text
src/pushtalk/
  main.py         App factory (create_app): logging, error handlers, middleware, routers
  health.py       GET /api/health
  core/
    config.py     Settings from environment variables (see ../../.env.example)
    logging.py    JSON logs to stdout for structlog and uvicorn
    errors.py     AppError and the error envelope for every non-2xx response
    middleware.py Request id + request log; Origin check (CSRF) for unsafe requests and WebSockets
tests/            pytest suite (async tests run with pytest-asyncio)
```

Every error response has the same shape:

```json
{ "error": { "code": "validation_error", "message": "Some fields are invalid.", "details": [{ "field": "size", "message": "Field required" }] }, "request_id": "3c53212a69c44137a1eaf66ba0e94d9b" }
```

Feature folders (`auth/`, `channels/`, `messages/`, …) are added phase by phase, following [`../../specs/app-arch/monorepo-decision.md`](../../specs/app-arch/monorepo-decision.md).
