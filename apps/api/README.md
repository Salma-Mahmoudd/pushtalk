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
    receipts.py   Delivered/played reports, counts per message, per-recipient details (sender only)
    router.py     Upload (202), history pages, protected audio (members only, Range support), receipts
  directs/        Direct messages: one channel of kind "direct" per pair of users (dm_key)
    repository.py Race-safe get-or-create (INSERT ... ON CONFLICT on dm_key), list, user search
    service.py    Open (201 new / 200 existing), list with the peer's online state, dm.created
    router.py     GET /api/users?query=, GET and POST /api/dms
  transcription/  Speech to text after a message is ready (queue "transcribe")
    transcribers.py Providers: local faster-whisper, OpenAI; get_transcriber picks one from settings
    job.py        Saves the transcript (or "failed") and publishes message.transcribed
  worker/         Celery app (Redis broker, queues "audio" and "transcribe", acks late) and the tasks
  channels/       Channels, membership and presence (see specs/chat/plan.md)
    models.py     channels, channel_members
    presence.py   Online users: one expiring Redis entry per connection
    service.py    Create, list, join, members; membership checks
    router.py     /api/channels endpoints
  realtime/       WebSockets
    router.py     /ws/channels/{id}: cookie auth (4401), membership (4403), presence, ping,
                  catch-up (since_seq), receipts, playback claims, event rate limit
                  /ws/me: the user's app-wide socket (dm.created, "online anywhere" presence)
    players.py    Which of a user's connections plays a channel (one playing tab per user)
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

## Transcription

Every ready message is transcribed by a second Celery step, after `message.ready` is broadcast, so playback never waits for it. The `transcriber` service (image target `transcriber` in the [`Dockerfile`](Dockerfile)) serves the `transcribe` queue one job at a time; the API and audio worker image stays without the speech libraries.

| `TRANSCRIBE_PROVIDER` | What happens |
| --- | --- |
| `local` (default) | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) on the CPU (int8). The `base` model is downloaded when the image is built, so the first `docker compose up` works offline. `WHISPER_MODEL=small` (or `tiny`, `medium`, `large-v3`) is fetched into the `whisper-models` volume on first use; set it before building to bake it into the image instead. |
| `openai` | OpenAI's transcription endpoint (`OPENAI_TRANSCRIBE_MODEL`, default `gpt-4o-mini-transcribe`). Needs `OPENAI_API_KEY`; the API refuses to start without it. The audio leaves the server. |
| `off` | No transcription step; messages carry no transcript. |

`TRANSCRIBE_LANGUAGE` (for example `en` or `ar`) fixes the language; empty detects it per message. A job is retried twice, then the transcript is marked `failed` and the message stays playable. Messages carry `transcript_status` (`pending`, `done`, `failed`), `transcript` and `transcript_lang`; the channel gets `message.transcribed` when the text is ready. Locally, `uv sync` installs the `transcribe` group too, so tests and mypy cover it.

## Direct messages

A conversation between two users is a channel of kind `direct`, so voice messages, history, receipts, transcripts and the channel WebSocket work unchanged. `dm_key` (`"<smaller id>:<larger id>"`) is unique: two people opening the same conversation at the same moment get one channel. Direct channels are never listed in `GET /api/channels` and cannot be joined; to anyone outside the pair they answer 404, as if they did not exist.

## Rate limits

Redis sliding windows shared by every API process (`infra/rate_limit.py`); a refused request gets **429** `rate_limited` with a `Retry-After` header. Each rule is a `"<requests>/<seconds>"` setting in [`../../.env.example`](../../.env.example).

| Action | Default | Counted per |
| --- | --- | --- |
| Log in | 10 / 15 min and 30 / 15 min | username, and client IP |
| Sign up | 5 / hour | client IP |
| Upload a voice message | 20 / minute and 200 / day | user |
| Create a channel | 10 / hour | user |
| Open a direct conversation | 10 / minute | user |
| WebSocket events from the client | 30 / second | connection (in memory); the excess is dropped with an `error` event |

Client IPs come from `X-Forwarded-For`, set by nginx; uvicorn trusts it (`--proxy-headers`) because only nginx reaches the API. A receipt event can carry up to 200 `message_ids`, so a catch-up stays far below the event limit.

Every error response has the same shape:

```json
{ "error": { "code": "validation_error", "message": "Some fields are invalid.", "details": [{ "field": "size", "message": "Field required" }] }, "request_id": "3c53212a69c44137a1eaf66ba0e94d9b" }
```

Feature folders (`auth/`, `channels/`, `messages/`, …) are added phase by phase, following [`../../specs/app-arch/monorepo-decision.md`](../../specs/app-arch/monorepo-decision.md).
