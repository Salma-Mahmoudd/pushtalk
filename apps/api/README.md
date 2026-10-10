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
| `uv run celery -A pushtalk.worker.celery_app worker -Q audio` | Worker for voice messages (needs ffmpeg and Redis) |
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
  messages/       Voice messages (see specs/chat/plan.md, Phase 3)
    models.py     messages: status, seq, duration, waveform, file keys
    service.py    Upload: membership, size, sniffed type, real duration, idempotent client id
    processing.py Worker job: Opus/OGG, duration, waveform, seq, broadcast; failures tell the sender
    router.py     Upload (202), history pages, protected audio (members only, Range support)
  worker/         Celery app (Redis broker, queue "audio", acks late) and the retrying task
  channels/       Channels, membership and presence (see specs/chat/plan.md)
    models.py     channels, channel_members
    presence.py   Online users: one expiring Redis entry per connection
    service.py    Create, list, join, members; membership checks
    router.py     /api/channels endpoints
  realtime/       WebSockets
    router.py     /ws/channels/{id}: cookie auth (4401), membership (4403), presence, ping
    manager.py    This process's sockets and their Redis pub/sub subscriptions
    bus.py        Event envelope and publishing to Redis topics
    sweeper.py    Announces users whose connections stopped sending heartbeats
  auth/           Sign up, log in, refresh, log out, /me (see specs/auth/plan.md)
    models.py     users, refresh_tokens
    schemas.py    Request and response bodies
    repository.py Database access for users and refresh tokens
    service.py    Rules: hashing, rotation, reuse detection, logout
    router.py     /api/auth endpoints; a failed refresh clears the cookies
    deps.py       get_current_user: the guard for protected endpoints
  core/
    config.py     Settings from environment variables (see ../../.env.example)
    logging.py    JSON logs to stdout for structlog and uvicorn
    errors.py     AppError and the error envelope for every non-2xx response
    middleware.py Request id + request log; Origin check (CSRF) for unsafe requests and WebSockets
    security.py   argon2id passwords, JWT access tokens, refresh tokens, auth cookies
    deps.py       Request dependencies: settings, database session, Redis, rate limiter
  db/
    base.py       Declarative Base with constraint naming rules (used by Alembic)
    models.py     Imports every model so Alembic sees all tables
    session.py    Async SQLAlchemy engine
  infra/
    redis.py      Async Redis client
    rate_limit.py Redis sliding-window rate limiter (429 + Retry-After)
    storage.py    Media files on disk (a Docker volume shared by api and worker)
    audio.py      ffprobe/ffmpeg: type sniffing, real duration, Opus conversion, waveform peaks
migrations/       Alembic (async template); env.py reads DATABASE_URL
tests/            pytest suite; database tests use a migrated `pushtalk_test` database
                  (each test rolled back) and are skipped when PostgreSQL is not running
```

Every error response has the same shape:

```json
{ "error": { "code": "validation_error", "message": "Some fields are invalid.", "details": [{ "field": "size", "message": "Field required" }] }, "request_id": "3c53212a69c44137a1eaf66ba0e94d9b" }
```

Feature folders (`auth/`, `channels/`, `messages/`, …) are added phase by phase, following [`../../specs/app-arch/monorepo-decision.md`](../../specs/app-arch/monorepo-decision.md).
