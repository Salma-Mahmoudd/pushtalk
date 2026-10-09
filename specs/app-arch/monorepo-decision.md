# Monorepo decision: TypeScript + Python in one repository

**Decision: a plain polyglot monorepo with no monorepo framework.** Each language uses its own native tool (pnpm for TypeScript, uv for Python). A root `Makefile` and `docker-compose.yml` tie them together.

---

## 1. What a monorepo is (and isn't)

A monorepo is **one Git repository that holds several deployable apps**. It does **not** require Nx, Turborepo, Bazel or any other special tool. Those tools add three things:

1. **Task orchestration**: "run `test` in every package, in dependency order."
2. **Caching**: "skip the build if nothing changed."
3. **Code sharing within one language**: "`web` imports `@pushtalk/ui`."

PushTalk has **two apps in two languages** and a short time box. The apps cannot import each other's code anyway: a Python service cannot `import` a TypeScript module. Most of what those tools offer has no use here, and they would add learning time and config files for reviewers to read.

## 2. The options

| Option | What it looks like | Pros | Cons | Verdict |
| --- | --- | --- | --- | --- |
| **A. Plain polyglot monorepo** (pnpm + uv + Makefile + compose) | `apps/web`, `apps/api`, root Makefile | No new concepts; each side uses its idiomatic tool; instantly readable; Docker does the real orchestration | No build caching (irrelevant at this size) | ✅ **Chosen** |
| B. Turborepo / pnpm workspaces for everything | `turbo.json`, Python wrapped in `package.json` scripts | Nice `turbo run test` | Python is not a first-class citizen; `uv`/`pytest` end up wrapped in npm scripts | ❌ |
| C. Nx with `@nxlv/python` plugin | `nx.json`, `project.json` per app | Real polyglot graph, caching | Steep learning curve, plugin magic, lots of config for 2 apps | ❌ (overkill) |
| D. Bazel / Pants | BUILD files | Hermetic, scales to thousands of packages | Days of setup | ❌ |
| E. Two separate repositories | `pushtalk-web`, `pushtalk-api` | Clean separation | The brief asks for **one** Git repository and one `docker compose up`; cross-cutting commits get split | ❌ |

**Rule of thumb:** add a monorepo framework when several packages **in the same language** depend on each other, or when CI time starts to hurt. Neither applies here, and one can be added later if that changes.

## 3. Chosen layout

```text
pushtalk/                            ← repository root
├── apps/
│   ├── api/                         ← one Python image: api · worker · transcriber · flower · migrate
│   │   ├── Dockerfile               ← targets: app, transcriber
│   │   ├── pyproject.toml  uv.lock  ← managed by uv (deps + ruff + mypy + pytest config)
│   │   ├── alembic.ini
│   │   ├── migrations/              ← env.py, versions/
│   │   ├── src/pushtalk/
│   │   │   ├── main.py              ← FastAPI app factory: middleware, error handlers, routers
│   │   │   ├── core/                ← config, logging, errors, security (JWT, cookies), deps
│   │   │   ├── db/                  ← declarative base, async session
│   │   │   ├── infra/               ← storage (MinIO), audio (ffprobe/ffmpeg), redis, rate_limit
│   │   │   ├── auth/                ← router · service · repository · models · schemas
│   │   │   ├── channels/            ← same 5 files + presence
│   │   │   ├── messages/            ← same 5 files + protected audio endpoint
│   │   │   ├── dms/                 ← same 5 files
│   │   │   ├── realtime/            ← WS routers, connection manager, Redis pub/sub bus, events
│   │   │   ├── transcription/       ← provider protocol, providers/local.py, providers/openai.py
│   │   │   └── worker/              ← celery_app, tasks/process_message, tasks/transcribe
│   │   └── tests/                   ← conftest.py, unit/, integration/
│   └── web/
│       ├── Dockerfile  nginx.conf   ← node build → nginx; proxies /api and /ws to api:8000
│       ├── package.json  pnpm-lock.yaml  vite.config.ts  tsconfig.json  eslint.config.js  components.json
│       └── src/
│           ├── main.tsx  App.tsx  router.tsx
│           ├── features/
│           │   ├── auth/            ← pages, api.ts, store.ts, session sync
│           │   ├── channels/        ← list, room, members/presence, message store
│           │   ├── voice/           ← Recorder, PlaybackQueue (+ tests), AudioPlayer, SpeedControl
│           │   └── dms/             ← DirectList, UserPicker, /ws/me client
│           ├── shared/
│           │   ├── ui/              ← shadcn/ui components
│           │   ├── lib/api/         ← ApiClient + generated schema.d.ts
│           │   └── lib/ws/          ← WsClient, backoff, event types
│           └── test/setup.ts
├── infra/                           ← minio-init.sh and anything not owned by one app
├── specs/                           ← plans + diagrams
├── steps/                           ← environment setup guide
├── docker-compose.yml  docker-compose.dev.yml
├── .env.example  .gitignore  .gitattributes  .editorconfig  .nvmrc  .python-version
├── Makefile                         ← the "monorepo task runner"
└── README.md  DECISIONS.md  AI_USAGE.md
```

**Rules that keep the boundaries clean:**

