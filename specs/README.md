# PushTalk specs

Planning docs for the PushTalk assignment

| Folder | What's inside |
| --- | --- |
| [`app-arch/`](app-arch/plan.md) | Monorepo decision guide, docker compose topology, cross-cutting conventions (errors, config, logging, rate limiter, typing), Phase 0 + Phase 6 |
| [`auth/`](auth/plan.md) | Sign up / log in: JWT access + rotating refresh token in httpOnly cookies, CSRF Origin check, brute-force limits. Phase 1 |
| [`chat/`](chat/plan.md) | Channels, presence, voice pipeline, realtime, playback queue, receipts, the 5 design decisions, and all four "stretch" features. Phases 2–5 |

Every `*.puml` file sits next to its rendered SVGs. A `.puml` holding several `@startuml <name>` blocks produces one `<name>.svg` per block. Each plan embeds its diagrams, so they show directly on GitHub and in the editor's Markdown preview.

![System architecture](app-arch/system-architecture.svg)

## Phase roadmap

| Phase | Scope | Spec | Brief coverage |
| --- | --- | --- | --- |
| **0** | Skeleton: monorepo, compose (+ dev override) with healthchecks, config, logs, error envelope, strict typing/lint, Alembic baseline | app-arch | DevOps hygiene, code quality |
| **1** | Auth: users, signup/login, cookie JWT + refresh rotation, logout, shared rate limiter with login/signup limits, FE auth pages and session sync | auth | Story 1 |
| **2** | Channels, membership, WS hub, Redis pub/sub, heartbeat presence | chat | Story 2 |
| **3** | Voice pipeline: record → upload → validate → Celery + ffmpeg → broadcast; failure path; protected audio | chat | Stories 3, 7, pipeline, security |
| **4** | Catch-up + reconnect/backoff, PlaybackQueue, autoplay unlock, receipts (aggregated **and** per-recipient), multi-tab/device | chat | Stories 4–7, realtime correctness |
| **5** | Playback speed · per-user rate limiting · transcription worker · direct messages | chat | "Stretch goals" (all of them) |
| **6** | README, DECISIONS.md, AI_USAGE.md, fresh-clone smoke test, 3–5 min demo video | app-arch | All deliverables |

Phases are ordered so the core (0–4) is solid before Phase 5 builds on it.

## Regenerating diagrams

Only needed after editing a `*.puml` source. From the repository root, with Docker running:

```bash
docker run --rm --user "$(id -u):$(id -g)" -e JAVA_TOOL_OPTIONS=-Duser.home=/tmp -v "$PWD":/work -w /work plantuml/plantuml:1.2025.4 -tsvg specs/*/*.puml
```

See [`../steps/environment-setup.md`](../steps/environment-setup.md#diagrams) for what each part of the command does.
