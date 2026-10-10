# Decisions

Each decision lists the options considered, the choice, the reasons, and the trade-off accepted. Detailed flows and diagrams live in [`specs/`](specs/README.md).

## Summary

| Area | Choice |
| --- | --- |
| Audio upload | HTTP multipart `POST`; the WebSocket carries JSON events only |
| Message arrives while recording | Received and queued; autoplay waits until the button is released |
| Autoplay before a user gesture | Visual notice; the first tap unlocks audio, then everything plays automatically |
| Same user in two tabs or devices | Only connections open on the channel can play; the most recently focused one plays; the others offer "▶ play here" |
| Ordering | Per-channel `seq`, assigned when processing finishes; catch-up with `since_seq` |
| Message status | Aggregated on the bubble **and** per recipient on click |
| Auth | JWT access token + rotating refresh token, both in httpOnly `SameSite=Strict` cookies |
| Job queue | Celery (Redis broker) + Flower |
| Media storage | Local Docker volume behind a small storage interface (MinIO planned; its images are no longer published) |
| Database access | SQLAlchemy 2 (async) + Alembic |
| Transcription | Local faster-whisper by default; optional cloud provider through an env variable |
| Repository | Plain polyglot monorepo (`apps/api`, `apps/web`), no monorepo framework |
| Frontend | React + TypeScript + Vite, Tailwind + shadcn/ui, Zustand + TanStack Query |
| Edge | nginx serves the built app and proxies `/api` and `/ws`, so the browser sees one origin |

---

## 1. Design questions from the brief

### 1.1 Upload audio over HTTP or over the WebSocket?

**Choice: HTTP multipart `POST /api/channels/{id}/messages`, answered with `202 Accepted`.**

| Option | For | Against |
| --- | --- | --- |
| **HTTP multipart** ✅ | One request, one clear result (`202`, `413`, `415`, `422`, `429`). Size limits enforced by nginx and the app before the body is read. Retries are idempotent through `client_msg_id`. Same auth, rate limiting and tests as every other endpoint | One extra request per message (about one round trip, negligible for a 0.5–60 s clip) |
| Binary WebSocket frames | Slightly lower latency; no new request | Framing, acknowledgements, size limits and resend-after-reconnect must be hand-built. A large upload blocks the socket, so incoming events queue behind it |

**Why:** the brief requires validation, queueing and processing before broadcast. That is a request with a definite outcome, which is what HTTP models. The WebSocket stays a thin, JSON-only event channel.

**Trade-off:** no live streaming while the button is held. The brief sends the message when recording stops, so streaming is not needed.

### 1.2 What happens when a message arrives while the user is recording?

**Choice: the message is received and queued, and autoplay waits until the button is released (half-duplex, like a real walkie-talkie).**

- `PlaybackQueue.recordingStarted()` suspends playback; an item that was already playing is paused.
- On release the paused item resumes, then the queue drains in `seq` order. A badge shows how many messages are waiting.
- Delivery receipts are still sent while recording; "played" is sent only after real playback.

| Option | Against |
| --- | --- |
| Play over the recording | Incoming audio leaks into the microphone and the sender talks over someone |
| Drop or skip incoming messages | Messages are lost from the listening experience |
| **Queue and hold** ✅ | Messages wait a few seconds |

**Trade-off:** a short delay for incoming audio, in exchange for clean recordings and no lost messages.

### 1.3 Browsers block audio without a prior user gesture. What happens on first load?

**Choice: a visual notice; the first tap unlocks audio, then everything plays automatically.**

- The queue starts in a `Locked` state. Messages that arrive are buffered, and a "🔊 Tap to enable audio" banner appears.
- The first click anywhere (or pressing the push-to-talk button) calls `unlock()`: a silent clip plays on the audio elements and the `AudioContext` resumes. From then on autoplay works for the life of the page.
- Messages buffered while locked play in order right after the tap.

**Trade-off:** one tap per page load. Browsers do not allow anything less; the notice makes the reason visible instead of failing silently.

### 1.4 What happens when the same user is connected from two tabs or two devices?

**Choice: only connections open on that channel are candidates; among them, the most recently focused one plays. The others stay silent and show "▶ play here".**

- Each tab has its own WebSocket per channel, so a tab showing another channel never receives this channel's audio.
- On focus, a tab sends `playback.claim`. The server marks that connection as the active player and sends `playback.released` to the user's other connections on the channel.
- "Last focused" instead of "currently focused": a walkie-talkie must keep working while the browser is in the background, when no tab has focus.
- Inactive connections still show messages and send `delivered`; "▶ play here" moves playback to them. `played` is idempotent, so the first play wins.
- Presence keeps one heartbeat entry per connection, so the user stays online until the last tab closes.

| Option | Against |
| --- | --- |
| Play in every tab or device | Echo when devices share a room |
| Play only in the currently focused tab | Nothing plays while the browser is in the background |
| **Channel-open + last focused** ✅ | One extra event type (`playback.claim` / `playback.released`) |

### 1.5 How is message ordering guaranteed, including after a reconnect?

