# PushTalk web

The PushTalk browser app: React + TypeScript, built with Vite.

## Scripts

Run from `apps/web/` (Node and pnpm versions: see [`../../steps/environment-setup.md`](../../steps/environment-setup.md)).

| Command | What it does |
| --- | --- |
| `pnpm install` | Install dependencies from `pnpm-lock.yaml` |
| `pnpm dev` | Development server with hot reload on <http://localhost:5173> |
| `pnpm build` | Type-check and build optimised static files into `dist/` |
| `pnpm preview` | Serve the built `dist/` locally to check a production build |
| `pnpm lint` | ESLint |
| `pnpm test` | Unit tests (Vitest) |
| `make types` (repository root) | Regenerate `src/shared/lib/api/schema.d.ts` from the API's OpenAPI description |

`pnpm dev` forwards `/api` and `/ws` to the API (`API_PROXY_TARGET`, default `http://localhost:8001`, the API started by `make dev`), so the browser sees one origin, as with nginx in production.

In Docker, the `web` image builds the app and nginx serves `dist/` ([`nginx/default.conf`](nginx/default.conf)): `/api/` and `/ws/` (WebSocket upgrade, 1 h idle timeout) are proxied to the API, hashed assets are cached for a year, and every response carries a Content-Security-Policy that allows only same-origin scripts ([`nginx/security-headers.conf`](nginx/security-headers.conf)). For that reason the pre-paint theme script lives in `public/theme-init.js` instead of inline in `index.html`.

## UI

- **Tailwind CSS v4** through the Vite plugin; styles and theme variables live in `src/index.css`.
- **shadcn/ui** (Radix UI, Vega style, RTL-ready). Components are copied into `src/shared/ui/` and added only when a feature needs them:

  ```bash
  pnpm dlx shadcn@latest add dialog
  ```

- **Theme:** [tweakcn Twitter](https://tweakcn.com/) in light and dark, Open Sans (self-hosted). One change: a darker light-mode `--input`, so field outlines stay visible. `src/shared/theme/` holds the provider (`next-themes`: light, dark or system, saved in `localStorage`) and the toggle. `public/theme-init.js` applies the saved theme before the first paint.
- Imports use the `@/` alias for `src/` (for example `@/shared/ui/button`).

## Layout

```text
src/
  main.tsx            Entry: theme provider + app
  app/                App level: router, session start-up, logged-in shell (header, log out)
  features/
    auth/             API calls, session store, refresh + tab sync, log-in/sign-up pages, route guards
    channels/         Sidebar, browse/join, create dialog, channel room with live member presence,
                      message store (keyed by client id, status only moves forward), sending, message list,
                      history paging, catch-up after reconnects, receipts (sent → delivered → played)
    directs/          Direct messages: sidebar list with online dots, user search dialog, and the
                      app-wide /ws/me socket (new conversations appear live); rooms reuse channels/
    voice/            Recorder (MediaRecorder), push-to-talk button (pointer or Space, 0.5–60 s),
                      playback queue (autoplay in order) and its audio element player
  shared/
    lib/api/          API client (cookies, error envelope → ApiError, one refresh for concurrent 401s)
                      and schema.d.ts, generated from the API (never edited by hand)
    lib/ws/           WsClient: reconnect with backoff (0.5 s doubling to 30 s, ±20 %), at once when
                      back online, drop the socket when the browser goes offline; refresh once on 4401,
                      stop on 4403; ping every 25 s
    hooks/            Shared hooks (useIsMobile)
    ui/               shadcn/ui components
    theme/            Light/dark/system provider and toggle
    brand/            Logo
```

Features import from `shared/`, never from each other's internals; `app/` composes them (for example, the app shell passes the direct message list into the channel sidebar).

### Session handling

Tokens live in httpOnly cookies and are never readable by JavaScript; the app only knows when the access cookie expires. `features/auth/session.ts` refreshes a minute before that, and the API client refreshes after any 401 and retries once. Tabs share one session: a Web Lock lets one tab refresh at a time, and a `BroadcastChannel` passes logins, refreshes and logouts to the other tabs.

### Server data

TanStack Query holds data from the API (channels, members); creating or joining a channel refreshes it, and a room refreshes its member list on `member.joined` events and after every reconnect. The cache is cleared when the session ends. Live state that only arrives over the WebSocket (who is online) stays in the room's hook.

### Playback

`features/voice/playback-queue.ts` decides what plays, without touching the DOM (unit-tested); `html-audio-player.ts` plays one `<audio>` source at a time.

- **Order:** incoming messages queue by channel sequence number and play one after another; a message that arrives late (catch-up, gap fill) slots into place. The same sequence number never queues twice, and the user's own messages never autoplay.
- **What autoplays:** messages that arrive live, and messages caught up after a reconnect. Opening a room or reloading the page shows history without playing it.
- **Browser autoplay rules:** audio starts only after the user has interacted with the page. Arriving through a click (for example on the channel link) counts; otherwise a banner shows how many messages are waiting, and the first tap or key press anywhere starts them.
- **While recording:** playback pauses when push-to-talk starts and resumes after release.
- **Speed:** 1×, 1.5× or 2× from the room header, pitch preserved. It applies to the message playing now without restarting it and to every later one, and is saved in `localStorage` (`features/voice/playback-settings.ts`).
- **Manual play:** the play button on any message interrupts the queue; the queue continues afterwards.
- **One playing tab per user:** each socket can claim playback (`playback.claim`). The focused tab claims on open and on focus; other tabs and devices of the same user show "Playing in another tab or device" with a "Play here" button.
- **Transcripts:** each ready message shows "Transcribing…", then its text under the bubble (`lang` and `dir="auto"` set, so right-to-left languages display correctly), "No speech detected", or "Transcript unavailable". The text arrives in a `message.transcribed` event; a finished transcript is never replaced by an older copy that still says pending.
- **Receipts:** the room reports `delivered` when a message arrives and `played` when it plays to the end. Senders see "Delivered n/m" or "Played n/m" under their messages, live, and a click opens the per-person times.

## Configuration

| Variable | Default | Used for |
| --- | --- | --- |
| `VITE_SITE_URL` | `http://localhost:8080` | Absolute address in the social-preview tags (`og:url`, `og:image`) of `index.html` |
| `API_PROXY_TARGET` | `http://localhost:8001` | Where `pnpm dev` forwards `/api` and `/ws` |

## Brand assets

| File | Purpose |
| --- | --- |
| `brand/mark.svg` | Master logo: speech bubble with voice waveform on Twitter blue `#1e9df1` |
| `brand/logo-light.svg`, `brand/logo-dark.svg` | Logo + "PushTalk" wordmark for light and dark backgrounds (used by the project README) |
| `public/favicon.svg`, `public/favicon.ico` | Browser tab icon (SVG for current browsers, ICO with 16/32/48 px) |
| `public/apple-touch-icon.png` | Icon for Safari bookmarks and the iOS home screen (180 px) |
| `public/og-image.png` | Link preview image (1200 × 630) for Open Graph and Twitter cards |

## Metadata

`index.html` holds the page title, description, light/dark theme colors, icons, and Open Graph / Twitter card tags. `public/robots.txt` allows indexing of the sign-in pages only; channels and the API require an account.
