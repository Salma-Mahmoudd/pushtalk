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

`pnpm dev` forwards `/api` to the API (`API_PROXY_TARGET`, default `http://localhost:8001`, the API started by `make dev`), so the browser sees one origin, as with nginx in production.

In Docker, the `web` image builds the app and nginx serves `dist/` ([`nginx/default.conf`](nginx/default.conf)): `/api/` is proxied to the API, hashed assets are cached for a year, and every response carries a Content-Security-Policy that allows only same-origin scripts ([`nginx/security-headers.conf`](nginx/security-headers.conf)). For that reason the pre-paint theme script lives in `public/theme-init.js` instead of inline in `index.html`.

## UI

- **Tailwind CSS v4** through the Vite plugin; styles and theme variables live in `src/index.css`.
- **shadcn/ui** (Radix UI, Vega style, RTL-ready). Components are copied into `src/shared/ui/` and added only when a feature needs them:

  ```bash
  pnpm dlx shadcn@latest add dialog
  ```

- **Theme:** [tweakcn Twitter](https://tweakcn.com/) in light and dark, Open Sans (self-hosted). `src/shared/theme/` holds the provider (`next-themes`: light, dark or system, saved in `localStorage`) and the toggle. `public/theme-init.js` applies the saved theme before the first paint.
- Imports use the `@/` alias for `src/` (for example `@/shared/ui/button`).

## Configuration

| Variable | Default | Used for |
| --- | --- | --- |
| `VITE_SITE_URL` | `http://localhost:8080` | Absolute address in the social-preview tags (`og:url`, `og:image`) of `index.html` |
| `API_PROXY_TARGET` | `http://localhost:8001` | Where `pnpm dev` forwards `/api` |

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
