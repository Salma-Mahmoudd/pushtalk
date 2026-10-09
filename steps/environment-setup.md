# Environment setup

What a machine needs to run and develop PushTalk. Each tool is installed with the method that suits the operating system, using the official guides linked below.

## What is needed for what

| Goal | Needs |
| --- | --- |
| Run the app (`docker compose up`) | Docker with Compose v2 |
| Work on `apps/web` (React, TypeScript) | Node + pnpm |
| Work on `apps/api` (FastAPI, Celery worker) | uv + Python |
| Re-render the `specs/` diagrams | Docker |
| Version control | Git |

Only Docker is required to run the app. The other tools are for development outside containers.

## Tools

| Tool | Version | Pinned in | Install | Upgrade |
| --- | --- | --- | --- | --- |
| Docker + Compose v2 | latest stable | — | [Get Docker](https://docs.docker.com/get-started/get-docker/) | [Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/) · Docker Desktop updates itself |
| Git | any recent | — | [Downloads](https://git-scm.com/downloads) | Same page, or the system package manager |
| Node | 24 (LTS) | `.nvmrc` | [nvm](https://github.com/nvm-sh/nvm#installing-and-updating) (Linux, macOS) · [nvm-windows](https://github.com/coreybutler/nvm-windows) | `nvm install` |
| pnpm | set by the web app | `packageManager` in `apps/web/package.json` | [Corepack](https://pnpm.io/installation#using-corepack) | Automatic: Corepack follows `packageManager` |
| uv | latest | — | [Installation](https://docs.astral.sh/uv/getting-started/installation/) | [`uv self update`](https://docs.astral.sh/uv/getting-started/installation/#upgrading-uv) |
| Python | 3.12 | `.python-version` | [`uv python install`](https://docs.astral.sh/uv/guides/install-python/) | Same command after the pin changes |

### Operating system notes

- **Linux:** after installing Docker Engine, follow the [post-install steps](https://docs.docker.com/engine/install/linux-postinstall/) so `docker` runs without `sudo`.
- **macOS:** Docker Desktop includes Compose v2.
- **Windows:** use [WSL 2](https://learn.microsoft.com/en-us/windows/wsl/install) with Docker Desktop, and run every command below inside the WSL terminal.
- Compose v2 is the `docker compose` subcommand. The older `docker-compose` binary is not supported.

## First run

Run every command from the repository root.

**1. Node**, version read from `.nvmrc`:

```bash
nvm install
```

```bash
nvm use
```

**2. pnpm**, version read from `packageManager`:

```bash
corepack enable
```

**3. Python**, version read from `.python-version`:

```bash
uv python install
```

**4. Web dependencies:**

```bash
pnpm --dir apps/web install
```

**5. API dependencies:**

```bash
uv sync --project apps/api
```

**6. Check** that every tool answers with a version:

```bash
docker compose version && git --version && node -v && pnpm -v && uv --version
```

## Diagrams

**Viewing needs no setup.** The rendered `*.svg` files are committed next to their sources in `specs/`. They open on GitHub, in any browser, or in the editor.

**Re-rendering** is only needed after editing a `*.puml` source. PlantUML needs Java, so to avoid installing Java it runs inside a Docker container:

```bash
docker run --rm --user "$(id -u):$(id -g)" -e JAVA_TOOL_OPTIONS=-Duser.home=/tmp -v "$PWD":/work -w /work plantuml/plantuml:1.2025.4 -tsvg specs/*/*.puml
```

How it works: a container has its own separate file system and cannot see the project folder by default.

| Part | Meaning |
| --- | --- |
| `--rm` | Delete the container when it finishes |
| `--user "$(id -u):$(id -g)"` | Run as the current user, so the new SVG files belong to that user and not to `root` |
| `-e JAVA_TOOL_OPTIONS=-Duser.home=/tmp` | Give Java a writable home folder inside the container. That user has no home folder, so without this Java writes a font cache into the repository under a folder named `?` |
| `-v "$PWD":/work` | Share the current folder (the repository) with the container. Inside the container it appears at `/work`, a name chosen for this command |
| `-w /work` | Start the container in that shared folder |
| `plantuml/plantuml:1.2025.4` | The [official PlantUML image](https://hub.docker.com/r/plantuml/plantuml), pinned to the version that rendered the committed SVGs |
| `-tsvg specs/*/*.puml` | Render every diagram source to SVG |

Because `/work` is the shared repository folder, the SVG files are written straight into `specs/` on the host, next to their `.puml` sources.

For live previews while editing, use the [PlantUML extension for VS Code](https://marketplace.visualstudio.com/items?itemName=jebbs.plantuml).

## Upgrading

This file always describes the current setup and is updated in place. To upgrade a tool for the whole project, change its pin (`.nvmrc`, `.python-version`, `packageManager`) and the version in the table above.