- Backend: inside a feature, router → service → repository → models. A service may call another feature's service, never its repository.
- Frontend: features import from `shared/`, never from another feature's internals.

### Why the worker lives inside `apps/api`

The worker needs the same SQLAlchemy models, settings, storage client and event bus as the API. As a separate app, that code would be either copied (and drift) or moved into a shared Python package (more packaging work). **One Python package with several entrypoints** is the standard FastAPI + worker pattern:

| Compose service | Command |
| --- | --- |
| `api` | `uvicorn pushtalk.main:app` |
| `worker` | `celery -A pushtalk.worker.celery_app worker -Q audio` |
| `transcriber` | `celery -A pushtalk.worker.celery_app worker -Q transcribe` (image target `transcriber`, adds faster-whisper) |
| `flower` | `celery -A pushtalk.worker.celery_app flower` |
| `migrate` | `alembic upgrade head` |

Compose starts the **same image** with a different `command:` for each.

### How TypeScript and Python stay in sync (the "shared contract")

FastAPI already generates an OpenAPI schema. The web app generates TypeScript types from it with `make types` (exports the schema from the app without starting a server, then runs `openapi-typescript` into `apps/web/src/shared/lib/api/schema.d.ts`).

The generated file is committed, so the web build does not need the API running. WebSocket events are not in OpenAPI, so they are hand-written as a TypeScript discriminated union in `shared/lib/ws/events.ts`, mirroring `pushtalk/realtime/events.py`. Both files stay short and side by side.

> Growth path: if a second TypeScript app appears (e.g. mobile or admin), the types move into `packages/contracts` with a `pnpm-workspace.yaml`. Not needed now.

## 4. Tooling cheat-sheet

| Concern | Python (`apps/api`) | TypeScript (`apps/web`) |
| --- | --- | --- |
| Scaffold | `uv init --package --name pushtalk` | `pnpm create vite --template react-ts`, `pnpm dlx shadcn@latest init` |
| Package manager | **uv** (`uv add fastapi`, `uv sync`, `uv run pytest`) | **pnpm** (`pnpm add`, `pnpm install`) |
| Lockfile | `uv.lock` | `pnpm-lock.yaml` |
| Lint/format | ruff (`ruff check`, `ruff format`) | eslint + prettier |
| Types | mypy `--strict` on `src/` | `tsc --noEmit` (strict) |
| Tests | pytest + pytest-asyncio + httpx `AsyncClient` | vitest |

Root `Makefile` (the only "monorepo glue"):

```make
up:        ; docker compose up --build
dev:       ; docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
down:      ; docker compose down
reset:     ; docker compose down -v          # wipe db + minio volumes
logs:      ; docker compose logs -f api worker transcriber
test:      test-api test-web
test-api:  ; cd apps/api && uv run pytest
test-web:  ; cd apps/web && pnpm vitest run
lint:      ; cd apps/api && uv run ruff check . && uv run mypy src && cd ../web && pnpm lint && pnpm tsc --noEmit
types:     ; ./infra/gen-types.sh
migration: ; docker compose run --rm migrate alembic revision --autogenerate -m "$(m)"
diagrams:  ; docker run --rm --user "$$(id -u):$$(id -g)" -e JAVA_TOOL_OPTIONS=-Duser.home=/tmp -v "$(CURDIR)":/work -w /work plantuml/plantuml:1.2025.4 -tsvg specs/*/*.puml
```

## 5. Making `docker compose up` work the first time

Reviewers clone the repository and run **one command**, with no `.env` file present. Checklist:

- Compose uses `${VAR:-dev-default}` for every variable, so it starts without a `.env` file. `.env.example` documents the same keys. Real secrets are never committed; the dev JWT secret is explicitly named `dev-insecure-change-me`.
- **Healthchecks** on postgres, redis and minio, plus `depends_on: condition: service_healthy`.
- Redis runs with `appendonly yes` on a `redisdata` volume, so queued Celery tasks survive a restart.
- **One-shot services**: `migrate` (alembic upgrade head) and `minio-init` (create bucket). `api`, `worker` and `transcriber` wait on them with `condition: service_completed_successfully`, so nothing races to migrate.
- Only `web` (`8080`) and `flower` (`5555`) are published to the host. Everything else talks over the compose network. nginx proxies `/api` and `/ws` with WebSocket upgrade headers, so the browser sees a **single origin**: no CORS, and the auth cookies reach every endpoint.
- The ffmpeg binary is installed in the api image (`apt-get install -y --no-install-recommends ffmpeg`). Both `api` (ffprobe validation) and `worker` (transcoding) need it.
- `docker-compose.dev.yml` (committed) for hot reload: bind-mounted source, `uvicorn --reload`, Celery restarted on change with `watchfiles`, Vite dev server proxying `/api` and `/ws`, MinIO console. Run it with `make dev`.
- The `transcriber` service is built from a separate Dockerfile target that adds faster-whisper and downloads the `base` model **at build time**. The first `docker compose up` needs no extra steps, and the api/worker images stay small. Other model sizes (`WHISPER_MODEL`) download on first use into the `whisper-models` volume.

See the [system architecture](system-architecture.svg) and [compose topology](deployment-compose.svg) diagrams in this folder.
