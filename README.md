<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="apps/web/brand/logo-dark.svg" />
    <img src="apps/web/brand/logo-light.svg" alt="PushTalk" width="280" />
  </picture>
</p>

<p align="center"><strong>Walkie-talkie voice channels in the browser.</strong><br />Hold to talk, release to send. Everyone in the channel hears it automatically, in order.</p>

---

## Status

Planning is complete and the skeleton (Phase 0) is in progress. The roadmap, phase by phase, is in [`specs/README.md`](specs/README.md).

## Features

- Sign up and log in; create or join channels; see who is online
- Hold a button to record (0.5–60 s), release to send
- Incoming messages play automatically, one at a time, in order; own messages never play back
- History and catch-up after being offline; status per message: sent → delivered → played
- Server-side processing before broadcast: validation, Opus/OGG normalisation, waveform peaks
- Playback speed (1× / 1.5× / 2×), transcription, direct messages, per-user rate limiting

## Stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic |
| Jobs and realtime | Celery + Redis (broker, pub/sub), Flower |
| Storage | PostgreSQL, MinIO (S3) |
| Frontend | React + TypeScript, Vite, Tailwind CSS, shadcn/ui, Zustand, TanStack Query |
| Edge and runtime | nginx, Docker Compose |

## Repository layout

```text
apps/web/     React app (brand assets in apps/web/brand/)
apps/api/     FastAPI app, Celery workers (Phase 0)
specs/        Phased plans and diagrams
steps/        Environment setup guide
DECISIONS.md  Design decisions and trade-offs
```

## Documentation

- [Environment setup](steps/environment-setup.md): tools, versions and first-run commands
- [Specs and roadmap](specs/README.md): plans, diagrams and acceptance criteria per phase
- [Decisions](DECISIONS.md): design questions, options considered and trade-offs
