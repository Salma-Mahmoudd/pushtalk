# PushTalk API

FastAPI app and Celery workers, packaged as `pushtalk` (`src/pushtalk/`) and managed with [uv](https://docs.astral.sh/uv/).

## Commands

Run from `apps/api/` (uv and Python versions: see [`../../steps/environment-setup.md`](../../steps/environment-setup.md)).

| Command | What it does |
| --- | --- |
| `uv sync` | Create `.venv` and install dependencies from `uv.lock` |
| `uv run uvicorn pushtalk.main:app --reload` | Development server on <http://localhost:8000> (API docs at `/api/docs`) |
| `uv run pytest` | Tests (integration tests are skipped when PostgreSQL or Redis is not running) |
| `uv run pytest -m "not integration"` | Unit tests only, no services needed |
| `uv run alembic upgrade head` | Apply database migrations |
| `uv run alembic revision --autogenerate -m "add users"` | Create a migration from model changes |
| `uv run ruff check .` | Lint |
| `uv run ruff format .` | Format |
| `uv run mypy` | Strict type check of `src/` and `tests/` |

## Services

PostgreSQL and Redis run in Docker. From the repository root:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

The API reads `DATABASE_URL` and `REDIS_URL` (defaults match those containers; see [`../../.env.example`](../../.env.example)). `GET /api/health` reports both.

## Layout

```text
src/pushtalk/
  main.py         App factory (create_app): logging, error handlers, middleware, routers
  health.py       GET /api/health: checks PostgreSQL and Redis (503 + details if one is down)
  core/
    config.py     Settings from environment variables (see ../../.env.example)
    logging.py    JSON logs to stdout for structlog and uvicorn
    errors.py     AppError and the error envelope for every non-2xx response
    middleware.py Request id + request log; Origin check (CSRF) for unsafe requests and WebSockets
  db/
    base.py       Declarative Base with constraint naming rules (used by Alembic)
    session.py    Async SQLAlchemy engine
  infra/
    redis.py      Async Redis client
migrations/       Alembic (async template); env.py reads DATABASE_URL
tests/            pytest suite; tests/integration/ uses the real PostgreSQL and Redis
```

Every error response has the same shape:

```json
{ "error": { "code": "validation_error", "message": "Some fields are invalid.", "details": [{ "field": "size", "message": "Field required" }] }, "request_id": "3c53212a69c44137a1eaf66ba0e94d9b" }
```

Feature folders (`auth/`, `channels/`, `messages/`, …) are added phase by phase, following [`../../specs/app-arch/monorepo-decision.md`](../../specs/app-arch/monorepo-decision.md).
