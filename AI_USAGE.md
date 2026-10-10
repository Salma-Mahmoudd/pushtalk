# AI usage

AI tools used: **Claude Code** (Anthropic), an AI coding assistant working in the terminal and the editor on this repository.

## What it was used for

| Area | Use |
| --- | --- |
| Planning | Breaking the brief into phases, drafting the plans and PlantUML diagrams in `specs/`, and laying out the options with their trade-offs for each design question |
| Decisions | Drafting `DECISIONS.md` from the options that were discussed; every choice (upload over HTTP, half-duplex queueing, the unlock banner, playback ownership, `seq` ordering, cookies with rotating refresh tokens, Celery, local volume, local transcription, repository layout, UI library and theme) was made by the developer after the comparison |
| Code | Writing the backend, the frontend, the migrations, the Docker and Compose files and the Makefile, in small commits reviewed before each commit |
| Tests | Writing the pytest and Vitest suites, and running headless Chrome checks of the full flows (two and three users, real speech as microphone input, offline and reconnect, two tabs) during development |
| Debugging | Investigating failures found by those checks, for example: nginx keeping a stale API address after a restart, a PyAV release incompatible with faster-whisper, the recording timer resetting on re-renders, rate limits keyed by the proxy's address, and the allowed origin not following `WEB_PORT` |
| Documentation | READMEs, the environment setup guide and code comments |

## How the output was checked

- Each commit was staged and explained before it was made; the developer approved the plan for each phase and the choice for each open decision.
- Every change ran through the type checkers (mypy strict, TypeScript strict), the linters (ruff, ESLint) and the test suites before it was committed.
- User-facing behaviour was checked in a real browser against the running Docker stack, including a fresh clone started with `docker compose up --build`.
- Library versions and APIs were checked against their documentation rather than taken from memory.
