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
| `uv run mypy` | Strict type check of `src/pushtalk` |

## Layout

```text
src/pushtalk/
  main.py     App factory (create_app) and the ASGI app
tests/        pytest suite (async tests run with pytest-asyncio)
```

Feature folders (`auth/`, `channels/`, `messages/`, …) are added phase by phase, following [`../../specs/app-arch/monorepo-decision.md`](../../specs/app-arch/monorepo-decision.md).