**Choice: a per-channel monotonic `seq`, assigned in the same transaction that marks a message `ready`.**

- The worker runs `UPDATE channels SET last_seq = last_seq + 1 … RETURNING last_seq` together with the update to `ready`. The row lock serialises concurrent workers, so `seq` is gapless and strictly increasing among ready messages. Failed messages never take a number.
- Clients track `lastSeq` per channel. On (re)connect they send `since_seq`; the server subscribes to pub/sub **before** querying Postgres, so nothing published in between is lost. The client ignores duplicate `seq` values and fetches any gap over REST.
- The playback queue plays strictly in `seq` order, one message at a time.

| Option | Against |
| --- | --- |
| **`seq` when processing finishes** ✅ | Order follows processing completion, not button release |
| `seq` at upload | One slow or failed message blocks everything behind it; needs "skip" markers and timeouts |
| Order by `created_at` | Ties within a millisecond and clock differences between servers; `>` loses messages and `>=` duplicates them on reconnect |
| Redis Stream IDs | A second source of truth next to Postgres, plus retention decisions |

**Trade-off:** two people releasing within about a second of each other may be heard in finishing order. In exchange, no listener ever waits behind a slow or failed message, and catch-up is a single query with no gap handling.

### 1.6 Message status (story 7): per recipient or aggregated?

**Choice: both.** The bubble shows the aggregate (`sent → delivered 2/3 → played 1/3`). Clicking one of the user's own messages opens a per-recipient list with delivered and played times. Both views come from the same `message_receipts` rows and update live through `receipt.updated`.

---

## 2. Stack and architecture

### 2.1 Authentication: JWT access token + rotating refresh token in cookies

The brief allows "JWT or session".

| Option | Token theft through XSS | WebSocket and `<audio src>` | Real logout | Extra work |
| --- | --- | --- | --- | --- |
| JWT in `localStorage` | ❌ readable by scripts | Token in the URL; audio fetched into memory | ❌ valid until expiry | — |
| Session id in Redis + cookie | ✅ | ✅ cookie sent automatically | ✅ | Small |
| JWT in an httpOnly cookie only | ✅ | ✅ | ❌ valid until expiry | Small |
| **JWT access + refresh, both in httpOnly cookies** ✅ | ✅ | ✅ | ✅ | Most |

**Design:**

- Access token: JWT, 15 minutes, in cookie `pt_access` (`HttpOnly`, `Secure`, `SameSite=Strict`).
- Refresh token: random opaque value, 7 days, in cookie `pt_refresh` scoped to `Path=/api/auth`. The database stores only its SHA-256 hash.
- Every refresh rotates the token. Reusing an already rotated token after a 10-second grace window revokes the whole login (theft detection). The grace window covers a lost response followed by a retry.
- Tabs coordinate through the Web Locks API so only one refreshes at a time, which keeps reuse detection from firing on normal use.
- CSRF: `SameSite=Strict` plus an Origin check on unsafe requests and WebSocket handshakes.
- Logout revokes the login and closes its open sockets.

**Trade-off:** the most code of the four options, mostly in the refresh path and multi-tab coordination, which are covered by tests. In exchange: no token readable by scripts, no tokens in URLs or logs, native audio streaming and seeking, and server-side logout.

### 2.2 Background jobs: Celery

| Option | For | Against |
| --- | --- | --- |
| **Celery** ✅ | Industry standard; rich retries, routing, time limits, `acks_late`; Flower dashboard | Tasks are synchronous functions, so async code runs through `asyncio.run()` with a per-task database engine (`NullPool`) |
| arq | Async-native, smallest amount of glue code | Smaller community, no dashboard, maintenance mode |
| RQ | Very simple | Synchronous, basic retries and timeouts |

**Reliability settings:** `acks_late` and `task_reject_on_worker_lost` (a task is not lost if a worker dies), prefetch of 1, exponential-backoff retries for transient errors, idempotent tasks guarded by message status, and Redis with `appendonly yes` so queued tasks survive a restart. Two queues, `audio` and `transcribe`, keep slow transcription from delaying delivery.

**Trade-off:** a little glue code and a new database connection per task, in exchange for a mature, well-understood queue with monitoring.

### 2.3 Media storage: local volume

The brief allows "local volume or MinIO". MinIO was the first choice (S3 API, the same code would work with real S3), but MinIO no longer publishes its community images: `minio/minio` is gone from Docker Hub, Quay requires a login, and the Bitnami images are frozen without security updates. A fresh `docker compose up` cannot depend on that.

| Option | Against |
| --- | --- |
| **Local volume** ✅ | Several *hosts* would need shared storage (several processes on one host are fine) |
| Frozen MinIO image | No security fixes since August 2025; may disappear like the others |
| Another S3 server (Garage, SeaweedFS) | Not named in the brief; extra key and bucket set-up |

Audio lives in a Docker volume mounted by the API and the worker, behind `FileStorage` (save, move in, delete, path). Keys are generated by the server, and a key that would leave the media folder is refused. Files are never served directly: the API checks membership (non-members get `404`, which does not reveal that the message exists) and streams with `Range` support, so seeking works. An S3 implementation of the same interface is a contained change.

### 2.4 Database access: SQLAlchemy 2 (async) + Alembic

The standard, typed, async-capable ORM with first-class migrations. SQLModel was not chosen because it adds a layer over SQLAlchemy without removing the need to know SQLAlchemy. Migrations run in a one-shot `migrate` service before the API and workers start.

### 2.5 Transcription: local by default, cloud optional

| Option | Against |
| --- | --- |
| Cloud API only | Reviewers have no key, so the feature fails on a fresh clone; audio leaves the system; costs money |
| **Local faster-whisper, optional cloud provider** ✅ | Larger transcriber image |
| Vosk | Lower accuracy, no punctuation |

`TRANSCRIBE_PROVIDER=local` (default) runs faster-whisper on the CPU inside Docker with no keys. The `base` model is downloaded at build time, so the first `docker compose up` works offline; `WHISPER_MODEL` selects another size, downloaded on first use. `TRANSCRIBE_PROVIDER=openai` with `OPENAI_API_KEY` switches to a cloud engine for a deployed setup. Transcription is a second worker step on its own queue and never delays message delivery.

### 2.6 Repository: plain polyglot monorepo

Two apps in two languages cannot share code directly, so Nx, Turborepo or Bazel would add configuration with little payoff. Each side uses its native tool (uv for Python, pnpm for TypeScript); a root `Makefile` and `docker-compose.yml` tie them together. The API and the workers are one Python package and one image started with different commands, so models and settings cannot drift. TypeScript types are generated from FastAPI's OpenAPI schema. Full reasoning: [`specs/app-arch/monorepo-decision.md`](specs/app-arch/monorepo-decision.md).

**Layout:** feature folders on both sides. Backend `src/pushtalk/{auth,channels,messages,dms,…}`, each with router → service → repository → models → schemas; frontend `src/features/{auth,channels,voice,dms}` plus `src/shared/`. Layers stay explicit, and one feature lives in one folder.

### 2.7 Frontend

- **Zustand** for client state (session, messages, presence, settings) and **TanStack Query** for REST data and caching: small, explicit state boundaries.
- **Tailwind + shadcn/ui**: accessible components copied into the repository, no runtime UI library.
- `PlaybackQueue` is plain TypeScript with an injected audio player, so its ordering and state rules are unit-tested without a browser.

### 2.8 Edge: nginx and a single origin

nginx serves the built app and proxies `/api` and `/ws` to FastAPI. The browser sees one origin, so `SameSite=Strict` cookies reach every endpoint and CORS is not needed. nginx also rejects oversized uploads before they reach Python and keeps idle WebSockets open. In development the Vite dev server plays the same proxy role with hot reload.

### 2.9 Presence and rate limiting in Redis

- **Presence:** one entry per connection in a Redis sorted set, refreshed by a heartbeat every 25 s and expired after 60 s. Users go offline on their own even if an API process crashes.
- **Rate limiting:** a Redis sliding window per user and per IP, shared by auth (login, signup) and chat (uploads, channel and DM creation, WebSocket events). Limited requests get `429` with `Retry-After`.

---

## 3. Scope

Everything in the brief is built: the seven user stories, the processing pipeline, protected audio, all non-functional requirements, the tests, all four stretch goals (playback speed, transcription, direct messages, per-user rate limiting) and the demo video. Nothing is cut.

**Trade-off:** the full scope is larger than the brief's suggested time box. Phases are ordered so the core (skeleton, auth, channels, voice pipeline, realtime correctness) is complete and tested before the stretch goals build on it, and commits stay small so every step is runnable.

**Not part of the brief, so not built:** password reset, email verification, OAuth, account deletion, a CI pipeline, HTTPS termination, a metrics and tracing stack, Kubernetes.

## 4. Known limitations

- Ordering follows processing completion (1.5).
- Safari records AAC (`audio/mp4`); uploads are accepted and normalised, but OGG/Opus playback depends on the Safari version. Chrome is the supported browser, as the brief requires.
- Mobile browsers throttle background tabs; queued messages play when the tab returns to the foreground.
- CPU transcription of a 60 s clip takes several seconds; the transcript appears after the audio.

## 5. With twice the time

- **Live push-to-talk streaming:** send audio chunks while the button is held (WebRTC or chunked WebSocket) for sub-second latency, keeping the processed copy for history.
- **End-to-end tests:** Playwright with two browser contexts covering record → autoplay → receipts → reconnect.
- **CI:** lint, type checks, tests and a `docker compose up` smoke test on every push.
- **Observability:** OpenTelemetry traces from the upload request through the Celery task to the WebSocket broadcast; metrics for queue depth and processing time.
- **Scale test:** several API replicas and workers behind nginx, with a load test (k6) on uploads and WebSocket fan-out.
- **Offline upload queue:** keep recordings made without a connection and send them on reconnect.
- **Storage lifecycle:** retention rules for audio and signed, cacheable media URLs.
- **Faster transcription:** GPU or streaming transcription, with language and speaker hints.
